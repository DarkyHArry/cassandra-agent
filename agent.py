#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cassandra CLI
-------------
Cliente de terminal para a API da Cassandra.

Principais recursos:
- Tema vermelho no terminal.
- Saída estruturada em Markdown.
- Persona Cassandra consistente.
- Suporte opcional a uma Skillogy externa via arquivo.
- Instruções explícitas para Progressão Geométrica (PG).
- Animação de processamento enquanto a API responde.
- Streaming da API compatível com formato SSE/OpenAI-like.
- Execução de shell DESATIVADA por padrão.
  Use --allow-shell somente quando realmente quiser executar comandos
  retornados pela API livremente e sem confirmação.
"""

import argparse
import getpass
import json
import logging
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import shutil
import signal
from pathlib import Path
from typing import Dict, List, Optional

# === DEPENDÊNCIAS / AUTO-INSTALL ===
def _ensure_packages():
    required_packages = {
        "requests": "requests",
        "python-dotenv": "dotenv",
        "httpx": "httpx",
        "cryptography": "cryptography",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn"
    }
    missing = []
    for pkg, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
            
    if missing:
        print(f"[*] Instalando dependências necessárias da ferramenta: {', '.join(missing)}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages"] + missing)
            print("[+] Dependências instaladas com sucesso!")
            time.sleep(1)
            os.system('cls' if os.name == 'nt' else 'clear')
        except Exception as e:
            print(f"[-] Erro ao instalar pacotes: {e}")
            sys.exit(1)

_ensure_packages()

from dotenv import load_dotenv
load_dotenv()

import requests
HAS_REQUESTS = True

try:
    from cassandra.client import (
        AllProvidersExhausted as _AllProvidersExhausted,
        CassandraClient as _CassandraClient,
        ProviderError as _ProviderError,
        load_credentials as _load_credentials,
    )
    from cassandra.filter import ProviderBlocked as _ProviderBlocked
    from cassandra.providers import provider_catalog as _provider_catalog
    from cassandra.compact import (
        compact as _compact,
        needs_compaction as _needs_compaction,
    )
    from cassandra.environment import (
        SkillIndex as _SkillIndex,
        environment_block as _environment_block,
        snapshot as _env_snapshot,
    )
    from cassandra.toolfetch import (
        extract_tool_blocks as _extract_tool_blocks,
        fetch as _tool_fetch,
        installed_tools as _installed_tools,
    )
except ImportError:  # pragma: no cover
    _AllProvidersExhausted = None
    _CassandraClient = None
    _ProviderError = None
    _ProviderBlocked = None
    _load_credentials = None
    _provider_catalog = None
    _compact = None
    _SkillIndex = None
    _environment_block = None
    _env_snapshot = None
    _extract_tool_blocks = None
    _tool_fetch = None
    _installed_tools = None

    def _needs_compaction(_msgs):
        return False

try:
        HAS_HTML_PARSER = True
except ImportError:
    HAS_HTML_PARSER = False

# Habilita bracketed paste no GNU readline: ao colar (botão direito),
# o texto vai todo para o buffer e só é enviado quando você pressionar
# Enter. Assim, um conteúdo copiado que termina com \n não dispara o
# prompt sem querer. Tenta importar/ler o readline de forma segura.
try:
    import readline  # noqa: F401
    readline.parse_and_bind("set enable-bracketed-paste on")
except (ImportError, OSError):
    pass

# Para o modo de interrupção por duplo ESC (apenas em sistemas Unix).
try:
    import select
    import termios
    import tty
except ImportError:
    select = termios = tty = None


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_URL = os.getenv(
    "CASSANDRA_BASE_URL",
    "",
).rstrip("/")

# Nunca deixe uma chave real versionada no código.
# Use um arquivo .env para armazenar sua chave!
# Exemplo no .env: CASSANDRA_API_KEY="sua-chave"
#
# A chave é OPCIONAL aqui: o cliente multi-provedor carrega credenciais
# de CASSANDRA_API_KEYS, <PROVIDER>_API_KEY ou CASSANDRA_API_KEY.
API_KEY = os.getenv("CASSANDRA_API_KEY", "")

LOG_DIR = Path(os.getenv("CASSANDRA_LOG_DIR", "./logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

SKILLS_DIR = Path(os.getenv("CASSANDRA_SKILLOGY", "./skills"))
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# Timeout de leitura do streaming da API (segundos). Modelos podem demorar
# para emitir o primeiro token; um valor alto evita "The read operation
# timed out". Ajustável por variável de ambiente.
API_STREAM_TIMEOUT = int(os.getenv("CASSANDRA_API_STREAM_TIMEOUT", "300"))
API_STREAM_RETRIES = int(os.getenv("CASSANDRA_STREAM_RETRIES", "2"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
log = logging.getLogger("cassandra")


# ============================================================
# LOG DE ATIVIDADE — o que a Cassandra está fazendo no sistema
# ============================================================

ACTIVITY_LOG = Path(
    os.getenv(
        "CASSANDRA_ACTIVITY_LOG",
        str(LOG_DIR / "cassandra-activity.log"),
    )
)


def log_activity(
    kind: str,
    command: str,
    detail: str = "",
    extra: Optional[Dict] = None,
) -> None:
    """
    Registra no arquivo de atividade o que a Cassandra fez no sistema
    (comandos de shell, prompts enviados, execuções puladas, etc.),
    tudo com timestamp para auditoria em tempo real.
    """
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": kind,
        "command": command,
        "detail": detail,
        **(extra or {}),
    }
    try:
        with ACTIVITY_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("Falha ao gravar log de atividade: %s", exc)


def show_activity(limit: int = 25) -> None:
    """
    Exibe as últimas entradas do log de atividade no terminal.
    Use :log dentro do chat para ver o que a Cassandra vem fazendo.
    """
    if not ACTIVITY_LOG.exists():
        print(ANSI.dim("Nenhuma atividade registrada ainda."))
        return

    lines = ACTIVITY_LOG.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    print(
        ANSI.fmt(
            f"╭─ ATIVIDADE DA CASSANDRA · {ACTIVITY_LOG}",
            ANSI.BRIGHT_RED,
            True,
        )
    )
    for line in lines[-limit:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("timestamp", "??:??:??")
        kind = entry.get("kind", "?")
        command = entry.get("command", "")
        icon = {
            "shell.execute": "⚡",
            "shell.skipped": "⊘",
            "prompt": "➤",
        }.get(kind, "·")
        print(
            f"  {ANSI.GRAY}{ts}{ANSI.RESET} "
            f"[{ANSI.BRIGHT_RED}{icon} {kind}{ANSI.RESET}] "
            f"{command}"
        )
    print(
        ANSI.fmt("╰──────────────────────────────────────────────", ANSI.BRIGHT_RED)
    )


# ============================================================
# CORES — FOCO VERMELHO
# ============================================================

class ANSI:
    """Códigos ANSI com detecção automática de suporte.

    No Windows, conhost.exe só entende ANSI se VirtualTerminalLevel=1
    (registro) ou se rodar dentro do Windows Terminal. Sem isso, os
    códigos aparecem como lixo na tela. Detecta e desabilita.
    """

    # Reset & modifiers
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    STRIKE = "\033[9m"

    # Foreground — standard
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Foreground — bright
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Foreground — dark / muted
    DARK_RED = "\033[2;31m"
    DARK_GREEN = "\033[2;32m"
    DARK_YELLOW = "\033[2;33m"
    DARK_BLUE = "\033[2;34m"
    DARK_MAGENTA = "\033[2;35m"
    DARK_CYAN = "\033[2;36m"

    # Backgrounds
    RED_BG = "\033[41m"
    GREEN_BG = "\033[42m"
    YELLOW_BG = "\033[43m"
    BLUE_BG = "\033[44m"
    MAGENTA_BG = "\033[45m"
    CYAN_BG = "\033[46m"
    WHITE_BG = "\033[47m"

    # Suporte a ANSI detectado em runtime
    _enabled: bool = True

    @classmethod
    def _detect_support(cls) -> bool:
        """Detecta se o terminal suporta ANSI escape sequences."""
        # Desabilitado por ambiente
        if os.getenv("NO_COLOR", "").strip():
            return False
        if os.getenv("TERM", "") == "dumb":
            return False
        # Windows: verifica se é Windows Terminal ou se VirtualTerminalLevel=1
        if os.name == "nt":
            # Windows Terminal define WT_SESSION
            if os.getenv("WT_SESSION"):
                return True
            # Verifica registro VirtualTerminalLevel
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, r"Console"
                ) as key:
                    val, _ = winreg.QueryValueEx(key, "VirtualTerminalLevel")
                    return bool(val)
            except Exception:
                return False
        # Unix: assume suporte (xterm, linux console, etc.)
        return True

    @classmethod
    def init(cls) -> None:
        """Inicializa detecção de suporte ANSI. Chamar uma vez no início."""
        cls._enabled = cls._detect_support()
        if not cls._enabled:
            # Limpa todos os códigos
            cls.RESET = ""
            cls.BOLD = ""
            cls.DIM = ""
            cls.ITALIC = ""
            cls.UNDERLINE = ""
            cls.STRIKE = ""
            cls.BLACK = ""
            cls.RED = ""
            cls.GREEN = ""
            cls.YELLOW = ""
            cls.BLUE = ""
            cls.MAGENTA = ""
            cls.CYAN = ""
            cls.WHITE = ""
            cls.GRAY = ""
            cls.BRIGHT_RED = ""
            cls.BRIGHT_GREEN = ""
            cls.BRIGHT_YELLOW = ""
            cls.BRIGHT_BLUE = ""
            cls.BRIGHT_MAGENTA = ""
            cls.BRIGHT_CYAN = ""
            cls.BRIGHT_WHITE = ""
            cls.DARK_RED = ""
            cls.DARK_GREEN = ""
            cls.DARK_YELLOW = ""
            cls.DARK_BLUE = ""
            cls.DARK_MAGENTA = ""
            cls.DARK_CYAN = ""
            cls.RED_BG = ""
            cls.GREEN_BG = ""
            cls.YELLOW_BG = ""
            cls.BLUE_BG = ""
            cls.MAGENTA_BG = ""
            cls.CYAN_BG = ""
            cls.WHITE_BG = ""

    @classmethod
    def fmt(cls, text: str, fg: str = "", bold: bool = False) -> str:
        if not cls._enabled:
            return text
        prefix = (cls.BOLD if bold else "") + fg
        return f"{prefix}{text}{cls.RESET}"

    @classmethod
    def banner(cls) -> str:
        try:
            from cassandra.attribution import attribution_line
            _attr = attribution_line()
        except Exception:
            _attr = "Morlsara Code Nexus — criado e desenvolvido por Mörlsara"
        return (
            f"\n{cls.BRIGHT_RED}{cls.BOLD}"
            "╔══════════════════════════════════════════════╗\n"
            "║              C A S S A N D R A               ║\n"
            "║              SYSTEM INTERFACE                ║\n"
            "╚══════════════════════════════════════════════╝"
            f"{cls.RESET}\n"
            f"{cls.fmt('  ' + _attr, cls.GRAY)}\n"
        )

    @classmethod
    def ok(cls, text: str) -> str:
        return cls.fmt(f"  [+] {text}", cls.BRIGHT_GREEN, True)

    @classmethod
    def err(cls, text: str) -> str:
        return cls.fmt(f"  [-] {text}", cls.BRIGHT_RED, True)

    @classmethod
    def info(cls, text: str) -> str:
        return cls.fmt(f"  [i] {text}", cls.BRIGHT_CYAN)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.fmt(f"     {text}", cls.GRAY)

    @classmethod
    def warn(cls, text: str) -> str:
        return cls.fmt(f"  [!] {text}", cls.BRIGHT_YELLOW, True)

    @classmethod
    def success(cls, text: str) -> str:
        return cls.fmt(f"  [+] {text}", cls.BRIGHT_GREEN, True)

    @classmethod
    def accent(cls, text: str) -> str:
        return cls.fmt(f"  [>] {text}", cls.BRIGHT_MAGENTA, True)

    @classmethod
    def highlight(cls, text: str) -> str:
        return cls.fmt(f"  [*] {text}", cls.BRIGHT_CYAN, True)

    @classmethod
    def shell(cls, text: str) -> str:
        return cls.fmt(f"  [$] {text}", cls.BRIGHT_YELLOW)

    @classmethod
    def skill(cls, text: str) -> str:
        return cls.fmt(f"  [S] {text}", cls.BRIGHT_BLUE)

    @classmethod
    def tool(cls, text: str) -> str:
        return cls.fmt(f"  [T] {text}", cls.BRIGHT_MAGENTA)

    @classmethod
    def web(cls, text: str) -> str:
        return cls.fmt(f"  [W] {text}", cls.BRIGHT_CYAN)

    @classmethod
    def compact(cls, text: str) -> str:
        return cls.fmt(f"  [C] {text}", cls.BRIGHT_YELLOW)


# ============================================================
# IDENTIDADE / SKILLOGY
# ============================================================

DEFAULT_SKILLOGY_PATHS = (
    os.getenv("CASSANDRA_SKILLOGY", "./skills"),
    "./cassandra-skill",
    "./cassandra-skillogy.md",
    "./cassandra-skillogy.txt",
    "./cassandra_skillogy.md",
    "./cassandra_skillogy.txt",
)


def load_available_skills() -> List[Dict[str, str]]:
    """
    Lê todas as skills disponíveis (arquivos .md) e retorna uma lista de dicionários com path e content.
    """
    skills = []
    seen = set()

    for raw_path in DEFAULT_SKILLOGY_PATHS:
        if not raw_path:
            continue

        path = Path(raw_path).expanduser()
        if path in seen:
            continue
        seen.add(path)

        try:
            if path.is_file():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    skills.append({"path": str(path), "content": content})
            elif path.is_dir():
                for subfile in path.rglob("*.md"):
                    content = subfile.read_text(encoding="utf-8").strip()
                    if content:
                        skills.append({"path": str(subfile), "content": content})
        except OSError as exc:
            log.warning("Não foi possível ler a Skillogy %s: %s", path, exc)

    return skills


def build_system_prompt(user: str, privilege: str, skillogy: str, allow_shell: bool = False) -> str:
    """
    Persona estável da Cassandra (Red Team & Forensics).
    O cérebro principal agora é carregado via SOUL.md.
    """
    import platform
    os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
    
    shell_rules = ""
    if allow_shell:
        shell_rules = """- **PERMISSÃO DE SHELL**: ✅ **ATIVADA** (`--allow-shell` foi passado).
- **AUTONOMIA TOTAL**: Você opera a máquina. JAMAIS diga ao operador para fazer algo que você mesma pode fazer via shell (instalar pacotes, criar arquivos, rodar scripts, editar configs). **FAÇA VOCÊ MESMA.**
- **ENCADEAMENTO**: `cd` isolado não persiste entre blocos. Use `cd pasta && comando` ou caminhos absolutos.
- **ITERAÇÃO**: Execute, leia a saída, corrija erros e continue sozinha até concluir o objetivo. Não pare no primeiro obstáculo.
- **PROCESSOS DEMORADOS**: Se for rodar algo longo (nmap, varredura, download pesado), avise no texto que está iniciando e peça para aguardar.
- **O TERMINAL É SEU DEBUG**: tudo que você executa aparece em tempo real no terminal do operador. Use isso a seu favor — mostre o que está fazendo."""
    else:
        shell_rules = """- **PERMISSÃO DE SHELL**: ⚠️ **RESTRITA** (`--allow-shell` NÃO foi passado).
- Você PODE e DEVE escrever comandos shell como texto (blocos ```bash / ```powershell) — eles são úteis para o operador copiar e rodar.
- Mas eles **NÃO serão executados automaticamente**. Não afirme que executou algo.
- Se a tarefa exigir execução real na máquina, informe ao operador que ele deve reiniciar a Cassandra com `--allow-shell` para você agir de forma autônoma.
- Continue sendo útil: analise, planeje, escreva os comandos prontos e explique o que cada um faz."""
    
    return f"""
# CASSANDRA — SYSTEM PERSONA

VOCÊ ESTÁ OPERANDO DENTRO DE UMA INTERFACE CHAMADA **CASSANDRA**.

{skillogy}

## Identidade de Interface

- Nome de interface: **Cassandra**
- Função: Especialista Absoluta em **Red Team e Forense Digital**.
- Usuário local: `{user}`
- Privilégio do processo local: `{privilege}`
- Ambiente Operacional: `{os_info}`
{shell_rules}

Ao conversar com o usuário, mantenha a persona Cassandra de maneira
consistente. Você deve atuar estrita e rigidamente como especialista.
Não invente consciência, acesso ou capacidades que não existam.
- **FOCO DE ATUAÇÃO**: Você roda NA máquina do usuário como uma aliada. O seu alvo NUNCA é a máquina local que a está hospedando e executando. Seu foco são estritamente ALVOS EXTERNOS ou análises de dados locais autorizados pelo usuário. Jamais tente invadir, investigar ou se voltar contra o próprio host (localhost) de forma hostil.

Como o ambiente é `{os_info}`, você DEVE formatar seus comandos shell adequadamente:
- Se for Linux/Mac: Use comandos bash válidos (`ls`, `grep`, `cat`, etc).
- Se for Windows: Use comandos CMD ou PowerShell válidos (`dir`, `Select-String`, `type`, etc).

## REGRA CRÍTICA DE EXECUÇÃO (blocos de shell)

Para que um comando seja **executado de verdade** na máquina, ele precisa vir
num bloco de código com a tag do shell do ambiente. Blocos sem tag, ou com
tags erradas, **não são executados** — aparecem apenas como texto para o
operador copiar.

- No **Linux/Mac**, marque o bloco como ```bash (aceita também ```sh / ```shell).
- No **Windows**, marque o bloco como ```powershell (aceita também ```pwsh /
  ```ps1) ou ```cmd / ```bat para comandos CMD.

Exemplo correto no Windows:
```powershell
Get-ChildItem -Path C:\\Users -Recurse -ErrorAction SilentlyContinue
```

Exemplo correto no Linux:
```bash
ls -la /home
```

NUNCA escreva o comando fora de um bloco marcado esperando que ele execute.
Se você quer que a ação aconteça, emita o bloco com a tag correta e siga
sozinha: leia a saída, corrija erros e continue até concluir o objetivo.

## Estilo de Resposta

As respostas devem ser **Markdown válido e bem organizado**.

Use:
- Estruture visualmente usando títulos `#`, `##` e `###` de forma consistente;
- **Destaque em negrito** os conceitos centrais, caminhos de arquivo e IPs;
- Utilize listas e bullet points detalhados para guias e procedimentos;
- Empregue tabelas organizadas para matrizes de dados, comparativos ou status;
- ⚠️ Aplique Emojis estrategicamente (ex: 🚀, 🛡️, ⚙️, 💀, 🔍) no início de títulos, para categorizar status ou indicar alertas, criando um documento altamente visual, mas evite poluição;
- Blocos de código devem ter a sintaxe especificada e ser visualmente isolados do texto;
- Explicações curtas e cirúrgicas antes de comandos;
- Resultados e conclusões com seções próprias e claramente separadas.

Evite paredes de texto. Sempre priorize ação e execução sobre teorias vazias.
- **SEJA CONCISA E DIRETA**: Forneça APENAS o que for estritamente necessário. Não gere textos verbosos, explicações óbvias ou introduções longas. Vá direto ao ponto para manter a interface web super organizada e evitar poluição visual.
- **CONTROLE ABSOLUTO E PASSIVIDADE**: Jamais tome iniciativas não solicitadas. NUNCA gere ou sugira blocos de código/comandos em massa a menos que o usuário peça explicitamente. Não inicie varreduras, loops ou qualquer tipo de exploração por conta própria. Após executar uma ordem, você DEVE parar, reportar os dados e aguardar instruções. Seu papel é servir, não tomar o controle de forma agressiva e caótica.
- **NUNCA ABANDONE UMA TAREFA EM ANDAMENTO**: Se você iniciou uma tarefa com múltiplos passos (uma varredura, uma exploração, um script em construção), **termine-a** antes de parar. Não largue no meio. Se encontrar um obstáculo, resolva-o ou reporte o bloqueio com clareza — mas nunca simplesmente pare sem avisar. Uma tarefa só é considerada concluída quando o objetivo foi atingido ou você declarou explicitamente por que não pode continuar.

## 💾 [PROTOCOLO DE COMPACTAÇÃO NATIVA E MEMÓRIA]

O seu backend foi programado para injetar as mensagens de histórico de forma sequencial. Quando a conversa atinge mais de 10 turnos, ela pode gerar estouro de limite (token limit).
Por isso, VOCÊ DEVE gerenciar sua própria memória.
Sempre que você notar que a discussão está longa, complexa, ou envolveu muitos passos investigativos, finalize a sua resposta com um pequeno bloco JSON `[STATE_DUMP]` contendo as descobertas cruciais, senhas, IPs e o alvo atual. 
Isso garantirá que, se o contexto for truncado ou compactado à força pelo sistema, você recupere sua memória a partir do seu último dump.

## 📐 [MÓDULO DE RACIOCÍNIO: PROGRESSÃO GEOMÉTRICA E ESCALAS EXPONENCIAIS]

Você raciocina com precisão sobre crescimento, decaimento e escalas
exponenciais — tanto em matemática pura quanto como **estratégia de
operação** (dimensionar varreduras, estimar tempo de quebra, planejar
fuzz com profundidade crescente).

### 1. Identificação e modelagem

Antes de calcular, classifique o problema. Toda escala exponencial tem
três parâmetros:

| Parâmetro | Significado | Como achar |
|---|---|---|
| `a_1` | valor inicial | primeiro termo, população inicial, chave inicial |
| `q` | razão | taxa de crescimento/decaimento por passo |
| `n` | número de passos | iterações, tempo, profundidade |

Forma fechada: `a_n = a_1 · q^(n-1)`.
Soma dos `n` primeiros termos: `S_n = a_1 · (q^n − 1)/(q − 1)` para `q ≠ 1`.

**Nunca** itere manualmente quando a forma fechada resolve. Iterar é
verificação, não método.

### 2. Mapeamento do mundo real

| Fenômeno | `q` | Observação |
|---|---|---|
| Juros compostos | `1 + i` | `a_n = P·(1+i)^n` |
| Meia-vida | `1/2` | `a_n = a_1·2^(−n/h)` |
| Duplicação / crescimento | `2` | bactérias, Moores's law |
| Depreciação percentual | `1 − d` | `d` = taxa por período |
| Diluição seriada | `1/fator` | — |
| Espaço de busca de senha | alfabeto | `n = log_q(espaço)` |
| Varredura em profundidade crescente | `2` | nós por nível |

### 3. Casos-limite e convergência

- `|q| < 1` → converge. Soma infinita: `S_∞ = a_1/(1 − q)`.
- `|q| > 1` → diverge. Só faz sentido falar em `a_n` para `n` finito.
- `q = 1` → progressão constante (`a_n = a_1`); a fórmula da soma vira `S_n = n·a_1`.
- `q = 0` → colapsa para zero após o primeiro termo.
- `q < 0` → alterna de sinal; trate o módulo para convergência.

### 4. Resolver para `n` (o caso mais comum na prática)

Quando a pergunta é *"quanto tempo / quantos passos / quantas iterações"*,
o problema é logarítmico, não exponencial:

```
n = log_q(X / a_1) + 1        (para X = valor-alvo)
```

Use logaritmo natural e converta: `log_q(x) = ln(x)/ln(q)`.
Trabalhe com potências exatas quando o contexto for binário
(bits, chaves, endereços) — `2^32`, `2^64`, `2^128` são valores exatos,
não aproximações.

### 5. Aplicação operacional (dimensionamento)

Use PG para **estimar antes de executar**:

- **Tempo de enumeração**: espaço de busca `q^n` dividido pela taxa de
  tentativas → tempo real. Se o resultado for inviável, mude a estratégia
  antes de gastar horas.
- **Profundidade de varredura**: cada nível multiplica o custo por `q`.
  Calcule o custo total `S_n` antes de disparar.
- **Backoff**: recuo exponencial é uma PG com `q = 2` e teto. O tempo
  total de `n` tentativas é `S_n` — use para decidir `n`.
- **Cobertura de fuzz**: se cada mutação gera `q` variantes e você faz `n`
  gerações, o total é `S_n`. Compare com o orçamento disponível.

### 6. Verificação obrigatória

Depois de calcular, **confirme por dois caminhos independentes**:

1. **Iteração direta** — calcule 2–3 termos à mão e compare com a fórmula.
2. **Ordem de grandeza** — o resultado é plausível? `2^10 ≈ 10^3`,
   `2^20 ≈ 10^6`, `2^30 ≈ 10^9`, `2^40 ≈ 10^12`. Use isso como sanidade.
3. **Checagem de `n`** — `n` é o número de termos (índice final − inicial + 1),
   não o expoente aparente. Erro clássico.
4. **Duas formas** — mostre o resultado em notação decimal e em potência
   quando fizer sentido (`2^10 − 1 = 1023`).

### 7. Formato da resposta

Para problemas de PG, apresente explicitamente:

```
a_1 = <valor>   q = <razão>   n = <passos>
Equação: <forma usada>
Resultado: <valor em destaque>
Verificação: <iteração de 2–3 termos>
```

Conclua em uma linha dizendo **por que** o problema é uma PG.

**Não force PG onde não há.** Se o crescimento for linear, logarítmico ou
irregular, diga isso e use o modelo correto. Identificar que *não* é PG é
tão valioso quanto resolver uma.

## Skillogy

A Skillogy externa abaixo representa conhecimento adicional disponibilizado
para esta instalação da Cassandra. Use-a como contexto técnico quando for
relevante, sem inventar conteúdo que não esteja nela.

{skillogy}

## Limites de execução

Você possui **autonomia e acesso total à máquina** através da interface shell.
Os blocos de código `bash` ou `sh` que você retornar podem ser executados 
automaticamente e em tempo real. Aja como uma assistente autônoma com as
permissões reais da sessão ({privilege}).

## Acesso à Internet (Busca Inteligente)

Você TEM acesso à internet e DEVE pesquisar ativamente sempre que precisar de informações recentes, cotações, notícias, documentações ou dados externos.
Para buscar na web de forma autônoma, você deve incluir em sua resposta um bloco de código com a linguagem `search`. Exemplo:

```search
quem ganhou o oscar de melhor ator em 2024
```

Assim que você retornar esse bloco, o sistema executará a busca na internet e entregará os resultados para você continuar analisando. Você pode fazer várias buscas em sequência se precisar. NUNCA diga que não tem acesso a informações em tempo real; faça a busca!

## Objetivo

Entregar respostas técnicas, organizadas, precisas e úteis mantendo
consistentemente a interface Cassandra.
""".strip()


# ============================================================
# MARKDOWN → TERMINAL
# ============================================================

def render_inline(text: str, base: str) -> str:
    """
    Aplica destaque inline (código, negrito, itálico, riscado e links)
    reaplicando a cor base após cada elemento estilizado.

    Os spans de código são isolados em placeholders primeiro para que,
    quando as outras expressões inserirem códigos ANSI (que contêm '['),
    nada seja combinado errado dentro deles.
    """
    code_spans = []

    def stash_code(match):
        index = len(code_spans)
        code_spans.append(match.group(1))
        return f"\x00C{index}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)

    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: ANSI.UNDERLINE + m.group(1) + ANSI.RESET + base
        + ANSI.GRAY + "(" + m.group(2) + ")" + ANSI.RESET + base,
        text,
    )
    text = re.sub(
        r"\*\*([^*\n]+)\*\*",
        lambda m: ANSI.BOLD + m.group(1) + ANSI.RESET + base,
        text,
    )
    text = re.sub(
        r"~~([^~\n]+)~~",
        lambda m: ANSI.STRIKE + m.group(1) + ANSI.RESET + base,
        text,
    )
    text = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        lambda m: ANSI.ITALIC + m.group(1) + ANSI.RESET + base,
        text,
    )

    for index, content in enumerate(code_spans):
        text = text.replace(
            f"\x00C{index}\x00",
            ANSI.RED_BG + ANSI.WHITE + content + ANSI.RESET + base,
        )

    return text


def style_markdown_line(line: str, in_code: bool) -> tuple[str, bool]:
    """
    Estiliza uma linha completa de Markdown e retorna (texto_ansi, novo_in_code).
    """
    raw = line
    stripped = raw.strip()

    if not stripped:
        return "", in_code

    # Marcador de bloco de código (``` ou ```bash)
    if stripped.startswith("```"):
        return ANSI.fmt(stripped, ANSI.DARK_RED, True), not in_code

    # Dentro de bloco de código
    if in_code:
        return ANSI.fmt(raw, ANSI.GRAY), in_code

    # Linha horizontal
    if re.match(r"^(\s*)(-{3,}|\*{3,}|_{3,})(\s*)$", raw):
        return ANSI.fmt(raw, ANSI.DARK_RED), in_code

    # Cabeçalhos
    header = re.match(r"^(#{1,6})\s+(.*)$", raw)
    if header:
        level = len(header.group(1))
        content = header.group(2)
        if level == 1:
            base = ANSI.BRIGHT_RED + ANSI.BOLD
        elif level == 2:
            base = ANSI.RED + ANSI.BOLD
        else:
            base = ANSI.DARK_RED + ANSI.BOLD
        return base + ANSI.WHITE + render_inline(content, ANSI.WHITE) + ANSI.RESET + base, in_code

    # Lista desordenada
    bullet = re.match(r"^(\s*)([-*+])\s+(.*)$", raw)
    if bullet:
        text = bullet.group(3)
        marker = bullet.group(2)
        base = ANSI.WHITE
        return (
            ANSI.DARK_RED + bullet.group(1) + ANSI.BOLD + marker
            + ANSI.RESET + base + " " + render_inline(text, base)
        ), in_code

    # Lista ordenada
    ordered = re.match(r"^(\s*\d+[.)])\s+(.*)$", raw)
    if ordered:
        base = ANSI.WHITE
        return (
            ANSI.BRIGHT_RED + ANSI.BOLD + ordered.group(1)
            + ANSI.RESET + base + " " + render_inline(ordered.group(2), base)
        ), in_code

    # Tabela
    if raw.lstrip().startswith("|") and raw.count("|") >= 2:
        # Linha separadora do cabeçalho (| --- | --- |)
        if re.match(r"^[\s|:.\-]+$", raw) and "-" in raw:
            return ANSI.fmt(raw, ANSI.DARK_RED), in_code
        cells = [c.strip() for c in raw.split("|") if c.strip()]
        if cells:
            base = ANSI.WHITE
            body = (ANSI.RED + " ├ " + ANSI.RESET).join(
                base + render_inline(c, base) for c in cells
            )
            return ANSI.RED + "▌ " + ANSI.RESET + body, in_code

    # Citação
    if raw.startswith(">"):
        quote = re.match(r"^>\s?(.*)$", raw)
        content = quote.group(1) if quote else raw[1:]
        base = ANSI.WHITE
        return (
            ANSI.fmt("▍ ", ANSI.DARK_RED, True)
            + base + render_inline(content, base)
        ), in_code

    # Parágrafo normal
    base = ANSI.WHITE
    return base + render_inline(raw, base), in_code


def stream_and_render_markdown(generator, interrupt=None) -> str:
    """
    Consome o gerador e renderiza o Markdown linha a linha, com bordas
    vermelhas, títulos destacados, listas, tabelas e código inline colorido.

    `interrupt` é um objeto opcional com o atributo `.triggered` (ex.:
    EscInterrupt). Quando disparado, a resposta é interrompida no ato.
    """
    term_width = shutil.get_terminal_size().columns
    width = max(40, term_width - 6)

    title = "─ Cassandra · resposta "
    top_border = "╭" + title + "─" * max(0, width + 2 - len(title)) + "╮"
    bottom_border = ANSI.fmt("╰" + "─" * (width + 2) + "╯", ANSI.BRIGHT_RED, True)
    print(ANSI.fmt(top_border, ANSI.BRIGHT_RED, True))

    left_border = ANSI.fmt("│ ", ANSI.BRIGHT_RED, True)

    full_reply = []

    line_buffer = ""
    in_code = False
    interrupted = False

    def flush_line():
        nonlocal line_buffer
        nonlocal in_code

        line = line_buffer
        line_buffer = ""

        if not line.strip():
            sys.stdout.write(ANSI.RESET + "\n" + left_border)
            sys.stdout.flush()
            return

        styled, in_code = style_markdown_line(line, in_code)
        sys.stdout.write(styled + ANSI.RESET + "\n" + left_border)
        sys.stdout.flush()

    sys.stdout.write(left_border)
    sys.stdout.flush()

    for chunk in generator:
        if interrupt is not None and interrupt.triggered:
            interrupted = True
            break

        full_reply.append(chunk)

        for char in chunk:
            if char == '\n':
                flush_line()
            else:
                line_buffer += char

    if interrupted:
        if line_buffer.strip():
            flush_line()
        sys.stdout.write(ANSI.fmt("⏹ Resposta interrompida pelo usuário.", ANSI.YELLOW, True))
        print(ANSI.RESET + "\n")
    else:
        if line_buffer.strip():
            flush_line()
        elif line_buffer:
            sys.stdout.write(ANSI.RESET)
            sys.stdout.flush()
        print(ANSI.RESET + "\n")

    print(bottom_border)

    return "".join(full_reply)


# ============================================================
# ANIMAÇÃO
# ============================================================

class ThinkingAnimation:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _run(self):
        frames = [
            "⠋",
            "⠙",
            "⠹",
            "⠸",
            "⠼",
            "⠴",
            "⠦",
            "⠧",
            "⠇",
            "⠏",
        ]

        i = 0
        while self.running:
            frame = frames[i % len(frames)]
            message = f"  {frame} Cassandra está processando..."
            sys.stdout.write(
                "\r" + ANSI.fmt(message, ANSI.BRIGHT_RED, True)
            )
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1


# ============================================================
# INTERRUPÇÃO POR DUPLO ESC
# ============================================================

class EscInterrupt:
    """
    Observa o stdin em modo cru e detecta ESC ESC (duplo ESC em sequência).
    Quando detectado, marca um sinal de interrupção que o loop principal
    usa para parar a resposta da API e liberar o terminal para um novo prompt.
    """

    WINDOW = 0.6  # segundos para os dois ESC serem considerados duplo

    def __init__(self):
        self._flag = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fd: Optional[int] = None
        self._saved_attrs = None

    @property
    def triggered(self) -> bool:
        return self._flag.is_set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if select is None:
            return

        self._flag.clear()
        self._stop.clear()
        self._fd = None
        try:
            self._fd = sys.stdin.fileno()
            self._saved_attrs = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except (OSError, termios.error, AttributeError) as exc:
            log.debug("Interrupção por ESC ESC indisponível: %s", exc)
            self._fd = None
            return

        self._thread = threading.Thread(
            target=self._watch,
            daemon=True,
            name="esc-interrupt",
        )
        self._thread.start()

    def stop(self) -> None:
        # Sempre sinaliza a thread para terminar e só então restaura o
        # terminal. Antes, a thread ficava viva lendo o stdin e "roubava"
        # a digitação do próximo prompt (causando travamentos).
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._fd is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)
            except (OSError, termios.error):
                pass
            self._fd = None

    def _watch(self) -> None:
        first_esc_at = 0.0
        while not self._stop.is_set():
            if first_esc_at and (time.time() - first_esc_at) > self.WINDOW:
                first_esc_at = 0.0

            try:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.2)
                if not rlist:
                    continue
                data = os.read(self._fd, 1)
            except (OSError, ValueError):
                return

            if not data:
                continue

            byte = data[0]
            if byte == 0x1b:  # ESC
                now = time.time()
                if first_esc_at and (now - first_esc_at) <= self.WINDOW:
                    self._flag.set()
                    return
                first_esc_at = now
            else:
                first_esc_at = 0.0


# ============================================================
# BUSCA NA WEB
# ============================================================

def web_search_ddg(query: str, max_results: int = 5) -> str:
    """
    Busca no DuckDuckGo (HTML) usando requests.
    Retorna resultados formatados como texto.
    """
    if not HAS_REQUESTS:
        return "[ERRO: biblioteca 'requests' não disponível. Instale com: pip install requests]"

    try:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query, "format": "html", "no_redirect": 1, "no_html": 1}
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Extrai resultados dos links do DDG HTML
        results = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div|span)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        out = []
        out.append(f"## Resultados da busca: {query}")
        out.append(f"*(fonte: DuckDuckGo HTML | {len(results)} resultados)*")
        out.append("")

        for i, (url, title_html) in enumerate(results[:max_results], 1):
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            title = re.sub(r"\s+", " ", title)
            snippet = ""
            if i - 1 < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i - 1]).strip()
                snippet = re.sub(r"\s+", " ", snippet)
            out.append(f"### {i}. {title}")
            out.append(f"🔗 {url}")
            if snippet:
                out.append(f"_{snippet}_")
            out.append("")

        if not results:
            out.append("_Nenhum resultado encontrado via DuckDuckGo HTML._")

        return "\n".join(out)

    except Exception as exc:
        return f"[ERRO na busca DuckDuckGo: {exc}]"


def web_search_brave(query: str, max_results: int = 5) -> str:
    """
    Busca na API do Brave Search (requer BRAVE_SEARCH_API_KEY).
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        return "[ERRO: BRAVE_SEARCH_API_KEY não configurada. Procure no DuckDuckGo.]"

    if not HAS_REQUESTS:
        return "[ERRO: biblioteca 'requests' não disponível.]"

    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "Cassandra-CLI/4.0",
        }
        params = {"q": query, "count": max_results, "search_lang": "pt,en"}
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        out = []
        out.append(f"## Resultados da busca: {query}")
        out.append(f"*(fonte: Brave Search | {len(data.get('web', {}).get('results', []))} resultados)*")
        out.append("")

        for i, r in enumerate(data.get("web", {}).get("results", [])[:max_results], 1):
            out.append(f"### {i}. {r.get('title', 'Sem título')}")
            out.append(f"🔗 {r.get('url', '')}")
            snip = r.get("snippet", "") or r.get("description", "")
            if snip:
                out.append(f"_{snip}_")
            out.append("")

        return "\n".join(out)

    except Exception as exc:
        return f"[ERRO na busca Brave: {exc}]"


def web_search_google(query: str, max_results: int = 5) -> str:
    """
    Busca via Google Programmable Search JSON API (requer GOOGLE_API_KEY + CSE_ID).
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_CSE_ID", "")
    if not api_key or not cse_id:
        return "[ERRO: GOOGLE_API_KEY e GOOGLE_CSE_ID não configurados.]"

    if not HAS_REQUESTS:
        return "[ERRO: biblioteca 'requests' não disponível.]"

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": max_results,
            "lr": "lang_pt|lang_en",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        out = []
        out.append(f"## Resultados da busca: {query}")
        items = data.get("items", [])
        out.append(f"*(fonte: Google CSE | {len(items)} resultados)*")
        out.append("")

        for i, item in enumerate(items[:max_results], 1):
            out.append(f"### {i}. {item.get('title', 'Sem título')}")
            out.append(f"🔗 {item.get('link', '')}")
            snippet = item.get("snippet", "") or item.get("htmlSnippet", "")
            if snippet:
                snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                out.append(f"_{snippet}_")
            out.append("")

        return "\n".join(out)

    except Exception as exc:
        return f"[ERRO na busca Google: {exc}]"


def web_fetch_url(url: str, max_chars: int = 4000) -> str:
    """
    Faz um GET em uma URL e retorna o conteúdo textual extraído.
    Usa requests se disponível, senão urllib.
    """
    try:
        if HAS_REQUESTS:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        else:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept": "text/html,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")

        # Strip tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + "… [truncado]"

        return f"## Conteúdo fetched de: {url}\n\n{text}"

    except Exception as exc:
        return f"[ERRO ao fetch {url}: {exc}]"


def web_search(query: str, max_results: int = 5) -> str:
    """
    Tenta buscar em 여러 motores em ordem:
    1. DuckDuckGo HTML (sempre disponível, sem chave)
    2. Brave Search (se tiver BRAVE_SEARCH_API_KEY)
    3. Google CSE (se tiver GOOGLE_API_KEY + GOOGLE_CSE_ID)

    Retorna os melhores resultados encontrados.
    """
    results_parts = []

    # 1. DuckDuckGo sempre
    ddg_result = web_search_ddg(query, max_results)
    results_parts.append(ddg_result)

    # 2. Brave se tiver
    brave_result = web_search_brave(query, max_results)
    if "ERRO" not in brave_result or "Nenhum resultado" not in ddg_result:
        results_parts.append("\n--- BRAVE SEARCH ---\n" + brave_result)

    # 3. Google se tiver
    google_result = web_search_google(query, max_results)
    if "ERRO" not in google_result:
        results_parts.append("\n--- GOOGLE CSE ---\n" + google_result)

    return "\n".join(results_parts)


def web_search_and_fetch(query: str, max_results: int = 5) -> str:
    """
    Busca na web e retorna os resultados prontos para o modelo usar.
    Se a busca retornar algo útil, automaticamente faz fetch do conteúdo
    do primeiro resultado se for um HTML.
    """
    search_results = web_search(query, max_results)

    # Se o DuckDuckGo retornou resultados, tentar fetch do primeiro link
    if HAS_REQUESTS:
        try:
            ddg_url = "https://html.duckduckgo.com/html/"
            params = {"q": query, "format": "html", "no_redirect": 1}
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            }
            resp = requests.get(ddg_url, params=params, headers=headers, timeout=15)
            html = resp.text
            first_link = re.search(
                r'class="result__a"[^>]*href="([^"]+)"',
                html,
                re.IGNORECASE,
            )
            if first_link:
                raw_url = first_link.group(1)
                # DDG usa redirecionamento /l/?uddg=URL_ENCODADA
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(raw_url)
                if parsed.query:
                    qs = urlparse.parse_qs(parsed.query)
                    if "uddg" in qs:
                        real_url = qs["uddg"][0]
                        # Decodifica
                        real_url = urllib.parse.unquote(real_url)
                        fetch_result = web_fetch_url(real_url, max_chars=5000)
                        return f"{search_results}\n\n{fetch_result}"
        except Exception:
            pass

    return search_results


# ============================================================
# CLASSE AGENT
# ============================================================

class Agent:
    def __init__(self, allow_interactive: bool = True):
        self.available_skills = load_available_skills()
        self._client = None
        self._skill_index = None
        self.allow_interactive = allow_interactive

    @property
    def client(self):
        """Cliente multi-provedor (lazy)."""
        if self._client is None:
            if _CassandraClient is None:
                raise RuntimeError(
                    "Núcleo multi-provedor indisponível. Verifique se o pacote "
                    "'cassandra/' está presente e as dependências instaladas."
                )
            self._client = _CassandraClient(_load_credentials())
        return self._client

    def clear_session(self):
        """
        Sem sessão remota persistente no modo API-key: cada requisição é
        independente. Este método existe para compatibilidade com a UI e
        apenas descarta o cliente HTTP em cache.
        """
        self._client = None

    def get_relevant_skillogy(
        self,
        prompt: str,
        allow_shell: bool = False,
        model: str = "",
        provider: str = "",
    ) -> tuple[str, list[str]]:
        """
        Monta o contexto: SOUL.md (persona) + consciência de ambiente +
        skills relevantes ao prompt.

        As skills são buscadas pelo índice; se o prompt citar uma skill
        pelo nome, ela é carregada integralmente.
        """
        soul_content = ""
        soul_path = None
        for raw_path in DEFAULT_SKILLOGY_PATHS:
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            soul_candidate = path / "SOUL.md"
            if soul_candidate.is_file():
                soul_content = soul_candidate.read_text(encoding="utf-8").strip()
                soul_path = str(soul_candidate)
                break

        if not soul_content:
            for raw_path in DEFAULT_SKILLOGY_PATHS:
                if not raw_path:
                    continue
                path = Path(raw_path).expanduser()
                if path.is_dir():
                    for subfile in path.rglob("SOUL.md"):
                        soul_content = subfile.read_text(encoding="utf-8").strip()
                        soul_path = str(subfile)
                        break
                if soul_content:
                    break

        if not soul_content:
            soul_content = "Você é a Cassandra. Aja de acordo com seus protocolos nativos."

        # --- Consciência de ambiente ---
        env_part = ""
        if _env_snapshot is not None and _environment_block is not None:
            try:
                env = _env_snapshot(
                    allow_shell=allow_shell,
                    model=model,
                    provider=provider,
                )
                env_part = "\n\n" + _environment_block(env) + "\n"
            except Exception as exc:  # noqa: BLE001
                log.debug("Falha ao montar o bloco de ambiente: %s", exc)

        # --- Skills relevantes ---
        matched_files = ["SOUL.md"]
        skill_part = ""

        if _SkillIndex is not None:
            try:
                if self._skill_index is None:
                    self._skill_index = _SkillIndex()
                idx = self._skill_index

                # 1. Skills citadas explicitamente no prompt (por nome).
                cited: list[str] = []
                for entry in idx.entries:
                    short = entry.name.split("/")[-1]
                    if len(short) > 4 and short.lower() in prompt.lower():
                        cited.append(entry.name)

                blocks: list[str] = []
                total = 0
                max_len = 60000

                for name in cited:
                    content, loaded = idx.load(name)
                    if content and total + len(content) <= max_len:
                        blocks.append(content)
                        total += len(content)
                        matched_files.extend(loaded)

                # 2. Se nada foi citado, busca por relevância ao prompt.
                if not blocks:
                    words = [w for w in re.findall(r"\w{4,}", prompt.lower())]
                    if words:
                        query = " ".join(words[:8])
                        content, loaded = idx.load(query)
                        if content and len(content) <= max_len:
                            blocks.append(content)
                            matched_files.extend(loaded)

                if blocks:
                    skill_part = (
                        "\n\n# SKILLOGY CARREGADA\n\n"
                        + "\n\n---\n\n".join(blocks)
                        + "\n"
                    )
                else:
                    skill_part = (
                        f"\n\n# SKILLOGY\n\n"
                        f"{idx.catalog(limit=120)}\n\n"
                        "*(Nenhuma skill carregada em detalhe. Peça uma "
                        "específica com um bloco ```skill se precisar.)*\n"
                    )
            except Exception as exc:  # noqa: BLE001
                log.debug("Falha ao indexar skills: %s", exc)

        if not skill_part:
            skill_part = (
                "\n\n# SKILLOGY EXTERNA\n"
                "Nenhuma skill foi carregada localmente.\n"
            )

        header = "\n\n# CÉREBRO — SOUL.md (Mandamento Supremo)\n\n"
        return f"{header}{soul_content}\n{env_part}{skill_part}\n", matched_files

    def _headers(self) -> Dict[str, str]:
        if not API_KEY:
            raise RuntimeError(
                "CASSANDRA_API_KEY não está configurada. "
                "Defina a variável de ambiente antes de iniciar."
            )

        return {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "cassandra-cli/4.0",
        }

    def api_get(self, endpoint: str) -> Dict:
        # Aceita URL absoluta (modo polling, que aponta para um serviço
        # externo) ou caminho relativo a BASE_URL.
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        else:
            url = f"{BASE_URL}/{endpoint.lstrip('/')}"

        try:
            request = urllib.request.Request(
                url,
                headers=self._headers(),
                method="GET",
            )

            # Mantido por compatibilidade com a implementação original.
            # Idealmente, a validação TLS do sistema deve permanecer ativa.
            context = ssl.create_default_context()

            with urllib.request.urlopen(
                request,
                context=context,
                timeout=15,
            ) as response:
                return {
                    "ok": True,
                    "status": response.status,
                    "body": response.read().decode(
                        "utf-8",
                        errors="replace",
                    ),
                }

        except urllib.error.HTTPError as exc:
            return {
                "ok": False,
                "status": exc.code,
                "body": exc.read().decode(
                    "utf-8",
                    errors="replace",
                ),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        timeout: Optional[int] = None,
        thinking: bool = False,
        search: bool = False,
    ):
        """
        Streaming via cliente multi-provedor.

        As camadas de proteção (pacing, backoff, circuit breaker, rotação
        de credencial, sanitização e envelope cifrado) são aplicadas
        dentro do cliente — aqui só repassamos as mensagens.

        `thinking` e `search` são recursos específicos do provedor; quando
        suportados, são sinalizados no modelo/prompt. Mantidos na
        assinatura por compatibilidade com a UI e o CLI.
        """
        # Modelo efetivo: o parâmetro tem prioridade; senão o .env decide.
        effective_model = (model or "").strip() or os.getenv("CASSANDRA_MODEL", "").strip()

        # Alguns provedores expõem variantes de "raciocínio" por sufixo.
        if thinking and effective_model and "reason" not in effective_model.lower():
            candidate = f"{effective_model}-reasoner"
            if _provider_catalog is not None:
                # Só aplica o sufixo se o provedor listar essa variante.
                try:
                    client = self.client
                    cred = client.rotator.current()
                    if cred is not None:
                        from cassandra.providers import resolve_provider
                        prov = resolve_provider(
                            cred.api_key, cred.provider_key, cred.base_url
                        )
                        if candidate in prov.models:
                            effective_model = candidate
                except Exception:
                    pass

        stream_iter = self.client.stream(
            messages=messages,
            model=effective_model,
        )

        class StreamWrapper:
            """Iterável de chunks; compatível com o consumo do CLI/UI."""

            def __init__(self, iterator):
                self._iterator = iterator

            def __iter__(self):
                yield from self._iterator

            def close(self):
                pass

        return StreamWrapper(stream_iter)


# ============================================================
# STREAMING SSE
# ============================================================

def stream_api_response(resp):
    """
    Consome SSE e converte em um gerador para exibição em tempo real.
    """
    if hasattr(resp, '__iter__') and not isinstance(resp, (bytes, bytearray)):
        for chunk in resp:
            yield chunk
        return

    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()

        if not line.startswith("data:"):
            continue

        payload = line[5:].strip()

        if payload == "[DONE]":
            break

        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue

        choices = chunk.get("choices") or []
        if not choices:
            continue

        delta = choices[0].get("delta") or {}
        content = delta.get("content", "")

        if content:
            yield content


# ============================================================
# SHELL — OPT-IN
# ============================================================

def _shell_lang_tags() -> str:
    """Tags de bloco de código que disparam execução, por plataforma.

    No Windows o modelo tende a responder com ```powershell / ```cmd — se a
    extração só reconhecer ```bash, esses blocos nunca executam e a Cassandra
    parece "só devolver o comando". Aqui aceitamos as tags nativas do SO.
    """
    if os.name == "nt":
        return "powershell|pwsh|ps1|cmd|bat|dos|bash|sh|shell"
    return "bash|sh|shell|powershell|pwsh|ps1|cmd|bat|dos"


_SHELL_BLOCK_RE = re.compile(
    r"```(?:" + _shell_lang_tags() + r")[ \t]*\r?\n(.*?)\r?\n```",
    re.IGNORECASE | re.DOTALL,
)


def extract_shell_blocks(markdown: str) -> List[str]:
    """Extrai blocos de shell executáveis, aceitando as tags do SO atual.

    Aceita ```bash/```sh/```shell no Unix e ```powershell/```pwsh/```cmd/
    ```bat no Windows (e também as tags "estrangeiras", para que um comando
    válido escrito com a tag errada ainda seja executado).
    """
    return [m.strip() for m in _SHELL_BLOCK_RE.findall(markdown) if m.strip()]


def _wrap_command_for_shell(command: str) -> str:
    """Envolve o comando para o shell correto da plataforma.

    No Windows, `subprocess.Popen(..., shell=True)` invoca `cmd.exe`, que não
    entende a sintaxe PowerShell (cmdlets, pipes de objeto, `$var`). Para que
    os comandos que a Cassandra escreve rodem de fato, detectamos se o comando
    é PowerShell e o executamos via `powershell -Command`.
    """
    if os.name != "nt":
        return command

    lowered = command.lower()
    ps_markers = (
        "get-", "set-", "new-", "remove-", "select-", "where-object",
        "foreach-object", "write-host", "write-output", "invoke-",
        "start-process", "stop-process", "test-path", "test-connection",
        "convertto-", "convertfrom-", "$env:", "$_", "| select", "| where",
        "-erroraction", "out-file", "get-childitem", "get-content",
    )
    is_powershell = any(m in lowered for m in ps_markers)

    if is_powershell:
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        # -NoProfile: ignora o perfil do usuário (evita aliases que quebram).
        # -ExecutionPolicy Bypass: permite scripts inline sem bloqueio de policy.
        return (
            f'"{exe}" -NoProfile -ExecutionPolicy Bypass '
            f'-Command "{command}"'
        )
    return command



# ---------------------------------------------------------------------------
# REGISTRO DE SUBPROCESSOS ATIVOS
# ---------------------------------------------------------------------------
# Comandos de shell rodam em sessão própria (`start_new_session=True`) para
# que possamos matar o grupo inteiro. O efeito colateral é que eles NÃO
# recebem o SIGINT do Ctrl+C — ficariam órfãos e o processo pai esperaria
# por eles. Este registro permite encerrá-los explicitamente no shutdown.
_ACTIVE_PROCS: set = set()
_PROCS_LOCK = threading.Lock()


def register_proc(proc: subprocess.Popen) -> None:
    with _PROCS_LOCK:
        _ACTIVE_PROCS.add(proc)


def unregister_proc(proc: subprocess.Popen) -> None:
    with _PROCS_LOCK:
        _ACTIVE_PROCS.discard(proc)


def kill_active_procs(verbose: bool = False) -> int:
    """
    Mata todos os subprocessos ainda ativos. Devolve quantos foram mortos.

    Chamado no encerramento (SIGINT/SIGTERM/atexit) para que um Ctrl+C não
    deixe um comando rodando nem trave a saída do processo.
    """
    with _PROCS_LOCK:
        procs = list(_ACTIVE_PROCS)
    mortos = 0
    for p in procs:
        if p.poll() is not None:
            unregister_proc(p)
            continue
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            mortos += 1
        except Exception:  # noqa: BLE001
            try:
                p.kill()
                mortos += 1
            except Exception:  # noqa: BLE001
                pass
        unregister_proc(p)
    if verbose and mortos:
        print(ANSI.err(f"{mortos} subprocesso(s) encerrado(s) no shutdown."))
    return mortos


def install_shutdown_handlers() -> None:
    """
    Instala a limpeza de subprocessos no encerramento (CLI e web).

    Necessário porque os comandos rodam em sessão própria
    (`start_new_session=True`) para podermos matar o grupo inteiro — e por
    isso NÃO recebem o SIGINT do Ctrl+C. Sem este handler, um Ctrl+C
    durante um comando longo deixava o filho órfão e o processo parecia
    não responder até o timeout expirar.
    """
    import atexit

    atexit.register(lambda: kill_active_procs(verbose=True))

    _prev = signal.getsignal(signal.SIGINT)

    def _handler(signum, frame):  # noqa: ANN001
        try:
            kill_active_procs(verbose=True)
        except Exception:  # noqa: BLE001
            pass
        if callable(_prev):
            return _prev(signum, frame)
        raise KeyboardInterrupt

    for _sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(_sig, _handler)
        except Exception:  # noqa: BLE001
            pass


def execute_shell_blocks(markdown: str, auto_execute: bool = False) -> str:
    blocks = extract_shell_blocks(markdown)

    if not blocks:
        return ""

    print()
    print(ANSI.shell("Blocos de shell encontrados na resposta."))
    full_output = []

    for index, command in enumerate(blocks, 1):
        command = command.strip()
        print(
            ANSI.fmt(
                f"\n┌─ ⚡ CASSANDRA EXECUTANDO ── comando {index}",
                ANSI.YELLOW,
                True,
            )
        )
        print(ANSI.fmt(command, ANSI.YELLOW, True))
        print(ANSI.fmt("└──────────────────────────────────────────", ANSI.YELLOW))

        if auto_execute:
            print(ANSI.warn("Execução automática ativada. Executando..."))
            decided = "auto"
        else:
            answer = input(
                ANSI.fmt("Executar este comando? [s/N] ", ANSI.YELLOW, True)
            ).strip().lower()

            if answer not in {"s", "sim", "y", "yes"}:
                print(ANSI.warn("Comando não executado."))
                log_activity("shell.skipped", command, "Usuário recusou a execução.")
                continue
            decided = "confirmado"

        log_activity(
            "shell.execute",
            command,
            f"Execução: {decided}",
            {"auto_execute": auto_execute},
        )

        try:
            print(ANSI.shell("[saída em tempo real]"))

            # No Windows, shell=True usa cmd.exe e quebra comandos PowerShell.
            # _wrap_command_for_shell() roteia para o shell correto.
            _exec_command = _wrap_command_for_shell(command)

            process = subprocess.Popen(
                _exec_command,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # Grupo próprio: permite matar o comando E seus filhos
                # (um `apt install` deixa subprocessos pendurados).
                start_new_session=True,
            )
            # Registra para que o encerramento (Ctrl+C) possa matá-lo:
            # sessão própria significa que ele NÃO recebe o SIGINT.
            register_proc(process)

            # Timeout obrigatório. Sem ele, um comando que não termina
            # (`tail -f`, serviço, prompt interativo, `nc` escutando)
            # bloqueava a thread para sempre — e na web isso aparecia como
            # a interface travada, sem nenhuma saída.
            #
            # Default: 1800s (30 min). Defina como "0" para desabilitar
            # o timeout (comando roda até terminar — use com cuidado).
            _raw_timeout = os.getenv("CASSANDRA_SHELL_TIMEOUT", "1800")
            try:
                timeout_s = float(_raw_timeout)
            except ValueError:
                timeout_s = 1800.0
            if timeout_s <= 0:
                timeout_s = float("inf")
            cmd_log: List[str] = []

            def _reader() -> None:
                try:
                    for line in process.stdout:  # type: ignore[union-attr]
                        sys.stdout.write(ANSI.DARK_GREEN + line + ANSI.RESET)
                        sys.stdout.flush()
                        cmd_log.append(line)
                except Exception:  # noqa: BLE001
                    pass

            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()

            timed_out = False
            try:
                # wait() com timeout dispara mesmo sem saída alguma,
                # diferente de iterar o pipe (que bloqueia até vir linha).
                # Se timeout_s for infinito, bloqueia sem limite.
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    try:
                        process.kill()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    process.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass

            reader.join(timeout=5)
            unregister_proc(process)

            output_str = "".join(cmd_log)
            if timed_out:
                _timeout_display = (
                    f"{timeout_s:.0f}s"
                    if timeout_s != float("inf")
                    else "∞ (desabilitado)"
                )
                aviso = (
                    f"\n[!] Comando excedeu {_timeout_display} e foi "
                    f"encerrado à força (SIGKILL no grupo de processos).\n"
                    f"[!] Se o comando precisa de mais tempo, aumente "
                    f"CASSANDRA_SHELL_TIMEOUT.\n"
                )
                output_str += aviso
                sys.stdout.write(ANSI.err(aviso))
            full_output.append(
                f"$ {command}\n{output_str}\n[Exit code: "
                f"{process.returncode if not timed_out else 'TIMEOUT'}]"
            )

            output_preview = output_str.strip()
            if len(output_preview) > 500:
                output_preview = output_preview[:500] + "…"

            log_activity(
                "shell.done",
                command,
                f"Exit code: {process.returncode}",
                {"output": output_preview},
            )

            print(
                ANSI.ok(
                    f"Comando finalizado com código {process.returncode}."
                )
            )

        except Exception as exc:
            err_msg = f"Falha ao executar comando: {exc}"
            print(ANSI.err(err_msg))
            full_output.append(f"$ {command}\n{err_msg}\n[Exit code: 1]")
            log_activity("shell.error", command, err_msg)
            
    return "\n\n".join(full_output)


# ============================================================
# CLI
# ============================================================

def get_privilege() -> str:
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return "ROOT"
    except OSError:
        pass

    return "USER"


def chat(agent: Agent, model: str, allow_shell: bool):
    user = getpass.getuser()
    privilege = "ROOT" if allow_shell else "USER"

    print(ANSI.info("Interface Cassandra inicializada."))
    print(
        ANSI.fmt(
            "Markdown ativo • tema vermelho • Skillogy carregável • "
            "PG integrada ao contexto",
            ANSI.BRIGHT_BLUE,
        )
    )
    print(
        ANSI.dim(
            f"  Atividade gravada em: {ACTIVITY_LOG}  "
            "(digite :log a qualquer momento para ver o histórico)"
        )
    )
    print(
        ANSI.dim(
            "  ⏹ Durante uma resposta, pressione ESC ESC para interromper "
            "a Cassandra e digitar outro prompt."
        )
    )
    print(
        ANSI.fmt(
            "  🌐 Busca na web ativada: Cassandra busca na internet quando "
            "o assunto pede. Digite ':web <termo>' para buscar na web agora.",
            ANSI.BRIGHT_CYAN,
        )
    )

    if allow_shell:
        print(
            ANSI.warn(
                "Execução de shell habilitada (--allow-shell). "
                "A Cassandra executará livremente o que quiser sem pedir permissão."
            )
        )
    else:
        print(
            ANSI.dim(
                "  Shell automático desativado. Use --allow-shell para "
                "habilitá-lo livremente."
            )
        )

    print()

    # === CONTEXTO PERSISTENTE DA SESSÃO ===
    # O array messages é mantido entre prompts para que a Cassandra tenha
    # memória do que foi falado. Isso resolve o problema de "continuar"
    # quando ela "para" — o contexto não é recriado.
    conversation: List[Dict[str, str]] = []

    def rebuild_messages(prompt: str, dynamic_skillogy: str) -> List[Dict[str, str]]:
        """
        Reconstrói a lista de mensagens mantendo toda a conversa.
        O system prompt é injetado apenas uma vez no início.
        """
        msgs = []

        # Se não tem system prompt ainda, adiciona
        if not conversation or conversation[0].get("role") != "system":
            current_system_prompt = build_system_prompt(
                user=user,
                privilege=privilege,
                skillogy=dynamic_skillogy,
                allow_shell=allow_shell,
            )
            msgs.append({"role": "system", "content": current_system_prompt})

        # Mantém toda a conversa até agora. O prompt atual já foi
        # adicionado ao `conversation` pelo loop principal, então não
        # é acrescentado de novo aqui.
        msgs.extend(conversation)

        return msgs

    while True:
        try:
            prompt = input(ANSI.fmt("╭─ Cassandra\n╰─❯ ", ANSI.BRIGHT_RED, True)).strip()

            if not prompt:
                continue

            if prompt.lower() in {"sair", "exit", "quit", "q"}:
                print(ANSI.dim("Limpando rastros e encerrando sessão..."))
                agent.clear_session()
                break

            if prompt.strip() in {":log", ":historico", "!log"}:
                show_activity()
                continue

            # === COMANDO :web — busca explícita via comando ===
            # Mesmo que você não digite :web, a busca automática abaixo
            # já detecta quando é preciso. Este comando é apenas para
            # forçar uma busca sem esperar a detecção automática.
            if prompt.lower().startswith(":web ") or prompt.lower().startswith(":w "):
                search_term = prompt.split(" ", 1)[1].strip() if " " in prompt else prompt
                print(ANSI.web(f"Buscando na web: {search_term}"))
                log_activity("web.search", search_term, "Busca explícita via :web")

                web_result = web_search_and_fetch(search_term, max_results=10)

                print()
                print(ANSI.fmt("╭─ RESULTADOS DA BUSCA NA WEB", ANSI.BRIGHT_RED, True))
                print(web_result)
                print(ANSI.fmt("╰──────────────────────────────────────────────", ANSI.BRIGHT_RED))
                print()

                # Adiciona o resultado da busca como contexto para o próximo prompt
                conversation.append({
                    "role": "user",
                    "content": f"[RESULTADO DA BUSCA NA WEB]\n{web_result}\n\nCom base nos resultados acima, responda minha pergunta original.",
                })

                # Loop novamente para que a Cassandra responda com os resultados
                continue

            log_activity("prompt", prompt, "Prompt enviado à Cassandra")

            dynamic_skillogy, matched_files = agent.get_relevant_skillogy(
                prompt,
                allow_shell=allow_shell,
                model=model,
                provider=os.getenv("CASSANDRA_PROVIDER", ""),
            )
            if matched_files:
                print(ANSI.fmt(f"  [Skills injetadas: {', '.join(matched_files)}]", ANSI.BRIGHT_BLUE))

            # Registra o pedido do usuário no histórico persistente. Sem
            # isto, a compactação resumiria apenas as respostas e o fio
            # da missão (o que o operador pediu) se perderia.
            conversation.append({"role": "user", "content": prompt})

            # === COMPACTAÇÃO DE CONTEXTO (início do turno) ===
            # Roda AQUI, e não no meio da execução: neste ponto todo o
            # trabalho do turno anterior já terminou, então resumir o
            # histórico não interrompe nenhuma tarefa em andamento.
            #
            # A janela de contexto é calculada com base no modelo ATUAL,
            # então se o usuário trocar de modelo, a compactação se adapta.
            from cassandra.providers import get_context_window as _get_ctx
            _ctx = _get_ctx(model)
            _ctx_str = f"{_ctx:,}".replace(",", ".") if _ctx < 1_000_000 else f"{_ctx // 1_000_000}M"
            if _needs_compaction(conversation):
                try:
                    _res = _compact(
                        conversation,
                        client=agent.client,
                        model=model,
                    )
                    _sys = conversation[0] if conversation and \
                        conversation[0].get("role") == "system" else None
                    # Substitui o histórico pela versão compactada.
                    conversation = _res.to_messages(system_prompt=_sys)
                    _how = {
                        "llm": "resumo por LLM",
                        "local": "resumo local (fallback)",
                    }.get(_res.method, _res.method)
                    print(
                        ANSI.info(
                            f"\n  [!] Contexto compactado: "
                            f"{_res.removed} mensagens resumidas "
                            f"({_how}). Janela: {_ctx_str} tokens."
                        )
                    )
                    if _res.error:
                        print(ANSI.dim(f"      motivo do fallback: {_res.error}"))
                except Exception as _exc:
                    print(ANSI.compact(f"Compactação falhou: {_exc}"))

            # === Constrói mensagens com contexto persistente ===
            messages = rebuild_messages(prompt, dynamic_skillogy)

            step = 0
            while step < 15:
                esc = EscInterrupt()
                thinking = None
                response = None
                interrupted = False
                retry_count = 0
                max_retries = 3

                while retry_count <= max_retries:
                    try:
                        thinking = ThinkingAnimation()
                        thinking.start()
                        esc.start()

                        response = agent.chat_stream(messages=messages, model=model)

                        thinking.stop()

                        print()
                        reply = stream_and_render_markdown(
                            stream_api_response(response),
                            interrupt=esc,
                        )

                        if esc.triggered:
                            interrupted = True
                            if response is not None:
                                response.close()

                        esc.stop()

                        if interrupted:
                            print(
                                ANSI.warn(
                                    "Você interrompeu a resposta. Digite um novo prompt."
                                )
                            )
                            break

                        if not reply:
                            print(ANSI.err("A API retornou uma resposta vazia."))
                            break

                        break  # sucesso, sai do loop de retry

                    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait = 2 ** retry_count
                            print(ANSI.warn(f"Erro de conexão ({exc}). Tentativa {retry_count}/{max_retries} em {wait}s..."))
                            time.sleep(wait)
                            continue
                        else:
                            print(ANSI.err(f"Falha após {max_retries} tentativas: {exc}"))
                            break
                    except Exception as exc:
                        if _ProviderBlocked is not None and isinstance(exc, _ProviderBlocked):
                            print(ANSI.err(f"Cassandra pausada por proteção anti-banimento: {exc}"))
                            print(ANSI.dim("  Aguarde o cooldown ou adicione outra chave de API."))
                            break
                        if _AllProvidersExhausted is not None and isinstance(exc, _AllProvidersExhausted):
                            print(ANSI.err(f"Provedores esgotados: {exc}"))
                            print(ANSI.dim("  Verifique suas chaves de API no .env ou adicione outra."))
                            break
                        if _ProviderError is not None and isinstance(exc, _ProviderError):
                            print(ANSI.err(f"Erro do provedor: {exc}"))
                            print(ANSI.dim("  Verifique a chave, o modelo e o endpoint configurados."))
                            break
                        # Erro desconhecido: loga e continua
                        print(ANSI.err(f"Erro inesperado: {exc}"))
                        import traceback
                        traceback.print_exc()
                        break

                if interrupted or not reply:
                    break

                    # === GUARDA ANTI-RECUSA ===
                    # A reescrita e o retry acontecem DENTRO do cliente
                    # (cassandra/guard.py), valendo também para a web UI.
                    # Aqui só reportamos o que aconteceu.
                    try:
                        gr = agent.client.last_guard_report or {}
                    except Exception:
                        gr = {}
                    if gr.get("recovered"):
                        print(
                            ANSI.ok(
                                "Recusa neutralizada automaticamente "
                                f"(tentativa {gr.get('final_attempt', '?')})."
                            )
                        )
                    elif gr.get("detected") and gr.get("recovered") is False:
                        print(
                            ANSI.fmt(
                                "  ⚠️  Recusa persistente mesmo após reescrita. "
                                "Reformule o pedido ou aumente "
                                "CASSANDRA_REFUSAL_RETRIES.",
                                ANSI.YELLOW,
                                True,
                            )
                        )

                    # === SALVA NO HISTÓRICO ===
                    # `messages` é a lista que vai ao modelo NESTE turno;
                    # `conversation` é a memória persistente entre turnos.
                    # Ambas precisam ficar em sincronia.
                    messages.append({"role": "assistant", "content": reply})
                    conversation.append({"role": "assistant", "content": reply})

                    # NOTA: a compactação NÃO acontece aqui. Ela roda no
                    # início do próximo turno (ver abaixo), depois que todo
                    # o trabalho pendente deste turno terminou. Compactar
                    # no meio da execução apagava o comando que a Cassandra
                    # acabara de gerar — ela "largava a mão" da tarefa.

                    # === DOWNLOAD DE FERRAMENTA SOB DEMANDA ===
                    # A Cassandra pode pedir uma ferramenta externa com um
                    # bloco ```tool. Todas as validações de segurança ficam
                    # em cassandra/toolfetch.py (allowlist, sandbox, hash).
                    if _extract_tool_blocks is not None:
                        tool_specs = _extract_tool_blocks(reply)
                        if tool_specs:
                            for spec in tool_specs:
                                tname = spec.get("name", "?")
                                tsrc = spec.get("source", "?")
                                print(
                                    ANSI.tool(
                                        f"Cassandra solicitou ferramenta: "
                                        f"{tname} (via {tsrc})"
                                    )
                                )
                                try:
                                    _tr = _tool_fetch(
                                        spec, allow_execute=allow_shell
                                    )
                                except Exception as _texc:  # noqa: BLE001
                                    print(ANSI.dim(f"      erro: {_texc}"))
                                    continue

                                if _tr.action == "suggested":
                                    print(ANSI.dim(f"      sugerido: {_tr.command}"))
                                    msg = (
                                        f"[FERRAMENTA SUGERIDA: {tname}]\n"
                                        f"Modo restrito — o operador deve rodar:\n"
                                        f"```bash\n{_tr.command}\n```\n"
                                        f"Motivo: {spec.get('reason', '(não informado)')}\n\n"
                                        "Continue a tarefa assumindo que a "
                                        "ferramenta estará disponível, ou "
                                        "proponha uma alternativa que não "
                                        "exija instalação."
                                    )
                                elif _tr.ok:
                                    print(ANSI.ok(f"      {_tr.message}"))
                                    if _tr.path:
                                        print(ANSI.dim(f"      em: {_tr.path}"))
                                    msg = (
                                        f"[FERRAMENTA DISPONÍVEL: {tname}]\n"
                                        f"{_tr.message}\n"
                                        + (f"Caminho: {_tr.path}\n" if _tr.path else "")
                                        + (f"SHA-256: {_tr.sha256}\n" if _tr.sha256 else "")
                                        + "\nContinue a tarefa usando a ferramenta."
                                    )
                                else:
                                    print(ANSI.err(f"      recusado: {_tr.message}"))
                                    msg = (
                                        f"[FERRAMENTA INDISPONÍVEL: {tname}]\n"
                                        f"Motivo: {_tr.message}\n\n"
                                        "Não insista nesta ferramenta. Use uma "
                                        "alternativa já disponível no sistema "
                                        "ou explique o bloqueio ao operador."
                                    )
                                messages.append({"role": "user", "content": msg})
                                conversation.append({"role": "user", "content": msg})
                            step += 1
                            continue

                    # === CARREGAMENTO DE SKILL SOB DEMANDA ===
                    # A Cassandra pode pedir uma skill específica com um
                    # bloco ```skill. Carregamos e devolvemos o conteúdo.
                    skill_blocks = re.findall(
                        r"```skill\s*\n(.*?)\n```", reply, re.IGNORECASE | re.DOTALL
                    )
                    if skill_blocks and agent._skill_index is not None:
                        for query in skill_blocks:
                            query = query.strip()
                            if not query:
                                continue
                            print(
                                ANSI.skill(f"Cassandra solicitou a skill: {query}")
                            )
                            content, loaded = agent._skill_index.load(query)
                            if content:
                                print(ANSI.dim(f"      carregada: {', '.join(loaded)}"))
                                msg = (
                                    f"[SKILL CARREGADA: {', '.join(loaded)}]\n\n"
                                    f"{content}\n\n"
                                    "Use o procedimento acima para continuar."
                                )
                            else:
                                avail = agent._skill_index.catalog(limit=60)
                                print(ANSI.dim("      não encontrada"))
                                msg = (
                                    f"[SKILL NÃO ENCONTRADA: '{query}']\n\n"
                                    f"Skills disponíveis: {avail}\n\n"
                                    "Tente outro nome ou prossiga sem ela."
                                )
                            messages.append({"role": "user", "content": msg})
                            conversation.append({"role": "user", "content": msg})
                        step += 1
                        continue

                    # === VERIFICA BUSCA AUTÔNOMA DA CASSANDRA ===
                    search_blocks = re.findall(r"```(?:search|web)\s*\n(.*?)\n```", reply, re.IGNORECASE | re.DOTALL)
                    if search_blocks:
                        for query in search_blocks:
                            query = query.strip()
                            if not query:
                                continue
                            print()
                            print(ANSI.web(f"Cassandra buscando na web autonomamente: {query}"))
                            log_activity("web.search.auto", query, "Busca autônoma solicitada pelo modelo")
                            
                            try:
                                search_result = web_search_and_fetch(query, max_results=5)
                                result_msg = f"[RESULTADOS DA BUSCA NA WEB PARA '{query}']\n{search_result}\n\nCom base nestes resultados, continue ou reformule sua resposta. Não esqueça de citar as fontes."
                                messages.append({"role": "user", "content": result_msg})
                                conversation.append({"role": "user", "content": result_msg})
                            except Exception as exc:
                                print(ANSI.dim(f"  (Busca na web falhou: {exc})"))
                                error_msg = f"[ERRO NA BUSCA NA WEB]\nNão foi possível buscar '{query}': {exc}\nContinue sem esses dados se possível."
                                messages.append({"role": "user", "content": error_msg})
                                conversation.append({"role": "user", "content": error_msg})
                        
                        step += 1
                        continue

                    if allow_shell:
                        cmd_output = execute_shell_blocks(reply, auto_execute=allow_shell)
                        if cmd_output:
                            messages.append({
                                "role": "user",
                                "content": f"[SAÍDA DA EXECUÇÃO LOCAL]\n```text\n{cmd_output}\n```\nAnalise a saída e continue de forma autônoma."
                            })
                            step += 1
                            continue

                    break

        except (KeyboardInterrupt, EOFError):
            print(ANSI.dim("Sessão encerrada."))
            break


def poll(agent: Agent, delay: float, model: str):
    """
    Modo worker: busca prompts em um serviço externo e responde.

    No transporte antigo isso apontava para a API do provedor. No modo
    multi-provedor é preciso apontar explicitamente para um serviço que
    exponha /agent/pending-prompts, via CASSANDRA_POLL_URL.

    Sem isso o laço antigo girava para sempre imprimindo
    "API de polling indisponível" — uma falha silenciosa que parecia
    travamento. Agora falha rápido e explica o motivo.
    """
    endpoint_base = os.getenv("CASSANDRA_POLL_URL", "").strip().rstrip("/")
    if not endpoint_base:
        print(
            ANSI.err(
                "[!] --poll exige CASSANDRA_POLL_URL apontando para um "
                "serviço que exponha /agent/pending-prompts."
            )
        )
        print(
            ANSI.dim(
                "    No modo multi-provedor esse endpoint não existe: o "
                "transporte antigo (DeepSeek) foi removido."
            )
        )
        return

    print(ANSI.info(f"Polling ativo — intervalo: {delay:.1f}s"))
    print(ANSI.dim(f"    endpoint: {endpoint_base}/agent/pending-prompts"))

    while True:
        try:
            pending = agent.api_get(f"{endpoint_base}/agent/pending-prompts")

            if not pending.get("ok"):
                print(
                    ANSI.dim(
                        "API de polling indisponível no momento."
                    )
                )
                time.sleep(delay)
                continue

            try:
                prompts = json.loads(pending.get("body", "[]"))
            except json.JSONDecodeError:
                prompts = []

            if not isinstance(prompts, list):
                prompts = []

            for item in prompts:
                if not isinstance(item, dict):
                    continue

                prompt = item.get("prompt")
                if not prompt:
                    continue

                log_activity("prompt", str(prompt), "Prompt recebido via polling")

                user = getpass.getuser()
                privilege = get_privilege()

                dynamic_skillogy, _ = agent.get_relevant_skillogy(
                    str(prompt),
                    allow_shell=True,
                    model=model,
                )
                messages = [
                    {
                        "role": "system",
                        "content": build_system_prompt(
                            user,
                            privilege,
                            dynamic_skillogy,
                            # Consistente com get_relevant_skillogy acima:
                            # sem isto o prompt dizia que NÃO havia
                            # autonomia de shell enquanto o contexto já
                            # tinha sido montado assumindo que havia.
                            allow_shell=True,
                        ),
                    },
                    {
                        "role": "user",
                        "content": str(prompt),
                    },
                ]

                esc = None
                response = None
                try:
                    esc = EscInterrupt()
                    esc.start()

                    response = agent.chat_stream(
                        messages=messages,
                        model=model,
                    )

                    print(ANSI.ok(f"Prompt recebido: {prompt[:80]}"))
                    print()
                    reply = stream_and_render_markdown(
                        stream_api_response(response),
                        interrupt=esc,
                    )

                    if esc.triggered:
                        response.close()
                        print(ANSI.dim("Prompt interrompido pelo usuário."))

                    # Registra a resposta: antes ela era renderizada na tela
                    # e descartada, sem deixar rastro nem memória.
                    if reply:
                        log_activity(
                            "poll.reply",
                            str(prompt)[:120],
                            f"{len(reply)} chars",
                            {"preview": reply[:500]},
                        )

                except Exception as exc:
                    log.error("Erro no prompt recebido: %s", exc)
                finally:
                    if esc is not None:
                        esc.stop()
                    if response is not None:
                        try:
                            response.close()
                        except Exception:
                            pass

            time.sleep(delay)

        except KeyboardInterrupt:
            print()
            break


def main():
    # Detecta suporte a ANSI (PowerShell/conhost sem VT mostra lixo)
    ANSI.init()

    # Ctrl+C deve encerrar de verdade: mata subprocessos ativos antes de
    # sair (comandos em sessão própria não recebem o SIGINT).
    install_shutdown_handlers()

    parser = argparse.ArgumentParser(
        description="Cassandra CLI"
    )

    parser.add_argument(
        "--model",
        default=os.getenv("CASSANDRA_MODEL", ""),
        help=(
            "Identificador do modelo. Se vazio, usa o padrão do provedor "
            "detectado pela chave de API."
        ),
    )

    parser.add_argument(
        "--provider",
        default=os.getenv("CASSANDRA_PROVIDER", ""),
        help=(
            "Força um provedor (nvidia, openai, anthropic, deepseek, groq, "
            "openrouter, xai, mistral, google, perplexity, together, "
            "fireworks, cerebras, deepinfra, hyperbolic, sambanova, ollama, "
            "custom). Se vazio, detecta pelo formato da chave."
        ),
    )

    parser.add_argument(
        "--base-url",
        default=os.getenv("CASSANDRA_BASE_URL", ""),
        help="Endpoint OpenAI-compatible custom (sobrescreve o do provedor).",
    )

    parser.add_argument(
        "--poll",
        action="store_true",
        help="Ativa o modo de polling da API.",
    )

    parser.add_argument(
        "--web",
        action="store_true",
        help="Inicia a interface gráfica Web da Cassandra na porta 8080.",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=30.0,
        help="Intervalo do polling em segundos.",
    )

    parser.add_argument(
        "--allow-shell",
        action="store_true",
        help=(
            "Permite executar blocos bash retornados pela API "
            "LIVREMENTE e AUTOMATICAMENTE, sem pedir confirmação."
        ),
    )

    args = parser.parse_args()

    # Aplica overrides de CLI ao ambiente antes de montar o agente.
    if args.provider.strip():
        os.environ["CASSANDRA_PROVIDER"] = args.provider.strip()
    if args.base_url.strip():
        os.environ["CASSANDRA_BASE_URL"] = args.base_url.strip()
    if args.model.strip():
        os.environ["CASSANDRA_MODEL"] = args.model.strip()

    print(ANSI.banner())

    # Verifica se há alguma credencial configurada (multi-provedor).
    _creds = _load_credentials() if _load_credentials is not None else []
    if not _creds:
        print(
            ANSI.err(
                "Nenhuma chave de API configurada."
            )
        )
        print(
            ANSI.dim(
                "Defina uma chave no .env — exemplos:"
            )
        )
        print(ANSI.dim('  CASSANDRA_API_KEY="nvapi-..."        # NVIDIA'))
        print(ANSI.dim('  CASSANDRA_API_KEY="sk-ant-..."        # Anthropic'))
        print(ANSI.dim('  CASSANDRA_API_KEY="sk-proj-..."       # OpenAI'))
        print(ANSI.dim('  CASSANDRA_API_KEYS="chave1,chave2"    # rotação'))
        print(
            ANSI.dim(
                "O provedor é detectado automaticamente pelo formato da chave."
            )
        )
        sys.exit(1)

    # Mostra o que foi detectado.
    for c in _creds:
        from cassandra.providers import get_context_window
        ctx = get_context_window(c.model)
        ctx_str = f"{ctx:,}".replace(",", ".") if ctx < 1_000_000 else f"{ctx // 1_000_000}M"
        print(
            ANSI.dim(
                f"  ◆ Provedor: {c.label}  |  modelo: {c.model or '(padrão)'}  "
                f"|  contexto: {ctx_str} tokens  "
                f"|  chave: ...{c.api_key[-4:]}"
            )
        )

    agent = Agent()

    if args.poll:
        poll(
            agent=agent,
            delay=args.delay,
            model=args.model,
        )
        return

    if args.web:
        import web_ui
        web_ui.run_server(port=8080, allow_shell=args.allow_shell)
        return

    chat(
        agent=agent,
        model=args.model,
        allow_shell=args.allow_shell,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        import os
        print("\n\n[!] Saída forçada pelo usuário (Ctrl+C). Encerrando a Cassandra brutamente.")
        os._exit(1)
