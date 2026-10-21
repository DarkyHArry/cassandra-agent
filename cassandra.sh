#!/usr/bin/env bash
# ============================================================
# Cassandra — wrapper de execução (Linux / macOS / Termux)
# ------------------------------------------------------------
# Uso:
#   ./cassandra.sh              # CLI interativa (autonomia padrão)
#   ./cassandra.sh --web        # Interface web em :8080
#   ./cassandra.sh --allow-shell
#   ./cassandra.sh --model <id> # Força um modelo específico
# ============================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PY="$VENV/bin/python"

# Preserva HOME do usuário caso executado sob sudo
if [[ -n "${SUDO_USER:-}" && -d "/home/$SUDO_USER" ]]; then
    export HOME="/home/$SUDO_USER"
fi

# Prepara ambiente virtual ou usa python3 do sistema (Termux / fallback)
if [[ ! -x "$PY" ]]; then
    echo "[*] Preparando ambiente Python..."
    if python3 -m venv "$VENV" 2>/dev/null; then
        "$VENV/bin/pip" install -q -r "$DIR/requirements.txt" || true
    else
        echo "[!] Criação de venv não suportada ou ausente (ex: Termux). Usando python3 do sistema..."
        PY="$(command -v python3 || echo "python3")"
        pip install -q -r "$DIR/requirements.txt" 2>/dev/null || true
    fi
fi

if [[ ! -f "$DIR/.env" ]]; then
    if [[ -f "$DIR/.env.example" ]]; then
        echo "[*] Criando .env a partir de .env.example..."
        cp "$DIR/.env.example" "$DIR/.env"
    else
        echo "[!] .env ausente. Copie .env.example e configure suas chaves."
        exit 1
    fi
fi

cd "$DIR"
exec "$PY" agent.py "$@"
