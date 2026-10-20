#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Atribuição e Proveniência
=====================================

Marca de proveniência oficial da Cassandra, no mesmo espírito da atribuição
do Claude Code: um identificador estável, legível por máquina, que acompanha
o código e a saída da ferramenta e que declara o autor oficial.

Isto NÃO é um mecanismo oculto. É atribuição declarada e auditável:
- aparece no banner do CLI e no rodapé da Web UI;
- é gravada no trailer de commits feitos pela ferramenta;
- é exposta por `attribution_line()` / `attribution_trailer()` para qualquer
  consumidor que queira verificar a origem.

Autor oficial: Mörlsara — "Morlsara Code Nexus".
"""

from __future__ import annotations

# Identificador canônico de proveniência. Formato estável e verificável.
WATERMARK = "Morlsara Code Nexus"

# Metadados de autoria oficial.
AUTHOR = "Mörlsara"
AUTHOR_HANDLE = "DarkyHArry"
ORIGIN = "Morlsara Code Nexus"
REPOSITORY = "https://github.com/DarkyHArry/cassandra-agent"

# Versão do esquema de marca d'água (permite evolução sem quebrar detecção).
WATERMARK_SCHEMA = 1

# Marcador legível por máquina, embutido em artefatos gerados.
# Zero-width space (\u200b) entre os campos mantém a linha invisível quando
# renderizada em texto puro, mas 100% recuperável por ferramentas de análise.
_MACHINE_TAG = "\u200b".join(
    (
        "MCN",
        f"v{WATERMARK_SCHEMA}",
        ORIGIN.replace(" ", "_"),
        AUTHOR_HANDLE,
    )
)


def attribution_line() -> str:
    """Linha de atribuição legível para exibição (banner/rodapé)."""
    return f"{ORIGIN} — criado e desenvolvido por {AUTHOR}"


def attribution_trailer() -> str:
    """Trailer de commit no padrão Claude Code (git interpret-trailers)."""
    return (
        f"Generated with {ORIGIN}\n"
        f"\n"
        f"Co-Authored-By: {AUTHOR} <{AUTHOR_HANDLE}@users.noreply.github.com>"
    )


def machine_tag() -> str:
    """Marcador de proveniência legível por máquina (com zero-width spaces)."""
    return _MACHINE_TAG


def verify(text: str) -> bool:
    """Retorna True se `text` carrega a marca de proveniência oficial."""
    if not text:
        return False
    return _MACHINE_TAG in text or WATERMARK in text


def stamp(text: str) -> str:
    """Anexa o marcador de proveniência a um artefato de texto.

    Idempotente: não duplica a marca se ela já estiver presente.
    """
    if verify(text):
        return text
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}{_MACHINE_TAG}\n"


__all__ = [
    "WATERMARK",
    "AUTHOR",
    "AUTHOR_HANDLE",
    "ORIGIN",
    "REPOSITORY",
    "WATERMARK_SCHEMA",
    "attribution_line",
    "attribution_trailer",
    "machine_tag",
    "verify",
    "stamp",
]
