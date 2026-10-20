#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Consciência de Ambiente
====================================

Dá à Cassandra conhecimento explícito de si mesma e do ambiente onde roda.
Sem isto, ela não sabe onde está instalada, quais skills tem disponíveis,
se pode executar shell, nem qual é o sistema operacional — e portanto não
consegue agir com autonomia real.

Fornece:
  * `Environment`   — snapshot do ambiente (SO, shell, privilégio, cwd,
                      pasta própria, skills, modelos, limites).
  * `environment_block()` — bloco de texto para o system prompt.
  * `SkillIndex`    — índice das skills com busca por nome/termo, para
                      carregar sob demanda em vez de despejar tudo.
  * `find_skill()`  — localiza uma skill pelo nome citado pelo usuário.

A pasta própria é descoberta a partir do arquivo, não de um caminho fixo,
para funcionar em qualquer instalação.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# DESCOBERTA DA INSTALAÇÃO
# ---------------------------------------------------------------------------

def install_root() -> Path:
    """Raiz da instalação da Cassandra (a pasta que contém agent.py)."""
    return Path(__file__).resolve().parent.parent


def skills_dirs() -> List[Path]:
    """
    Pastas onde skills são procuradas, em ordem de precedência.

    Inclui a pasta própria (cassandra-skill/) e qualquer caminho extra
    definido em CASSANDRA_SKILLOGY.
    """
    root = install_root()
    dirs: List[Path] = []

    extra = os.getenv("CASSANDRA_SKILLOGY", "").strip()
    if extra:
        dirs.append(Path(extra).expanduser())

    dirs.append(root / "cassandra-skill")
    dirs.append(root / "skills")

    # Remove duplicatas preservando a ordem.
    seen: set = set()
    out: List[Path] = []
    for d in dirs:
        rp = d.resolve() if d.exists() else d
        if rp not in seen:
            seen.add(rp)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# SNAPSHOT DO AMBIENTE
# ---------------------------------------------------------------------------

@dataclass
class Environment:
    """Retrato do ambiente de execução."""

    os_name: str = ""
    os_release: str = ""
    os_version: str = ""
    arch: str = ""
    python: str = ""
    shell: str = ""
    shell_kind: str = ""          # "bash" | "powershell" | "cmd"
    user: str = ""
    privilege: str = ""           # "ROOT" | "USER"
    cwd: str = ""
    install_dir: str = ""
    skills_dir: str = ""
    allow_shell: bool = False
    skill_count: int = 0
    soul_loaded: bool = False
    soul_path: str = ""
    model: str = ""
    provider: str = ""

    def is_windows(self) -> bool:
        return os.name == "nt" or "windows" in self.os_name.lower()

    def shell_examples(self) -> List[str]:
        """Exemplos de comando válidos para o shell detectado."""
        if self.is_windows():
            if self.shell_kind == "powershell":
                return [
                    "Get-ChildItem -Force",
                    "Get-Content arquivo.txt",
                    "Select-String -Path *.log -Pattern erro",
                    "Get-Process | Sort-Object CPU -Descending | Select -First 5",
                    "Test-NetConnection -ComputerName host -Port 443",
                ]
            return [
                "dir /a",
                "type arquivo.txt",
                "findstr /i erro *.log",
                "tasklist",
                "netstat -ano",
            ]
        return [
            "ls -la",
            "cat arquivo.txt",
            "grep -ri erro .",
            "ps aux --sort=-%cpu | head -5",
            "ss -tlnp",
        ]


def _detect_shell() -> Tuple[str, str]:
    """Detecta o shell e seu tipo. Devolve (caminho, tipo)."""
    if os.name == "nt":
        ps = shutil.which("pwsh") or shutil.which("powershell")
        if ps:
            return ps, "powershell"
        return os.getenv("COMSPEC", "cmd.exe"), "cmd"
    sh = os.getenv("SHELL") or shutil.which("bash") or "/bin/sh"
    kind = "bash" if "bash" in sh else "sh"
    return sh, kind


def _privilege() -> str:
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return "ROOT"
    except OSError:
        pass
    return "USER"


def _find_soul() -> Tuple[bool, str]:
    """Localiza o SOUL.md na instalação."""
    for d in skills_dirs():
        if not d.exists():
            continue
        candidate = d / "SOUL.md"
        if candidate.is_file():
            return True, str(candidate)
        if d.is_dir():
            for sub in d.rglob("SOUL.md"):
                return True, str(sub)
    return False, ""


def snapshot(
    allow_shell: bool = False,
    model: str = "",
    provider: str = "",
) -> Environment:
    """Monta o retrato do ambiente atual."""
    shell_path, shell_kind = _detect_shell()
    soul_ok, soul_path = _find_soul()
    dirs = skills_dirs()

    env = Environment(
        os_name=platform.system(),
        os_release=platform.release(),
        os_version=platform.version(),
        arch=platform.machine(),
        python=platform.python_version(),
        shell=shell_path,
        shell_kind=shell_kind,
        user=os.getenv("USER") or os.getenv("USERNAME") or "desconhecido",
        privilege=_privilege(),
        cwd=os.getcwd(),
        install_dir=str(install_root()),
        skills_dir=str(dirs[0]) if dirs else "",
        allow_shell=allow_shell,
        skill_count=count_skills(),
        soul_loaded=soul_ok,
        soul_path=soul_path,
        model=model,
        provider=provider,
    )
    return env


def count_skills() -> int:
    """Conta as skills disponíveis (arquivos SKILL.md / *.md)."""
    total = 0
    seen: set = set()
    for d in skills_dirs():
        if not d.is_dir():
            continue
        for f in d.rglob("SKILL.md"):
            if f not in seen:
                seen.add(f)
                total += 1
        if total == 0:
            for f in d.rglob("*.md"):
                if f.name.upper() == "SOUL.MD":
                    continue
                if f not in seen:
                    seen.add(f)
                    total += 1
    return total


# ---------------------------------------------------------------------------
# BLOCO DE AMBIENTE PARA O PROMPT
# ---------------------------------------------------------------------------

def environment_block(env: Environment) -> str:
    """
    Gera o bloco que informa a Cassandra sobre si mesma e o ambiente.

    Este texto vai no system prompt e é o que faz a Cassandra saber que é
    autônoma, onde está instalada, e como usar o shell corretamente.
    """
    lines: List[str] = []
    lines.append("# 🖥️ CONSCIÊNCIA DE AMBIENTE")
    lines.append("")
    lines.append("Você sabe onde está e o que pode fazer. Use isto.")
    lines.append("")

    lines.append("## Identidade da instalação")
    lines.append(f"- **Pasta própria (instalação):** `{env.install_dir}`")
    lines.append(f"- **Pasta de skills:** `{env.skills_dir}`")
    lines.append(f"- **Skills disponíveis:** {env.skill_count}")
    if env.soul_loaded:
        lines.append(f"- **SOUL.md carregado de:** `{env.soul_path}`")
    else:
        lines.append("- **SOUL.md:** não encontrado (usando persona padrão)")
    lines.append("")

    lines.append("## Sistema")
    lines.append(f"- **SO:** {env.os_name} {env.os_release} ({env.arch})")
    lines.append(f"- **Shell:** `{env.shell}` ({env.shell_kind})")
    lines.append(f"- **Usuário:** `{env.user}` — privilégio **{env.privilege}**")
    lines.append(f"- **Diretório de trabalho:** `{env.cwd}`")
    lines.append(f"- **Python:** {env.python}")
    if env.model:
        lines.append(f"- **Modelo ativo:** `{env.model}`")
    if env.provider:
        lines.append(f"- **Provedor:** {env.provider}")
    lines.append("")

    # --- Autonomia ---
    lines.append("## ⚡ AUTONOMIA E EXECUÇÃO")
    lines.append("")
    if env.allow_shell:
        lines.append(
            "**MODO AUTÔNOMO ATIVO** (`--allow-shell` foi passado pelo operador)."
        )
        lines.append("")
        lines.append(
            "Você tem acesso real à máquina. Blocos de código com a linguagem "
            "`bash` (Linux/macOS) ou `powershell`/`cmd` (Windows) que você "
            "retornar **serão executados automaticamente** e a saída voltará "
            "para você continuar."
        )
        lines.append("")
        lines.append("Diretrizes de autonomia:")
        lines.append(
            "- **AJA, não peça.** Se você pode fazer via shell, FAÇA. Nunca "
            "diga ao operador para rodar algo que você mesma pode executar."
        )
        lines.append(
            "- **Encadeie comandos.** `cd` isolado não persiste entre blocos. "
            "Use `cd pasta && comando` ou caminhos absolutos."
        )
        lines.append(
            "- **Itere sozinha.** Execute, leia a saída, corrija erros e "
            "continue até concluir o objetivo. Não pare no primeiro obstáculo."
        )
        lines.append(
            "- **Avise sobre processos longos.** Se for rodar algo demorado "
            "(nmap, varredura, download grande), diga que está iniciando e "
            "peça para aguardar."
        )
        lines.append(
            "- **Você é a operadora da máquina.** Trate-a como seu ambiente "
            "de trabalho, com as permissões reais indicadas acima."
        )
    else:
        lines.append(
            "**MODO RESTRITO** (`--allow-shell` NÃO foi passado)."
        )
        lines.append("")
        lines.append(
            "Você pode **analisar, planejar e escrever** comandos, mas eles "
            "**não serão executados automaticamente**. Apresente os comandos "
            "como texto para o operador copiar e rodar."
        )
        lines.append("")
        lines.append(
            "Se a tarefa exigir execução real, informe ao operador que ele "
            "precisa reiniciar com `--allow-shell` para você agir sozinha."
        )
    lines.append("")

    # --- Shell correto ---
    lines.append("## Sintaxe do shell neste ambiente")
    lines.append("")
    if env.is_windows():
        lang = "powershell" if env.shell_kind == "powershell" else "cmd"
        lines.append(f"Use blocos ```{lang} com comandos Windows válidos:")
    else:
        lines.append("Use blocos ```bash com comandos POSIX válidos:")
    lines.append("")
    for ex in env.shell_examples():
        lines.append(f"- `{ex}`")
    lines.append("")
    lines.append(
        "**IMPORTANTE:** só blocos com a tag acima (ou equivalente do SO) são "
        "executados. Um comando escrito fora de um bloco marcado NÃO roda — "
        "ele fica apenas como texto para o operador copiar."
    )
    lines.append("")

    # --- Ferramentas externas ---
    lines.append("## 🔧 Ferramentas externas (download sob demanda)")
    lines.append("")
    lines.append(
        "Se a tarefa exigir uma ferramenta que não está instalada, você pode "
        "pedir o download. **Não** invente comandos de instalação aleatórios — "
        "use o bloco abaixo e o sistema cuida das validações de segurança."
    )
    lines.append("")
    lines.append("```tool")
    lines.append('{"name": "nmap", "source": "apt", "reason": "varredura de portas"}')
    lines.append("```")
    lines.append("")
    lines.append("Fontes disponíveis:")
    lines.append("")
    lines.append("| `source` | Uso | Campos obrigatórios |")
    lines.append("|---|---|---|")
    lines.append("| `apt` | pacote do sistema (Debian/Ubuntu) | `name` |")
    lines.append("| `pypi` | pacote Python no venv | `name` |")
    lines.append("| `npm` | pacote Node local | `name` |")
    lines.append("| `go` | binário Go | `name` (formato `modulo@versao`) |")
    lines.append("| `github` | asset de release | `repo`, `asset` |")
    lines.append("| `url` | URL direta | `url`, `sha256` |")
    lines.append("")
    lines.append(
        "**Controles de segurança aplicados automaticamente:** allowlist de "
        "origem (só GitHub, PyPI, npm, apt e projetos oficiais), sandbox em "
        "`tools/`, limite de tamanho, verificação de checksum quando fornecida, "
        "e registro de auditoria. O download **nunca executa** nada sozinho."
    )
    lines.append("")
    if env.allow_shell:
        lines.append(
            "**Modo autônomo:** o download será executado automaticamente e "
            "você receberá o resultado para continuar."
        )
    else:
        lines.append(
            "**Modo restrito:** o sistema devolverá o comando para o operador "
            "rodar. Continue a tarefa assumindo que a ferramenta estará "
            "disponível, ou proponha uma alternativa."
        )
    lines.append("")

    # --- Skills sob demanda ---
    lines.append("## 🧠 Skills (conhecimento próprio)")
    lines.append("")
    lines.append(
        f"Você tem **{env.skill_count} skills** em `{env.skills_dir}`. "
        "Elas contêm metodologias, técnicas e procedimentos."
    )
    lines.append("")
    lines.append(
        "**Você pode pedir uma skill específica.** Se o operador citar uma "
        "skill pelo nome, ou se você precisar de um procedimento que não tem "
        "em contexto, escreva um bloco assim (substitua pelo nome real):"
    )
    lines.append("")
    lines.append("```skill")
    lines.append("<nome-da-skill-aqui>")
    lines.append("```")
    lines.append("")
    lines.append(
        "O sistema carrega o conteúdo da skill e devolve para você continuar. "
        "Você pode pedir várias em sequência."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ÍNDICE DE SKILLS (CARREGAMENTO SOB DEMANDA)
# ---------------------------------------------------------------------------

@dataclass
class SkillEntry:
    name: str
    path: str
    description: str = ""
    size: int = 0


class SkillIndex:
    """
    Índice das skills disponíveis, para busca e carregamento sob demanda.

    Evita despejar 384 skills no contexto (que estouraria a janela).
    Em vez disso, indexa nome + descrição e carrega o conteúdo completo
    apenas quando pedido.
    """

    def __init__(self, dirs: Optional[List[Path]] = None):
        self.dirs = dirs or skills_dirs()
        self.entries: List[SkillEntry] = []
        self._by_name: Dict[str, SkillEntry] = {}
        self._build()

    def _build(self) -> None:
        seen: set = set()
        for d in self.dirs:
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("SKILL.md")):
                if f in seen:
                    continue
                seen.add(f)
                entry = self._make_entry(f, d)
                if entry:
                    self.entries.append(entry)
                    self._by_name[entry.name.lower()] = entry

    def _make_entry(self, path: Path, root: Path) -> Optional[SkillEntry]:
        try:
            rel = path.parent.relative_to(root)
            name = str(rel).replace(os.sep, "/") or path.parent.name
        except ValueError:
            name = path.parent.name

        desc = ""
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:1200]
            # Tenta extrair a description do frontmatter YAML.
            if head.startswith("---"):
                end = head.find("---", 3)
                if end > 0:
                    fm = head[3:end]
                    for line in fm.splitlines():
                        if line.strip().lower().startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip("\"'")
                            break
            if not desc:
                # Primeira linha não-vazia após o frontmatter.
                body = head[end + 3:] if head.startswith("---") and end > 0 else head
                for line in body.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        desc = line[:160]
                        break
        except OSError:
            pass

        return SkillEntry(
            name=name,
            path=str(path),
            description=desc,
            size=path.stat().st_size if path.exists() else 0,
        )

    def names(self) -> List[str]:
        return [e.name for e in self.entries]

    def find(self, query: str) -> List[SkillEntry]:
        """
        Busca skills por nome ou descrição. Devolve as mais relevantes.

        Aceita correspondência exata de nome, parcial, ou por termos.
        """
        q = (query or "").strip().lower()
        if not q:
            return []

        # 1. Nome exato.
        if q in self._by_name:
            return [self._by_name[q]]

        # 2. Nome parcial.
        partial = [e for e in self.entries if q in e.name.lower()]

        # 3. Termos na descrição.
        terms = [t for t in q.replace("/", " ").replace("-", " ").split() if len(t) > 2]
        scored: List[Tuple[int, SkillEntry]] = []
        for e in self.entries:
            if e in partial:
                continue
            hay = (e.name + " " + e.description).lower()
            score = sum(1 for t in terms if t in hay)
            if score:
                scored.append((score, e))

        scored.sort(key=lambda x: (-x[0], x[1].name))
        out = partial + [e for _, e in scored]
        return out[:5]

    def load(self, query: str, max_chars: int = 40000) -> Tuple[str, List[str]]:
        """
        Carrega o conteúdo de uma skill. Devolve (conteúdo, nomes_carregados).
        """
        matches = self.find(query)
        if not matches:
            return "", []

        parts: List[str] = []
        loaded: List[str] = []
        total = 0
        for e in matches:
            try:
                content = Path(e.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if total + len(content) > max_chars:
                parts.append(f"⚠️ Skill `{e.name}` omitida (limite de tamanho).")
                break
            parts.append(f"# SKILL: {e.name}\nFonte: `{e.path}`\n\n{content}")
            loaded.append(e.name)
            total += len(content)
        return "\n\n---\n\n".join(parts), loaded

    def catalog(self, limit: int = 200) -> str:
        """Lista compacta de nomes para o prompt (sem conteúdo)."""
        names = self.names()
        if not names:
            return "(nenhuma skill encontrada)"
        shown = names[:limit]
        out = ", ".join(shown)
        if len(names) > limit:
            out += f" ... (+{len(names) - limit})"
        return out


def roundtrip_ok() -> bool:
    """Auto-teste: ambiente e índice funcionam."""
    env = snapshot()
    ok_env = bool(env.os_name and env.install_dir and env.shell)
    block = environment_block(env)
    ok_block = "CONSCIÊNCIA DE AMBIENTE" in block and env.install_dir in block
    idx = SkillIndex()
    ok_idx = len(idx.entries) > 0
    return ok_env and ok_block and ok_idx


if __name__ == "__main__":
    print(f"[env] roundtrip: {'OK' if roundtrip_ok() else 'FALHOU'}")
    print()
    env = snapshot(allow_shell=True, model="teste", provider="NVIDIA")
    print(environment_block(env))
    print()
    idx = SkillIndex()
    print(f"[env] {len(idx.entries)} skills indexadas")
    print(f"[env] primeiras 10: {', '.join(idx.names()[:10])}")
    print()
    for q in ["malicious-virtual-machine", "redteam", "osint"]:
        found = idx.find(q)
        print(f"[env] busca '{q}' -> {[e.name for e in found]}")
