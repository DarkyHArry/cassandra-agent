#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x build/dragon-cassandra ]] || { echo "Execute primeiro: ./desktop/build-debian.sh"; exit 1; }
[[ -x .venv/bin/python ]] || { echo "Prepare: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
backend_pid=""
if ! curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
  .venv/bin/python agent.py --web & backend_pid=$!
  trap 'if [[ -n "$backend_pid" ]]; then kill "$backend_pid" 2>/dev/null || true; fi' EXIT INT TERM
  for _ in $(seq 1 40); do curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1 && break; sleep 0.5; done
fi
./build/dragon-cassandra