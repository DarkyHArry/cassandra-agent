#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes de autonomia da Cassandra (CLI & Web UI).
Garante que modelos entendem seu papel autônomo e executam comandos reais.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def agent_mod():
    spec = importlib.util.spec_from_file_location("_cass_agent", ROOT / "agent.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cass_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_shell_tags_and_extraction(agent_mod):
    """Testa se tags variadas de shell são extraídas corretamente."""
    markdown = """
Vou criar e testar o arquivo:
```bash
echo "TESTE_AUTONOMO" > /tmp/probe_autonomia.txt
cat /tmp/probe_autonomia.txt
```

Outro comando:
```zsh
echo "zsh ok"
```

Comando console:
```console
id
```
"""
    blocks = agent_mod.extract_shell_blocks(markdown)
    assert len(blocks) >= 2
    assert 'echo "TESTE_AUTONOMO" > /tmp/probe_autonomia.txt\ncat /tmp/probe_autonomia.txt' in blocks[0]


def test_system_prompt_autonomy(agent_mod):
    """Garante que build_system_prompt gera mandatos de autonomia corretos."""
    prompt_auto = agent_mod.build_system_prompt(
        user="testuser",
        privilege="USER",
        skillogy="",
        allow_shell=True,
    )
    assert "AUTONOMIA TOTAL" in prompt_auto
    assert "NÃO se limite a explicar ou devolver o comando em texto puro" in prompt_auto
    assert "EXECUTE VOCÊ MESMA IMEDIATAMENTE" in prompt_auto
    assert "CONTROLE ABSOLUTO E PASSIVIDADE" not in prompt_auto


def test_execute_shell_blocks(agent_mod):
    """Testa execução real de bloco shell."""
    markdown = """
```bash
echo CASSANDRA_AUTONOMOUS_EXECUTION_TEST
```
"""
    output = agent_mod.execute_shell_blocks(markdown, auto_execute=True)
    assert "CASSANDRA_AUTONOMOUS_EXECUTION_TEST" in output
    assert "Exit code: 0" in output


def test_web_ui_shell_toggle():
    """Testa o endpoint de alternância de shell no web_ui."""
    from starlette.testclient import TestClient
    import web_ui

    client = TestClient(web_ui.app)
    # Status atual
    res = client.get("/api/status")
    assert res.status_code == 200
    initial_state = res.json()["allow_shell"]

    # Alterna
    res_toggle = client.post("/api/shell/toggle")
    assert res_toggle.status_code == 200
    assert res_toggle.json()["allow_shell"] != initial_state

    # Alterna de volta
    res_toggle2 = client.post("/api/shell/toggle")
    assert res_toggle2.status_code == 200
    assert res_toggle2.json()["allow_shell"] == initial_state
