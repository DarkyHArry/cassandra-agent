#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x build/dragon-cassandra ]] || { echo "Execute primeiro: ./desktop/build-debian.sh"; exit 1; }
[[ -x .venv/bin/python ]] || { echo "Prepare: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
backend_pid=""
if ! curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
  echo "Iniciando Cassandra em modo autônomo (--allow-shell)."
  .venv/bin/python agent.py --web --allow-shell &
  backend_pid=$!
  trap 'if [[ -n "$backend_pid" ]]; then kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true; fi' EXIT INT TERM
  ready=0
  for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1; then ready=1; break; fi
    kill -0 "$backend_pid" 2>/dev/null || { echo "O backend Cassandra encerrou inesperadamente."; exit 1; }
    sleep 0.5
  done
  [[ "$ready" -eq 1 ]] || { echo "Timeout aguardando a API em http://127.0.0.1:8080"; exit 1; }
else
  echo "Backend já ativo. A interface usará as permissões e o modo desse processo existente."
fi
./build/dragon-cassandra
