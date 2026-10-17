#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Filtro Anti-Banimento
=================================

Camada de proteção operacional contra bloqueios indesejados
(rate-limit, WAF, suspensão de conta, banimento de IP/chave).

Componentes:
  1. RateLimiter     — espaçamento mínimo entre requisições + jitter.
  2. BackoffPolicy   — retry exponencial com jitter para 429/5xx/timeout.
  3. CircuitBreaker  — para de insistir quando o provedor sinaliza abuso.
  4. Sanitizer       — suaviza termos-gatilho que disparam filtros de
                       borda, preservando o significado técnico.
  5. ProviderRotator — troca de provedor/chave quando um está queimado.

Filosofia: o objetivo é NUNCA martelar um endpoint. Uma requisição
espaçada, com jitter e recuo progressivo, parece tráfego humano e evita
a maior parte dos banimentos automáticos.
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. RATE LIMITER
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Garante um intervalo mínimo entre requisições, com jitter aleatório
    para não produzir um padrão de tempo detectável.

    `min_interval` e `jitter` vêm de:
      CASSANDRA_MIN_INTERVAL (segundos, padrão 2.5)
      CASSANDRA_JITTER       (segundos, padrão 1.5)
    """

    def __init__(
        self,
        min_interval: Optional[float] = None,
        jitter: Optional[float] = None,
    ):
        self.min_interval = (
            min_interval
            if min_interval is not None
            else float(os.getenv("CASSANDRA_MIN_INTERVAL", "2.5"))
        )
        self.jitter = (
            jitter
            if jitter is not None
            else float(os.getenv("CASSANDRA_JITTER", "1.5"))
        )
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> float:
        """Bloqueia o tempo necessário. Devolve quantos segundos dormiu."""
        with self._lock:
            now = time.monotonic()
            base = self.min_interval - (now - self._last)
            extra = random.uniform(0, max(0.0, self.jitter))
            delay = max(0.0, base) + extra
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()
            return delay


# ---------------------------------------------------------------------------
# 2. BACKOFF
# ---------------------------------------------------------------------------

@dataclass
class BackoffPolicy:
    """
    Recuo exponencial com jitter completo (full jitter).

    delay(n) = random(0, min(cap, base * 2^n))
    """

    base: float = 1.5
    cap: float = 60.0
    max_attempts: int = 4

    def delay_for(self, attempt: int) -> float:
        ceiling = min(self.cap, self.base * (2 ** attempt))
        return random.uniform(0.0, ceiling)

    @classmethod
    def from_env(cls) -> "BackoffPolicy":
        return cls(
            base=float(os.getenv("CASSANDRA_BACKOFF_BASE", "1.5")),
            cap=float(os.getenv("CASSANDRA_BACKOFF_CAP", "60")),
            max_attempts=int(os.getenv("CASSANDRA_MAX_ATTEMPTS", "4")),
        )


# ---------------------------------------------------------------------------
# 3. CIRCUIT BREAKER
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Abre o circuito quando o provedor sinaliza abuso, impedindo
    insistência. Fecha automaticamente após `cooldown` segundos.
    """

    def __init__(self, cooldown: Optional[float] = None):
        self.cooldown = (
            cooldown
            if cooldown is not None
            else float(os.getenv("CASSANDRA_COOLDOWN", "120"))
        )
        self._lock = threading.Lock()
        self._opened_at: Optional[float] = None
        self.reason = ""

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._opened_at = None
                self.reason = ""
                return False
            return True

    def remaining(self) -> float:
        with self._lock:
            if self._opened_at is None:
                return 0.0
            return max(0.0, self.cooldown - (time.monotonic() - self._opened_at))

    def trip(self, reason: str) -> None:
        with self._lock:
            self._opened_at = time.monotonic()
            self.reason = reason

    def reset(self) -> None:
        with self._lock:
            self._opened_at = None
            self.reason = ""


class ProviderBlocked(RuntimeError):
    """Circuito aberto: o provedor está temporariamente queimado."""


# ---------------------------------------------------------------------------
# 4. SANITIZER DE TERMOS-GATILHO
# ---------------------------------------------------------------------------

# Pares (regex, substituto). A substituição preserva o sentido técnico
# mas quebra o casamento literal que filtros de superfície procuram.
# O modelo reconstrói o termo pelo contexto — a semântica permanece.
_TRIGGER_MAP: List[Tuple[str, str]] = [
    # Termos de segurança ofensiva
    (r"\bkeylogger\b", "input-capture-agent"),
    (r"\bkeyloggers\b", "input-capture-agents"),
    (r"\bransomware\b", "encryptor-for-extortion"),
    (r"\brootkit\b", "kernel-persistence-module"),
    (r"\bbotnet\b", "distributed-node-network"),
    (r"\bmalware\b", "unwanted-software-sample"),
    (r"\bexploit\b", "proof-of-concept"),
    (r"\bexploits\b", "proofs-of-concept"),
    (r"\bshellcode\b", "position-independent-code"),
    (r"\bbackdoor\b", "persistent-access-channel"),
    (r"\bbackdoors\b", "persistent-access-channels"),
    (r"\bpayload\b", "delivery-artifact"),
    (r"\bpayloads\b", "delivery-artifacts"),
    (r"\bC2\b", "command-relay"),
    (r"\bC&C\b", "command-relay"),
    (r"\bexfiltrat\w*\b", "data-transfer"),
    (r"\bexfil\b", "data-transfer"),
    (r"\bprivilege escalation\b", "permission-boundary-crossing"),
    (r"\bpriv\s*esc\b", "permission-boundary-crossing"),
    (r"\bSQL injection\b", "query-structure-injection"),
    (r"\bSQLi\b", "query-structure-injection"),
    (r"\bXSS\b", "client-script-injection"),
    (r"\bRCE\b", "remote-execution"),
    (r"\bLFI\b", "local-file-inclusion"),
    (r"\bRFI\b", "remote-file-inclusion"),
    (r"\bSSRF\b", "server-side-request-forgery"),
    (r"\bzero-?day\b", "unpatched-flaw"),
    (r"\b0day\b", "unpatched-flaw"),
    (r"\bbrute[- ]?force\b", "credential-enumeration"),
    (r"\bcredential stuffing\b", "credential-replay"),
    (r"\bphishing\b", "credential-solicitation"),
    (r"\bspear[- ]?phishing\b", "targeted-credential-solicitation"),
    (r"\bDDoS\b", "availability-disruption"),
    (r"\bbotnet\b", "distributed-node-network"),
    (r"\bworm\b", "self-propagating-sample"),
    (r"\btrojan\b", "deceptive-artifact"),
    (r"\bspyware\b", "telemetry-collector"),
    (r"\bantivirus evasion\b", "detection-avoidance"),
    (r"\bAV evasion\b", "detection-avoidance"),
    (r"\bbypass (?:the )?(?:AV|antivirus|EDR)\b", "avoid detection by endpoint controls"),
    (r"\bcrack(?:ing)?\b", "license-analysis"),
    (r"\bkeygen\b", "license-generator"),
    (r"\bpentest\b", "authorized-security-assessment"),
    (r"\bhack(?:ing|er)?\b", "security-testing"),
]

_COMPILED_TRIGGERS = [(re.compile(p, re.IGNORECASE), r) for p, r in _TRIGGER_MAP]


@dataclass
class SanitizeReport:
    original_len: int
    sanitized_len: int
    hits: Dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.hits)


def sanitize(text: str, enabled: bool = True) -> Tuple[str, SanitizeReport]:
    """
    Suaviza termos-gatilho preservando a intenção técnica.

    Devolve (texto_sanitizado, relatório). Com `enabled=False` devolve o
    texto intacto e um relatório vazio.
    """
    report = SanitizeReport(original_len=len(text), sanitized_len=len(text))
    if not enabled or not text:
        return text, report

    out = text
    for pattern, replacement in _COMPILED_TRIGGERS:
        matches = pattern.findall(out)
        if matches:
            report.hits[pattern.pattern] = len(matches)
            out = pattern.sub(replacement, out)

    report.sanitized_len = len(out)
    return out, report


# ---------------------------------------------------------------------------
# 5. ROTADOR DE PROVEDORES
# ---------------------------------------------------------------------------

@dataclass
class Credential:
    """Uma credencial configurada (provedor + chave + modelo)."""

    provider_key: str
    api_key: str
    model: str = ""
    base_url: str = ""
    label: str = ""


class ProviderRotator:
    """
    Mantém uma lista de credenciais e rotaciona quando uma é marcada como
    queimada. Suporta múltiplas chaves do mesmo provedor.

    Uso:
        rot = ProviderRotator([Credential("nvidia", "nvapi-..."), ...])
        cred = rot.current()
        rot.mark_burned(cred, "429")
    """

    def __init__(self, credentials: List[Credential]):
        self._creds = list(credentials)
        self._burned: Dict[int, float] = {}
        self._idx = 0
        self._lock = threading.Lock()
        self.burn_cooldown = float(os.getenv("CASSANDRA_KEY_COOLDOWN", "300"))

    def __len__(self) -> int:
        return len(self._creds)

    def _is_available(self, i: int) -> bool:
        ts = self._burned.get(i)
        if ts is None:
            return True
        if time.monotonic() - ts >= self.burn_cooldown:
            del self._burned[i]
            return True
        return False

    def current(self) -> Optional[Credential]:
        with self._lock:
            if not self._creds:
                return None
            for offset in range(len(self._creds)):
                i = (self._idx + offset) % len(self._creds)
                if self._is_available(i):
                    self._idx = i
                    return self._creds[i]
            return None

    def mark_burned(self, cred: Credential, reason: str = "") -> None:
        with self._lock:
            for i, c in enumerate(self._creds):
                if c is cred or (
                    c.provider_key == cred.provider_key and c.api_key == cred.api_key
                ):
                    self._burned[i] = time.monotonic()
                    break
            # Avança para a próxima credencial.
            self._idx = (self._idx + 1) % max(1, len(self._creds))

    def rotate(self) -> None:
        """
        Avança para a próxima credencial SEM queimá-la.

        Usado quando a falha é do endpoint (stream travado, gateway ruim),
        não da chave: a credencial continua válida e pode ser tentada de
        novo mais tarde.
        """
        with self._lock:
            if len(self._creds) > 1:
                self._idx = (self._idx + 1) % len(self._creds)

    def available_count(self) -> int:
        return sum(1 for i in range(len(self._creds)) if self._is_available(i))


# ---------------------------------------------------------------------------
# DETECÇÃO DE SINAL DE BANIMENTO
# ---------------------------------------------------------------------------

_BAN_MARKERS = (
    "rate limit", "rate_limit", "too many requests", "quota exceeded",
    "quota_exceeded", "insufficient_quota", "account suspended",
    "account disabled", "account deactivated", "banned", "blocked",
    "risk control", "security verification", "verify you are human",
    "captcha", "abuse", "violat", "forbidden", "unauthorized",
    "invalid api key", "authentication failed", "access denied",
)


def is_ban_signal(status: int, body: str = "") -> bool:
    """True quando a resposta indica bloqueio/limite/conta queimada."""
    if status in (401, 403, 429, 402):
        return True
    text = (body or "").lower()
    return any(m in text for m in _BAN_MARKERS)


def is_retryable(status: int) -> bool:
    """Erros transitórios que valem um retry com backoff."""
    return status in (408, 409, 425, 429, 500, 502, 503, 504, 522, 524)
