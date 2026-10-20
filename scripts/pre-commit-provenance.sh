#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# Pre-commit: proteção de proveniência — Cassandra
# ------------------------------------------------
# Bloqueia o commit se a marca de atribuição oficial ("Morlsara Code Nexus")
# tiver sido removida ou adulterada. Impede que um fork/refactor apague a
# proveniência sem que isso seja um ato explícito e visível.
#
# Instalar:
#   ln -sf ../../scripts/pre-commit-provenance.sh .git/hooks/pre-commit
# ou:
#   cp scripts/pre-commit-provenance.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TEST="$ROOT/tests/test_provenance.py"

if [ ! -f "$TEST" ]; then
    echo "[provenance] AVISO: $TEST não encontrado; pulando verificação." >&2
    exit 0
fi

if ! python3 "$TEST" >/dev/null 2>&1; then
    echo "" >&2
    echo "[provenance] COMMIT BLOQUEADO — marca de atribuição comprometida." >&2
    echo "[provenance] A proveniência oficial (Morlsara Code Nexus) está ausente" >&2
    echo "[provenance] ou adulterada. Rode para ver o detalhe:" >&2
    echo "[provenance]     python3 tests/test_provenance.py" >&2
    echo "[provenance] Remover a marca de forma intencional exige alterar o teste" >&2
    echo "[provenance] e ficará registrado no histórico de commits." >&2
    echo "" >&2
    exit 1
fi

exit 0
