"""
Authentication — Playwright login + session capture.

Mirrors the Windows-Copilot-API design: the browser is used ONLY to establish a
signed-in session (handling the AWS WAF / "verify you're human" check and the
email/password form). It does not chat. We then capture the bearer token from
`localStorage.userToken` plus the session cookies, and hand them to the
pure-HTTP client in `deepseek.client`.

A persistent Chromium profile means the human-check is a one-time thing: once
you've signed in, later runs reuse the profile and capture the token headlessly.

    from deepseek.auth import get_session
    session = get_session()          # logs in (visible) the first time, else headless
    print(session.token[:8], "...")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

from playwright.sync_api import sync_playwright

try:
    import httpx
except ImportError:  # pragma: no cover — probe skipped without httpx
    httpx = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
# Override with DEEPSEEK_PROFILE_DIR to reuse an existing signed-in Chrome profile.
DEFAULT_PROFILE_DIR = Path(os.getenv("DEEPSEEK_PROFILE_DIR", ROOT / "session" / "profile"))
DEFAULT_SESSION_FILE = ROOT / "session" / "session.json"

CHAT_URL = "https://chat.deepseek.com/"
SIGNIN_URL = "https://chat.deepseek.com/sign_in"

# Do not modify browser automation fingerprints to try to defeat CAPTCHA/WAF.
# DeepSeek may require a real human verification step; the supported path is to
# let the user complete it in a visible browser.
LAUNCH_ARGS = []
DEEPSEEK_CDP_URL = os.getenv("DEEPSEEK_CDP_URL", "").strip()
# Token is trusted for this long before we refresh it from the browser again.
SESSION_MAX_AGE = 24 * 60 * 60  # 24 hours
HEADLESS_REFRESH = os.getenv('DEEPSEEK_HEADLESS_REFRESH', '0').lower() in {'1','true','yes'}
LOGIN_TIMEOUT = float(os.getenv("DEEPSEEK_LOGIN_TIMEOUT", "300"))


def _windows_chrome_exe() -> Optional[str]:
    """Real Chrome on Windows, for when Playwright's ``channel="chrome"`` can't
    find it (non-default install location). Returns None on other systems."""
    if os.name != "nt":
        return None
    for raw in (
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ):
        path = os.path.expandvars(raw)
        if path and os.path.isfile(path):
            return path
    return None


def _launch_persistent(p, profile_dir: Path, headless: bool):
    """Open the persistent profile, preferring a real Chrome over the bundled
    Chromium — a real Chrome is what survives Google sign-in and CAPTCHA/WAF."""
    try:
        return p.chromium.launch_persistent_context(
            str(profile_dir), headless=headless, channel="chrome", args=LAUNCH_ARGS,
        )
    except Exception:
        pass
    if os.name != "nt" and os.path.isfile("/usr/bin/chromium"):
        try:
            return p.chromium.launch_persistent_context(
                str(profile_dir), headless=headless, executable_path="/usr/bin/chromium",
                args=LAUNCH_ARGS,
            )
        except Exception:
            pass
    win_chrome = _windows_chrome_exe()
    if win_chrome is not None:
        try:
            return p.chromium.launch_persistent_context(
                str(profile_dir), headless=headless, executable_path=win_chrome,
                args=LAUNCH_ARGS,
            )
        except Exception:
            pass
    return p.chromium.launch_persistent_context(
        str(profile_dir), headless=headless, args=LAUNCH_ARGS,
    )


def _timeout_help() -> str:
    """Actionable next steps when the login window never yields a token.

    The two common causes are (1) Google sign-in refusing the automated
    browser ("This browser or app may not be secure") and (2) a CAPTCHA/WAF
    loop. Both are solved the same way: log in through a real Chrome via CDP
    instead of the Playwright build.
    """
    if os.name == "nt":
        return (
            "Likely causes: Google sign-in blocks automated browsers, or DeepSeek "
            "is looping a CAPTCHA/human-check.\n"
            "Fix — use a real Chrome via CDP:\n"
            '  1. Close Chrome, then run:\n'
            '     & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `\n'
            '       --remote-debugging-port=9222 `\n'
            '       --user-data-dir="$env:LOCALAPPDATA\\cassandra-chrome" `\n'
            '       --no-first-run "https://chat.deepseek.com/"\n'
            "  2. Sign in in that window (Google works there), solve any CAPTCHA.\n"
            "  3. In another terminal:\n"
            '     $env:DEEPSEEK_CDP_URL="http://127.0.0.1:9222"\n'
            "     python -m deepseek.auth\n"
            "Cassandra never solves CAPTCHAs itself — complete them by hand."
        )
    return (
        "Likely causes: Google sign-in blocks automated browsers, or DeepSeek "
        "is looping a CAPTCHA/human-check.\n"
        "Fix — use a real Chrome via CDP:\n"
        "  1. Close Chrome, then run:\n"
        "     google-chrome --remote-debugging-port=9222 \\\n"
        '       --user-data-dir="$HOME/.local/share/cassandra-chrome" \\\n'
        '       --no-first-run "https://chat.deepseek.com/"\n'
        "  2. Sign in in that window (Google works there), solve any CAPTCHA.\n"
        "  3. In another terminal:\n"
        "     export DEEPSEEK_CDP_URL=http://127.0.0.1:9222\n"
        "     python -m deepseek.auth\n"
        "Cassandra never solves CAPTCHAs itself — complete them by hand."
    )


class LoginRequired(RuntimeError):
    """Raised when no usable session exists and interactive login is disallowed
    (e.g. inside the server, where we can't pop open a browser mid-request).
    The message tells the user how to log in."""

    DEFAULT = (
        "No DeepSeek session found. Log in first by running:\n"
        "    python -m deepseek.auth\n"
        "This opens a browser once so you can sign in and clear the human-check; "
        "afterwards the server reuses the saved session automatically."
    )

    def __init__(self, message: str = DEFAULT):
        super().__init__(message)


@dataclass
class Session:
    """A captured signed-in DeepSeek session."""

    token: str
    cookies: Dict[str, str]
    user_agent: str
    captured_at: float

    @property
    def age(self) -> float:
        return time.time() - self.captured_at

    def save(self, path: Path = DEFAULT_SESSION_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = DEFAULT_SESSION_FILE) -> Optional["Session"]:
        if not path.exists():
            return None
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None


# --- in-page helpers --------------------------------------------------------

# Reads the bearer token the web app stores after login. Shape:
#   localStorage.userToken = {"value":"<TOKEN>","__version":"0"}
_READ_TOKEN_JS = """
() => {
  try {
    const raw = window.localStorage.getItem('userToken');
    if (!raw) return null;
    const o = JSON.parse(raw);
    return (o && o.value) ? o.value : null;
  } catch (e) { return null; }
}
"""


def _safe_evaluate(page, js: str):
    """Run page.evaluate, swallowing the benign 'Execution context was destroyed'
    error that fires when a navigation (e.g. the post-login redirect) happens to
    land mid-evaluate. Returns None on any such transient failure instead of
    raising, so callers can just retry on the next poll."""
    try:
        return page.evaluate(js)
    except Exception as e:
        msg = str(e)
        if "Execution context was destroyed" in msg or "navigation" in msg.lower():
            return None
        raise


def _probe_token(session: "Session") -> None:
    """Verify the captured token against the API before saving it.

    A token can exist in localStorage while the server already considers it
    revoked (logout elsewhere, server-side rotation). Saving it anyway means
    discovering the problem hours later as a cryptic chat failure. The probe
    creates a throwaway chat session (deleted right after) — if the server
    rejects the token we fail loudly here instead.

    Explicit auth rejection (401/403/auth markers) raises RuntimeError.
    Anything else (network blip, 429, 5xx) only warns and lets the save
    proceed — the client reports those properly at chat time.
    """
    if httpx is None:
        return
    try:
        r = httpx.post(
            "https://chat.deepseek.com/api/v0/chat_session/create",
            json={},
            headers={
                "authorization": f"Bearer {session.token}",
                "content-type": "application/json",
                "user-agent": session.user_agent,
                "origin": "https://chat.deepseek.com",
                "referer": "https://chat.deepseek.com/",
            },
            cookies=session.cookies,
            timeout=20.0,
        )
    except Exception as e:
        print(f"[auth] warning: could not validate the token ({type(e).__name__}); "
              "saving it anyway.")
        return
    body = r.text[:500]
    auth_markers = (
        "authorization failed", "invalid token", "unauthorized",
        "token expired", "login required", "please log in",
    )
    if r.status_code in (401, 403) or any(m in body.lower() for m in auth_markers):
        raise RuntimeError(
            "The captured token was rejected by DeepSeek (invalid/expired).\n"
            "Do a FULL logout + login in the browser window (avatar → sign out, "
            "sign back in, send a test message on the site), then run this again."
        )
    # Token accepted — delete the throwaway probe session to avoid clutter.
    try:
        data = r.json()
        cid = data.get("data", {}).get("biz_data", {}).get("chat_session", {}).get("id")
        if cid:
            httpx.post(
                "https://chat.deepseek.com/api/v0/chat_session/delete",
                json={"chat_session_id": cid},
                headers={"authorization": f"Bearer {session.token}"},
                cookies=session.cookies,
                timeout=20.0,
            )
    except Exception:
        pass


def _capture_from_context(context, page) -> Optional[Session]:
    """Read token + cookies + UA off a logged-in page, or None if not signed in."""
    token = _safe_evaluate(page, _READ_TOKEN_JS)
    if not token:
        return None
    cookies = {c["name"]: c["value"] for c in context.cookies()}
    ua = _safe_evaluate(page, "() => navigator.userAgent") or ""
    return Session(token=token, cookies=cookies, user_agent=ua, captured_at=time.time())


def _wait_for_token(page, timeout: float) -> Optional[str]:
    """Poll localStorage.userToken until it appears or we time out. Tolerates
    transient navigations (e.g. the Google OAuth redirect chain) that briefly
    destroy the page's JS execution context — those just count as "no token
    yet" rather than aborting the whole login."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        token = _safe_evaluate(page, _READ_TOKEN_JS)
        if token:
            return token
        try:
            page.wait_for_timeout(1000)
        except Exception:
            print("[auth] Navegador fechado pelo usuário antes do login ser concluído.")
            return None
    return None


def _safe_goto(page, url: str) -> None:
    """Navigate, tolerating the benign `net::ERR_ABORTED` that DeepSeek's SPA
    redirects and the AWS WAF check often raise mid-navigation. We wait only for
    the initial commit, not full `load`; the token-poll afterwards is what
    actually gates sign-in, so an aborted/partial load here is fine."""
    try:
        page.goto(url, wait_until="commit", timeout=60000)
    except Exception as e:
        print(f"[auth] navigation to {url} was interrupted ({type(e).__name__}); "
              "continuing — finish signing in in the window if needed.")
    # Give the SPA a moment to render its login UI before we touch the form.
    page.wait_for_timeout(2000)


def login(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = False,
    assume_logged_out: bool = False,
    timeout: float = LOGIN_TIMEOUT,
) -> Session:
    """Interactive login. Opens a visible window and waits for you to sign in by
    hand (and clear the AWS WAF human-check); once a token appears it captures
    and saves the session. The persistent profile means later `get_session()`
    calls capture the token headlessly without a window.

    `assume_logged_out=True` skips the initial "are we already signed in?" hop to
    CHAT_URL and goes straight to the sign-in page. Callers that have just
    confirmed there's no token (e.g. get_session after a failed headless refresh)
    pass this so the window doesn't visibly bounce CHAT_URL -> SIGNIN_URL."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        # Optional CDP mode reuses a normal Chrome window. This is useful when
        # DeepSeek's CAPTCHA/WAF rejects an automated browser. The user still
        # completes the challenge manually; Cassandra never solves or bypasses it.
        if DEEPSEEK_CDP_URL:
            browser = p.chromium.connect_over_cdp(DEEPSEEK_CDP_URL)
            contexts = browser.contexts
            context = contexts[0] if contexts else browser.new_context()
            owns_context = not bool(contexts)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            context = _launch_persistent(p, profile_dir, headless)
            owns_context = True
            page = context.pages[0] if context.pages else context.new_page()

        # Normally we first land on CHAT_URL to reuse an already-signed-in
        # profile. When the caller already knows we're logged out, skip straight
        # to the sign-in page so the window doesn't appear to "refresh".
        existing = None
        if not assume_logged_out:
            _safe_goto(page, CHAT_URL)
            existing = page.evaluate(_READ_TOKEN_JS)

        if not existing:
            _safe_goto(page, SIGNIN_URL)
            print("[auth] Please sign in in the window (solve the human-check if "
                  "shown). Waiting for the session...")
            if not _wait_for_token(page, timeout=timeout):
                if owns_context:
                    context.close()
                raise RuntimeError(
                    f"Login timed out after {timeout:.0f}s — no token captured.\n\n"
                    + _timeout_help()
                )

        session = _capture_from_context(context, page)
        if owns_context:
            context.close()
        if session is None:
            raise RuntimeError("Logged in but could not read the token.")
        _probe_token(session)
        session.save()
        return session


def _headless_refresh(profile_dir: Path) -> Optional[Session]:
    """Try to capture a token headlessly from the persistent profile. Returns a
    saved Session if the profile is still signed in, else None. Never opens a
    visible window."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = _launch_persistent(p, profile_dir, headless=True)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _safe_goto(page, CHAT_URL)
            session = _capture_from_context(context, page)
        finally:
            context.close()

    if session is not None:
        session.save()
    return session


def get_session(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    session_file: Path = DEFAULT_SESSION_FILE,
    max_age: int = SESSION_MAX_AGE,
    allow_interactive: bool = True,
) -> Session:
    """Return a usable session: cached file if fresh, else a headless refresh
    from the browser profile.

    If neither works and `allow_interactive` is True, open a visible window for
    manual sign-in. If it's False (the server's case — we can't pop a browser
    mid-request), raise `LoginRequired` telling the user to run the login step.

    For difficult CAPTCHA/WAF environments, set DEEPSEEK_CDP_URL to a Chrome
    instance started with remote debugging. This reuses the user's normal browser
    session instead of trying to disguise an automated browser.

    Note: this uses Playwright's *sync* API, so it must not be called from inside
    an asyncio event loop — call it from a worker thread (e.g. run_in_threadpool)."""
    cached = Session.load(session_file)
    if cached and cached.age < max_age:
        return cached

    # Headless browser refresh is opt-in. Automated background navigation can
    # trigger provider anti-abuse systems, so the safe default is to reuse the
    # saved session and require a human login when it expires.
    if HEADLESS_REFRESH:
        session = _headless_refresh(profile_dir)
        if session is not None:
            return session

    if not allow_interactive:
        raise LoginRequired()

    # Not logged in yet — open a visible window so the user can sign in (and
    # clear the human-check) by hand. The persistent profile means this only
    # happens once — later calls capture the token headlessly. We just confirmed
    # (above) there's no token, so go straight to the sign-in page.
    print("[auth] No valid session found — opening a browser window to log in...")
    return login(profile_dir=profile_dir, assume_logged_out=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="DeepSeek login helper — opens a browser once so you can sign "
                    "in, then saves the session for later runs."
    )
    ap.add_argument(
        "--cdp-url", default="",
        help="Chrome DevTools URL, e.g. http://127.0.0.1:9222. Reuses a real "
             "Chrome window (required for Google sign-in / CAPTCHA loops). "
             "Overrides DEEPSEEK_CDP_URL.",
    )
    ap.add_argument(
        "--timeout", type=float, default=LOGIN_TIMEOUT,
        help=f"Seconds to wait for login (default {LOGIN_TIMEOUT:.0f}).",
    )
    args = ap.parse_args()
    if args.cdp_url.strip():
        globals()["DEEPSEEK_CDP_URL"] = args.cdp_url.strip()
    s = login(timeout=args.timeout)
    print(f"[auth] captured token {s.token[:10]}... ({len(s.cookies)} cookies)")
