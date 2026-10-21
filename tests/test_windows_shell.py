#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regressão — execução autônoma no Windows (PowerShell/CMD)
=========================================================

Bug corrigido: no Windows a Cassandra "só devolvia o comando digitado" e não
agia. Causa: `extract_shell_blocks` reconhecia apenas ```bash/```sh/```shell,
então blocos ```powershell/```cmd nunca eram executados; e a execução usava
`shell=True` (cmd.exe), que não entende sintaxe PowerShell.

Este teste trava o comportamento correto:

    python tests/test_windows_shell.py

Exit 0 = OK, 1 = regressão detectada.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_failures: list[str] = []


def _check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  [+] {msg}")
    else:
        print(f"  [-] FALHA: {msg}")
        _failures.append(msg)


def _load_agent():
    """Carrega agent.py sem executar main() (bloco __main__ protegido)."""
    spec = importlib.util.spec_from_file_location("_cass_agent", ROOT / "agent.py")
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cass_agent"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] não foi possível importar agent.py: {exc}")
        return None
    return mod


try:
    import pytest
    @pytest.fixture
    def agent():
        return _load_agent()
except ImportError:
    pass


def test_extraction(agent) -> None:
    print("== extração de blocos ==")
    reply = (
        "Vou executar:\n\n"
        "```powershell\nGet-Process | Select -First 3\n```\n\n"
        "```cmd\ndir /a\n```\n\n"
        "```bash\nls -la\n```\n"
    )
    blocks = agent.extract_shell_blocks(reply)
    _check(len(blocks) == 3, f"extrai 3 blocos (powershell/cmd/bash) — obtido {len(blocks)}")
    _check(any("Get-Process" in b for b in blocks), "bloco ```powershell extraído")
    _check(any(b.strip() == "dir /a" for b in blocks), "bloco ```cmd extraído")
    _check(any("ls -la" in b for b in blocks), "bloco ```bash extraído")

    # Blocos não-shell não devem ser executados.
    _check(agent.extract_shell_blocks("```python\nprint(1)\n```") == [],
           "bloco ```python NÃO é executado")
    _check(agent.extract_shell_blocks("```\necho x\n```") == [],
           "bloco sem tag NÃO é executado")


def test_windows_wrapper(agent) -> None:
    print("== roteamento de shell no Windows ==")
    orig = os.name
    try:
        agent.os.name = "nt"
        ps = agent._wrap_command_for_shell("Get-Process | Select -First 3")
        _check("powershell" in ps.lower() and "-Command" in ps,
               "cmdlet PowerShell roteado para powershell -Command")
        ps_env = agent._wrap_command_for_shell("echo $env:PATH")
        _check("powershell" in ps_env.lower(),
               "uso de $env: roteado para PowerShell")
        cmd = agent._wrap_command_for_shell("dir /a")
        _check(cmd == "dir /a", "comando CMD permanece inalterado")
    finally:
        agent.os.name = orig

    # No Unix, nada é alterado.
    _check(agent._wrap_command_for_shell("ls -la") == "ls -la",
           "no Linux o comando não é alterado")


def main() -> int:
    print("\nRegressão — shell no Windows\n")
    agent = _load_agent()
    if agent is None:
        print("RESULTADO: não foi possível carregar agent.py.")
        return 1
    test_extraction(agent)
    test_windows_wrapper(agent)
    print()
    if _failures:
        print(f"RESULTADO: {len(_failures)} falha(s) — regressão detectada.")
        return 1
    print("RESULTADO: execução Windows OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
