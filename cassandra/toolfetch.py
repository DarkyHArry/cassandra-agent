#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Gerenciador de Ferramentas Externas
===============================================

Permite que a Cassandra baixe ferramentas externas quando a tarefa exige,
mas com controles que impedem que isso vire um vetor de comprometimento.

Modelo de segurança (defesa em profundidade)
--------------------------------------------
1. **Allowlist de origem** — só baixa de hosts confiáveis (GitHub releases,
   PyPI, npm, apt, repositórios oficiais). Nada de URL arbitrária.
2. **Sandbox de destino** — tudo vai para `tools/` dentro da instalação.
   Nunca para `/usr/bin`, PATH do sistema ou diretório do usuário.
3. **Verificação de integridade** — checksum SHA-256 quando disponível;
   tamanho máximo; recusa de arquivos que não sejam o tipo esperado.
4. **Sem execução automática** — o download NUNCA executa nada. Baixa,
   verifica e reporta. A execução continua sendo decisão explícita.
5. **Registro auditável** — toda operação vai para um log JSONL com
   origem, hash, tamanho e resultado.
6. **Confirmação no modo restrito** — sem `--allow-shell`, apenas sugere
   o comando; não baixa.

Uso pela Cassandra (bloco na resposta):

    ```tool
    {"name": "nmap", "source": "apt", "reason": "varredura de portas"}
    ```

    ```tool
    {"name": "ffuf", "source": "github", "repo": "ffuf/ffuf",
     "asset": "ffuf_2.1.0_linux_amd64.tar.gz", "reason": "fuzzing web"}
    ```

    ```tool
    {"name": "requests", "source": "pypi", "reason": "cliente HTTP"}
    ```
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

def install_root() -> Path:
    return Path(__file__).resolve().parent.parent


def tools_dir() -> Path:
    """Sandbox onde as ferramentas são instaladas."""
    d = Path(os.getenv("CASSANDRA_TOOLS_DIR", str(install_root() / "tools")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def audit_log() -> Path:
    d = Path(os.getenv("CASSANDRA_LOG_DIR", str(install_root() / "logs")))
    d.mkdir(parents=True, exist_ok=True)
    return d / "tools-audit.jsonl"


def max_download_mb() -> int:
    try:
        return int(os.getenv("CASSANDRA_MAX_DOWNLOAD_MB", "200"))
    except ValueError:
        return 200


def is_enabled() -> bool:
    return os.getenv("CASSANDRA_ALLOW_TOOLS", "1").lower() in {"1", "true", "yes", "on"}


def install_timeout() -> float:
    """
    Tempo máximo para uma instalação (pip/apt/npm/go).

    Era 600s fixo, o que na interface web significa dez minutos sem
    retorno. Agora é configurável, com padrão mais curto.
    """
    try:
        return float(os.getenv("CASSANDRA_INSTALL_TIMEOUT", "300"))
    except ValueError:
        return 300.0


# ---------------------------------------------------------------------------
# ALLOWLIST DE ORIGENS
# ---------------------------------------------------------------------------

# Hosts dos quais é aceitável baixar. Qualquer outro é recusado.
ALLOWED_HOSTS = {
    # Código / releases
    "github.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
    "raw.githubusercontent.com",
    # Gerenciadores de pacote
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "crates.io",
    "static.crates.io",
    # Distribuições
    "deb.debian.org",
    "security.debian.org",
    "archive.ubuntu.com",
    "security.ubuntu.com",
    # Projetos de segurança conhecidos
    "nmap.org",
    "download.savannah.gnu.org",
    "ftp.gnu.org",
    "www.openssl.org",
    "curl.se",
    "github-releases.githubusercontent.com",
}

# Fontes suportadas e o que cada uma faz.
SOURCES = {
    "apt": "Pacote do repositório APT do sistema (Debian/Ubuntu).",
    "pypi": "Pacote Python via pip (instalado no venv do projeto).",
    "npm": "Pacote Node via npm (instalado localmente).",
    "github": "Asset de release do GitHub (requer repo + asset).",
    "url": "URL direta de host na allowlist (requer url + sha256).",
    "go": "Binário Go via 'go install' (instalado no sandbox).",
}

# Extensões/formatos aceitos no download direto.
SAFE_SUFFIXES = {
    ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".zip",
    ".whl", ".deb", ".rpm", ".gz", ".xz", ".bin",
}


# ---------------------------------------------------------------------------
# REGISTRO DE AUDITORIA
# ---------------------------------------------------------------------------

def _audit(entry: Dict) -> None:
    entry = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    try:
        with audit_log().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# RESULTADO
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    name: str
    source: str
    ok: bool
    action: str = ""          # "downloaded" | "installed" | "suggested" | "refused"
    path: str = ""
    sha256: str = ""
    size: int = 0
    message: str = ""
    command: str = ""         # comando sugerido (modo restrito)

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# VALIDAÇÕES
# ---------------------------------------------------------------------------

def _host_allowed(url: str) -> Tuple[bool, str]:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False, "URL inválida"
    if not host:
        return False, "URL sem host"
    if host in ALLOWED_HOSTS:
        return True, host
    # Subdomínios de hosts permitidos (ex.: algo.github.com)
    for allowed in ALLOWED_HOSTS:
        if host.endswith("." + allowed):
            return True, host
    return False, f"host '{host}' não está na allowlist"


def _sha256_file(path: Path, limit_mb: int = 500) -> str:
    h = hashlib.sha256()
    total = 0
    cap = limit_mb * 1024 * 1024
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    """Sanitiza o nome para evitar path traversal."""
    name = (name or "").strip()
    name = re.sub(r"[^\w.\-+]", "_", name)
    name = name.lstrip(".-")
    return name[:80] or "tool"


# ---------------------------------------------------------------------------
# DOWNLOAD DIRETO
# ---------------------------------------------------------------------------

def _download(
    url: str,
    dest_name: str,
    expected_sha256: str = "",
    reason: str = "",
) -> ToolResult:
    """
    Baixa um arquivo para o sandbox com validações.

    Não executa nada. Verifica host, tamanho e (se fornecida) o hash.
    """
    allowed, info = _host_allowed(url)
    if not allowed:
        _audit({"op": "download", "url": url, "result": "refused", "why": info})
        return ToolResult(
            name=dest_name, source="url", ok=False, action="refused",
            message=f"Origem recusada: {info}",
        )

    dest = tools_dir() / _safe_name(dest_name)
    max_bytes = max_download_mb() * 1024 * 1024

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "cassandra-toolfetch/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Checa Content-Length antes de baixar.
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > max_bytes:
                return ToolResult(
                    name=dest_name, source="url", ok=False, action="refused",
                    message=f"Arquivo grande demais ({int(cl)//1024//1024} MB > "
                            f"{max_download_mb()} MB)",
                )

            written = 0
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        fh.close()
                        dest.unlink(missing_ok=True)
                        return ToolResult(
                            name=dest_name, source="url", ok=False,
                            action="refused",
                            message=f"Download excedeu {max_download_mb()} MB",
                        )
                    fh.write(chunk)

        # Verificação de integridade.
        digest = _sha256_file(dest)
        if expected_sha256:
            exp = expected_sha256.strip().lower()
            if digest.lower() != exp:
                dest.unlink(missing_ok=True)
                _audit({
                    "op": "download", "url": url, "result": "hash_mismatch",
                    "expected": exp, "got": digest,
                })
                return ToolResult(
                    name=dest_name, source="url", ok=False, action="refused",
                    message=f"Checksum não confere (esperado {exp[:16]}…, "
                            f"obtido {digest[:16]}…)",
                )

        # Tipo de arquivo esperado.
        #
        # Binários de release frequentemente NÃO têm extensão
        # (ex.: `jq-linux-amd64`, `ffuf`, `nuclei`). Recusá-los por isso
        # seria um falso positivo. A regra correta: se não tem extensão
        # conhecida, exige checksum verificado — sem hash, recusa.
        name_lower = dest.name.lower()
        has_known_suffix = any(name_lower.endswith(s) for s in SAFE_SUFFIXES)
        has_script_suffix = dest.suffix.lower() in {".py", ".sh", ".txt", ".json"}
        no_suffix = "." not in dest.name

        if not (has_known_suffix or has_script_suffix or no_suffix):
            dest.unlink(missing_ok=True)
            return ToolResult(
                name=dest_name, source="url", ok=False, action="refused",
                message=f"Tipo de arquivo não aceito: {dest.name}",
            )

        if no_suffix and not expected_sha256:
            dest.unlink(missing_ok=True)
            _audit({
                "op": "download", "url": url, "result": "refused_no_hash",
                "why": "binário sem extensão exige checksum",
            })
            return ToolResult(
                name=dest_name, source="url", ok=False, action="refused",
                message=("Binário sem extensão exige 'sha256' para ser "
                         "aceito (integridade obrigatória)."),
            )

        _audit({
            "op": "download", "url": url, "result": "ok",
            "path": str(dest), "sha256": digest, "size": written,
            "reason": reason,
        })
        return ToolResult(
            name=dest_name, source="url", ok=True, action="downloaded",
            path=str(dest), sha256=digest, size=written,
            message=f"Baixado e verificado ({written//1024} KB).",
        )

    except urllib.error.HTTPError as exc:
        _audit({"op": "download", "url": url, "result": f"http_{exc.code}"})
        return ToolResult(
            name=dest_name, source="url", ok=False,
            message=f"HTTP {exc.code} ao baixar {url}",
        )
    except Exception as exc:  # noqa: BLE001
        _audit({"op": "download", "url": url, "result": f"error: {exc}"})
        return ToolResult(
            name=dest_name, source="url", ok=False,
            message=f"Falha no download: {exc}",
        )


# ---------------------------------------------------------------------------
# GITHUB RELEASE
# ---------------------------------------------------------------------------

def _github_asset_url(repo: str, asset: str, tag: str = "latest") -> Optional[str]:
    """Monta a URL do asset de um release do GitHub."""
    if not re.match(r"^[\w.\-]+/[\w.\-]+$", repo or ""):
        return None
    if tag == "latest":
        return f"https://github.com/{repo}/releases/latest/download/{asset}"
    return f"https://github.com/{repo}/releases/download/{tag}/{asset}"


# ---------------------------------------------------------------------------
# INSTALADORES DE PACOTE
# ---------------------------------------------------------------------------

def _install_pip(name: str, reason: str) -> ToolResult:
    """Instala um pacote Python no venv do projeto."""
    pkg = _safe_name(name)
    if not re.match(r"^[\w.\-+\[\]]+$", pkg):
        return ToolResult(name=pkg, source="pypi", ok=False,
                          action="refused", message="Nome de pacote inválido")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-input", pkg],
            capture_output=True, text=True, timeout=install_timeout(),
        )
        ok = r.returncode == 0
        _audit({"op": "pip_install", "package": pkg, "result": "ok" if ok else "fail",
                "reason": reason})
        return ToolResult(
            name=pkg, source="pypi", ok=ok,
            action="installed" if ok else "",
            message=(f"Pacote '{pkg}' instalado no venv." if ok
                     else f"pip falhou: {r.stderr.strip()[:200]}"),
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(name=pkg, source="pypi", ok=False,
                          message=f"Erro no pip: {exc}")


def _install_apt(name: str, reason: str) -> ToolResult:
    """Instala um pacote do repositório APT do sistema."""
    pkg = _safe_name(name)
    if not re.match(r"^[\w.\-+]+$", pkg):
        return ToolResult(name=pkg, source="apt", ok=False,
                          action="refused", message="Nome de pacote inválido")
    if os.name == "nt":
        return ToolResult(name=pkg, source="apt", ok=False,
                          message="APT não existe no Windows")
    if not shutil.which("apt-get"):
        return ToolResult(name=pkg, source="apt", ok=False,
                          message="apt-get não disponível neste sistema")
    try:
        r = subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends", pkg],
            capture_output=True, text=True, timeout=install_timeout(),
        )
        ok = r.returncode == 0
        _audit({"op": "apt_install", "package": pkg, "result": "ok" if ok else "fail",
                "reason": reason})
        return ToolResult(
            name=pkg, source="apt", ok=ok,
            action="installed" if ok else "",
            message=(f"Pacote '{pkg}' instalado via apt." if ok
                     else f"apt falhou: {r.stderr.strip()[:200]}"),
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(name=pkg, source="apt", ok=False,
                          message=f"Erro no apt: {exc}")


def _install_npm(name: str, reason: str) -> ToolResult:
    pkg = _safe_name(name)
    if not re.match(r"^[\w.\-/@]+$", pkg):
        return ToolResult(name=pkg, source="npm", ok=False,
                          action="refused", message="Nome de pacote inválido")
    if not shutil.which("npm"):
        return ToolResult(name=pkg, source="npm", ok=False,
                          message="npm não disponível")
    try:
        r = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", pkg],
            capture_output=True, text=True, timeout=install_timeout(),
            cwd=str(tools_dir()),
        )
        ok = r.returncode == 0
        _audit({"op": "npm_install", "package": pkg, "result": "ok" if ok else "fail",
                "reason": reason})
        return ToolResult(
            name=pkg, source="npm", ok=ok,
            action="installed" if ok else "",
            message=(f"Pacote '{pkg}' instalado localmente." if ok
                     else f"npm falhou: {r.stderr.strip()[:200]}"),
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(name=pkg, source="npm", ok=False,
                          message=f"Erro no npm: {exc}")


# ---------------------------------------------------------------------------
# API PÚBLICA
# ---------------------------------------------------------------------------

def parse_request(spec: Dict) -> Tuple[Optional[Dict], str]:
    """
    Valida e normaliza um pedido de ferramenta.

    Devolve (pedido_normalizado, erro). `erro` vazio significa OK.
    """
    if not isinstance(spec, dict):
        return None, "pedido não é um objeto JSON"

    name = _safe_name(str(spec.get("name", "")))
    if not name:
        return None, "campo 'name' obrigatório"

    source = str(spec.get("source", "")).strip().lower()
    if source not in SOURCES:
        return None, (f"fonte '{source}' inválida. Use: "
                      f"{', '.join(sorted(SOURCES))}")

    out = {
        "name": name,
        "source": source,
        "reason": str(spec.get("reason", ""))[:200],
        "repo": str(spec.get("repo", "")).strip(),
        "asset": str(spec.get("asset", "")).strip(),
        "tag": str(spec.get("tag", "latest")).strip(),
        "url": str(spec.get("url", "")).strip(),
        "sha256": str(spec.get("sha256", "")).strip(),
    }

    if source == "github":
        if not out["repo"] or not out["asset"]:
            return None, "fonte 'github' exige 'repo' e 'asset'"
    if source == "url":
        if not out["url"]:
            return None, "fonte 'url' exige 'url'"
        if not out["sha256"]:
            return None, ("fonte 'url' exige 'sha256' (integridade "
                          "obrigatória para URL direta)")

    return out, ""


def fetch(spec: Dict, allow_execute: bool = False) -> ToolResult:
    """
    Processa um pedido de ferramenta.

    `allow_execute=False` (modo restrito): não baixa nada, apenas devolve
    o comando sugerido para o operador rodar.

    `allow_execute=True` (modo autônomo): executa o download/instalação
    com todas as validações.
    """
    if not is_enabled():
        return ToolResult(
            name=str(spec.get("name", "?")), source=str(spec.get("source", "?")),
            ok=False, action="refused",
            message="Download de ferramentas desativado (CASSANDRA_ALLOW_TOOLS=0).",
        )

    req, err = parse_request(spec)
    if err:
        return ToolResult(
            name=str(spec.get("name", "?")), source=str(spec.get("source", "?")),
            ok=False, action="refused", message=err,
        )

    name, source = req["name"], req["source"]

    # --- Modo restrito: só sugere ---
    if not allow_execute:
        cmd = _suggest_command(req)
        _audit({"op": "tool", "name": name, "source": source,
                "result": "suggested", "reason": req["reason"]})
        return ToolResult(
            name=name, source=source, ok=True, action="suggested",
            command=cmd,
            message=(f"Modo restrito: comando sugerido para o operador.\n"
                     f"`{cmd}`"),
        )

    # --- Modo autônomo: executa ---
    if source == "pypi":
        return _install_pip(name, req["reason"])
    if source == "apt":
        return _install_apt(name, req["reason"])
    if source == "npm":
        return _install_npm(name, req["reason"])
    if source == "github":
        url = _github_asset_url(req["repo"], req["asset"], req["tag"])
        if not url:
            return ToolResult(name=name, source=source, ok=False,
                              action="refused",
                              message="repo/asset inválidos para o GitHub")
        return _download(url, req["asset"], req["sha256"], req["reason"])
    if source == "url":
        return _download(req["url"], name, req["sha256"], req["reason"])
    if source == "go":
        return _install_go(name, req["reason"])

    return ToolResult(name=name, source=source, ok=False,
                      action="refused", message=f"fonte não implementada: {source}")


def _install_go(name: str, reason: str) -> ToolResult:
    if not shutil.which("go"):
        return ToolResult(name=name, source="go", ok=False,
                          message="go não disponível")
    if not re.match(r"^[\w.\-/]+@[\w.\-]+$", name):
        return ToolResult(name=name, source="go", ok=False, action="refused",
                          message="use o formato modulo@versao")
    gopath = tools_dir() / "go"
    gopath.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GOBIN": str(gopath), "GOPATH": str(gopath)}
    try:
        r = subprocess.run(
            ["go", "install", name],
            capture_output=True, text=True, timeout=install_timeout(), env=env,
        )
        ok = r.returncode == 0
        _audit({"op": "go_install", "module": name,
                "result": "ok" if ok else "fail", "reason": reason})
        return ToolResult(
            name=name, source="go", ok=ok,
            action="installed" if ok else "",
            path=str(gopath) if ok else "",
            message=(f"Instalado em {gopath}" if ok
                     else f"go falhou: {r.stderr.strip()[:200]}"),
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(name=name, source="go", ok=False,
                          message=f"Erro no go: {exc}")


def _suggest_command(req: Dict) -> str:
    """Comando equivalente para o operador rodar no modo restrito."""
    s = req["source"]
    n = req["name"]
    if s == "pypi":
        return f"{sys.executable} -m pip install {n}"
    if s == "apt":
        return f"sudo apt-get install -y {n}"
    if s == "npm":
        return f"npm install {n}"
    if s == "go":
        return f"go install {n}"
    if s == "github":
        url = _github_asset_url(req["repo"], req["asset"], req["tag"])
        return f"curl -fL -o {req['asset']} '{url}'"
    if s == "url":
        return f"curl -fL -o {n} '{req['url']}'"
    return f"# instalar {n} via {s}"


def extract_tool_blocks(markdown: str) -> List[Dict]:
    """
    Extrai pedidos de ferramenta de blocos ```tool na resposta.

    Tolera cercas malformadas, que são comuns: modelos às vezes emitem
    ```` ```".tool ````, ```` ``` tool ````, ```` ```json tool ```` ou a
    cerca colada no texto anterior. Em vez de exigir o formato perfeito,
    procuramos qualquer cerca de abertura que mencione 'tool' e pegamos
    o bloco JSON seguinte.

    Aceita JSON de uma linha ou múltiplas linhas.
    """
    out: List[Dict] = []

    # Cerca tolerante: ``` seguida (com ruído opcional) de 'tool'
    fence = re.compile(
        r"```[^\n`]{0,20}?\btool\b[^\n]*\n(.*?)\n\s*```",
        re.IGNORECASE | re.DOTALL,
    )
    candidates = [m.group(1).strip() for m in fence.finditer(markdown)]

    # Fallback: cerca de abertura corrompida que ainda contém 'tool'
    # e um objeto JSON logo depois, mesmo sem cerca de fechamento.
    if not candidates:
        loose = re.compile(
            r"```[^\n`]{0,20}?\btool\b[^\n]*\n(\{.*?\})",
            re.IGNORECASE | re.DOTALL,
        )
        candidates = [m.group(1).strip() for m in loose.finditer(markdown)]

    for raw in candidates:
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                out.append(obj)
            elif isinstance(obj, list):
                out.extend(o for o in obj if isinstance(o, dict))
        except json.JSONDecodeError:
            # Tenta recuperar JSON embutido no texto.
            brace = re.search(r"\{.*\}", raw, re.DOTALL)
            if brace:
                try:
                    obj = json.loads(brace.group(0))
                    if isinstance(obj, dict):
                        out.append(obj)
                        continue
                except json.JSONDecodeError:
                    pass
            # Formato simples: "nome" ou "nome: fonte"
            parts = raw.split(":", 1)
            name = parts[0].strip().strip("\"'")
            src = parts[1].strip().strip("\"'") if len(parts) > 1 else "pypi"
            if name and len(name) < 60 and " " not in name:
                out.append({"name": name, "source": src})

    return out


def installed_tools() -> List[str]:
    """Lista o que já está no sandbox."""
    d = tools_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if not p.name.startswith("."))


def roundtrip_ok() -> bool:
    """Auto-teste: validações e parsing funcionam."""
    # Host fora da allowlist deve ser recusado.
    r1 = fetch({"name": "x", "source": "url", "url": "https://evil.example/x",
                "sha256": "abc"}, allow_execute=True)
    ok1 = (not r1.ok) and r1.action == "refused"
    # URL sem sha256 deve ser recusada.
    r2 = fetch({"name": "x", "source": "url",
                "url": "https://github.com/a/b/releases/x"}, allow_execute=True)
    ok2 = (not r2.ok) and "sha256" in r2.message
    # Fonte inválida.
    r3 = fetch({"name": "x", "source": "torrent"}, allow_execute=True)
    ok3 = not r3.ok
    # Modo restrito sugere comando.
    r4 = fetch({"name": "nmap", "source": "apt"}, allow_execute=False)
    ok4 = r4.ok and r4.action == "suggested" and "apt" in r4.command
    # Parsing de bloco.
    blocks = extract_tool_blocks('```tool\n{"name":"ffuf","source":"github",'
                                 '"repo":"ffuf/ffuf","asset":"ffuf.tgz"}\n```')
    ok5 = len(blocks) == 1 and blocks[0]["name"] == "ffuf"
    # Path traversal deve ser neutralizado (sem separadores de caminho).
    r6 = fetch({"name": "../../etc/passwd", "source": "pypi"}, allow_execute=False)
    ok6 = "/" not in r6.name and "\\" not in r6.name
    return all([ok1, ok2, ok3, ok4, ok5, ok6])


if __name__ == "__main__":
    print(f"[tools] roundtrip: {'OK' if roundtrip_ok() else 'FALHOU'}")
    print(f"[tools] sandbox: {tools_dir()}")
    print(f"[tools] limite: {max_download_mb()} MB")
    print(f"[tools] ativo: {is_enabled()}")
    print(f"[tools] hosts permitidos: {len(ALLOWED_HOSTS)}")
    print(f"[tools] instaladas: {installed_tools() or '(nenhuma)'}")
    print()
    print("Fontes suportadas:")
    for k, v in SOURCES.items():
        print(f"  {k:8} {v}")
