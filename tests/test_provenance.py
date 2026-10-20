#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proteção de proveniência — Cassandra
====================================

Teste de integridade da marca de atribuição oficial ("Morlsara Code Nexus").

Objetivo: falhar de forma explícita se um fork, refactor ou "limpeza" remover
ou adulterar a marca de proveniência. A marca é declarada e auditável — este
teste garante que ela permaneça presente nos pontos de exposição.

Executa sem pytest (python puro):

    python tests/test_provenance.py

Retorna código 0 se a proveniência estiver íntegra, 1 caso contrário.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Valores canônicos esperados. Alterar a marca exige alterar este teste —
# o que é um ato deliberado e visível no histórico de commits.
EXPECTED_ORIGIN = "Morlsara Code Nexus"
EXPECTED_AUTHOR = "Mörlsara"
EXPECTED_HANDLE = "DarkyHArry"

_failures: list[str] = []


def _check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  [+] {msg}")
    else:
        print(f"  [-] FALHA: {msg}")
        _failures.append(msg)


def _load_attribution():
    """Carrega cassandra/attribution.py isolado (sem importar o pacote)."""
    path = ROOT / "cassandra" / "attribution.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_cass_attr", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_module_present() -> None:
    print("== módulo de atribuição ==")
    attr = _load_attribution()
    _check(attr is not None, "cassandra/attribution.py existe")
    if attr is None:
        return
    _check(getattr(attr, "WATERMARK", None) == EXPECTED_ORIGIN,
           f"WATERMARK == {EXPECTED_ORIGIN!r}")
    _check(getattr(attr, "AUTHOR", None) == EXPECTED_AUTHOR,
           f"AUTHOR == {EXPECTED_AUTHOR!r}")
    _check(getattr(attr, "AUTHOR_HANDLE", None) == EXPECTED_HANDLE,
           f"AUTHOR_HANDLE == {EXPECTED_HANDLE!r}")

    # A API de verificação precisa funcionar e detectar a marca.
    _check(attr.verify(attr.machine_tag()), "verify() reconhece a marca")
    _check(not attr.verify("texto sem marca alguma"), "verify() rejeita texto limpo")
    stamped = attr.stamp("artefato")
    _check(attr.verify(stamped), "stamp() aplica marca verificável")
    _check(attr.stamp(stamped) == stamped, "stamp() é idempotente")


def test_exposure_points() -> None:
    """A marca deve aparecer no banner do CLI e no rodapé da Web UI."""
    print("== pontos de exposição ==")

    agent_src = (ROOT / "agent.py").read_text(encoding="utf-8")
    _check("attribution_line" in agent_src,
           "agent.py usa attribution_line() no banner")
    _check("Morlsara Code Nexus" in agent_src,
           "agent.py contém a marca (fallback do banner)")

    web_src = (ROOT / "web_ui.py").read_text(encoding="utf-8")
    _check("Morlsara Code Nexus" in web_src,
           "web_ui.py contém a marca no rodapé")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    _check("Morlsara Code Nexus" in readme,
           "README.md documenta a marca")
    _check("Provenance" in readme or "Attribution" in readme,
           "README.md tem seção de proveniência")


def test_no_scrubbed_mark() -> None:
    """A marca não pode ter sido esvaziada/neutralizada silenciosamente."""
    print("== integridade da marca ==")
    attr = _load_attribution()
    if attr is None:
        return
    tag = attr.machine_tag()
    _check(bool(tag.strip()), "machine_tag() não está vazio")
    # A tag precisa carregar o identificador de autor legível por máquina.
    _check(EXPECTED_HANDLE in tag,
           f"machine_tag() carrega o handle {EXPECTED_HANDLE}")
    _check(EXPECTED_ORIGIN.replace(" ", "_") in tag,
           "machine_tag() carrega a origem")


def main() -> int:
    print(f"\nProteção de proveniência — {EXPECTED_ORIGIN}\n")
    test_module_present()
    test_exposure_points()
    test_no_scrubbed_mark()
    print()
    if _failures:
        print(f"RESULTADO: {len(_failures)} falha(s) — proveniência comprometida.")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("RESULTADO: proveniência íntegra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
