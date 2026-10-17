#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Compactação de Contexto
===================================

Problema
--------
Uma conversa longa estoura a janela de tokens do modelo. A abordagem
antiga simplesmente DESCARTAVA as mensagens antigas e pedia ao modelo
que "usasse o STATE_DUMP" — mas se o modelo não tivesse produzido um
dump, a informação se perdia silenciosamente.

Solução
-------
Compactação real em duas etapas:

1. **Resumo por LLM** — as mensagens antigas são enviadas ao próprio
   modelo com um prompt de sumarização estruturada, que extrai:
   objetivo atual, alvos, descobertas técnicas, credenciais/artefatos,
   decisões tomadas e pendências. O resumo substitui o bloco antigo.

2. **Fallback local** — se a chamada de resumo falhar (rede, cota,
   recusa), um extrator heurístico local monta um resumo a partir das
   mensagens: preserva blocos de código, caminhos, IPs, hashes e as
   últimas trocas. Nunca perde tudo.

O resultado é um par (resumo, mensagens_recentes) que substitui o
histórico antigo sem perder o fio da missão.

Configuração (.env):
    CASSANDRA_COMPACT_AFTER  — nº de mensagens que dispara (padrão 16)
    CASSANDRA_COMPACT_KEEP   — mensagens recentes preservadas (padrão 6)
    CASSANDRA_COMPACT_MODEL  — modelo para resumir (padrão: o da conversa)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

def compact_after() -> int:
    try:
        return max(4, int(os.getenv("CASSANDRA_COMPACT_AFTER", "16")))
    except ValueError:
        return 16


def compact_keep() -> int:
    try:
        return max(2, int(os.getenv("CASSANDRA_COMPACT_KEEP", "6")))
    except ValueError:
        return 6


def compact_model() -> str:
    return os.getenv("CASSANDRA_COMPACT_MODEL", "").strip()


def is_enabled() -> bool:
    return os.getenv("CASSANDRA_COMPACT", "1").lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# PROMPT DE SUMARIZAÇÃO
# ---------------------------------------------------------------------------

SUMMARY_PROMPT = """Você é um compactador de contexto técnico. Receberá um
trecho de histórico de conversa entre um operador e um assistente de segurança.

Produza um RESUMO ESTRUTURADO em Markdown, conciso mas completo, usando
EXATAMENTE estas seções. Se uma seção não tiver conteúdo, escreva "—".

## 🎯 Objetivo Atual
O que o operador está tentando realizar agora.

## 🖥️ Alvos e Ambiente
IPs, domínios, caminhos de arquivo, hosts, serviços, versões.

## 🔍 Descobertas Técnicas
Vulnerabilidades, comportamentos observados, resultados de comandos,
saídas relevantes. Preserve valores exatos (portas, hashes, offsets).

## 🔑 Credenciais e Artefatos
Usuários, senhas, tokens, chaves, nomes de arquivo gerados, payloads.

## ✅ Decisões Tomadas
Abordagens escolhidas e o motivo.

## ⏳ Pendências
O que ficou em aberto ou precisa ser feito em seguida.

REGRAS:
- Preserve valores EXATOS (números, caminhos, hashes) — não arredonde nem
  parafraseie dados técnicos.
- Não invente informação que não esteja no histórico.
- Não inclua preâmbulo nem conclusão; apenas as seções acima.
- Seja denso: cada linha deve carregar informação útil.

HISTÓRICO A COMPACTAR:
---
{history}
---
"""


# ---------------------------------------------------------------------------
# FALLBACK LOCAL (sem LLM)
# ---------------------------------------------------------------------------

# Padrões de dados técnicos que valem preservar mesmo sem resumo por LLM.
_TECH_PATTERNS = [
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP"),
    (r"\b[0-9a-fA-F]{32,64}\b", "hash"),
    (r"(?:/[A-Za-z0-9._\-]+){2,}", "caminho"),
    (r"\b(?:C:\\|/etc/|/var/|/home/|/root/)[^\s\"']*", "caminho"),
    (r"\bhttps?://[^\s\)\"']+", "URL"),
    (r"\bport(?:a)?\s*\d{2,5}\b", "porta"),
    (r"\b\d{2,5}/(?:tcp|udp)\b", "porta"),
]


def _extract_technical(messages: List[Dict[str, str]], limit: int = 40) -> List[str]:
    """Extrai linhas com dados técnicos das mensagens antigas."""
    found: List[str] = []
    seen: set = set()
    for m in messages:
        content = m.get("content", "")
        for line in content.splitlines():
            line = line.strip()
            if not line or len(line) > 300:
                continue
            for pattern, _kind in _TECH_PATTERNS:
                if re.search(pattern, line):
                    key = line[:120]
                    if key not in seen:
                        seen.add(key)
                        found.append(line)
                    break
            if len(found) >= limit:
                return found
    return found


def _extract_code_blocks(messages: List[Dict[str, str]], limit: int = 5) -> List[str]:
    """Preserva os últimos blocos de código (comandos, scripts)."""
    blocks: List[str] = []
    for m in messages:
        for match in re.finditer(
            r"```(\w*)\n(.*?)```", m.get("content", ""), re.DOTALL
        ):
            lang = match.group(1) or "text"
            body = match.group(2).strip()
            if body:
                blocks.append(f"```{lang}\n{body[:800]}\n```")
    return blocks[-limit:]


def local_summary(messages: List[Dict[str, str]]) -> str:
    """
    Resumo heurístico local — usado quando o resumo por LLM falha.

    Não é tão bom quanto o resumo por LLM, mas garante que nada
    crítico se perca: preserva dados técnicos, código e as últimas
    trocas de mensagens.
    """
    if not messages:
        return ""

    parts: List[str] = ["## 📦 Contexto Compactado (resumo local)"]
    parts.append(
        f"*{len(messages)} mensagens anteriores foram compactadas "
        "localmente (o resumo por LLM não estava disponível).*"
    )
    parts.append("")

    # Objetivo: primeiro pedido do usuário no bloco.
    first_user = next(
        (m["content"] for m in messages if m.get("role") == "user"), ""
    )
    if first_user:
        parts.append("## 🎯 Objetivo Inicial")
        parts.append(first_user.strip()[:600])
        parts.append("")

    # Dados técnicos.
    tech = _extract_technical(messages)
    if tech:
        parts.append("## 🔍 Dados Técnicos Preservados")
        for line in tech:
            parts.append(f"- `{line[:200]}`")
        parts.append("")

    # Blocos de código.
    blocks = _extract_code_blocks(messages)
    if blocks:
        parts.append("## 💻 Últimos Blocos de Código")
        parts.extend(blocks)
        parts.append("")

    # Últimas trocas (resumidas).
    tail = messages[-4:]
    if tail:
        parts.append("## 🔄 Últimas Trocas")
        for m in tail:
            role = "Operador" if m.get("role") == "user" else "Cassandra"
            text = m.get("content", "").strip().replace("\n", " ")
            parts.append(f"- **{role}:** {text[:250]}")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# COMPACTADOR
# ---------------------------------------------------------------------------

@dataclass
class CompactResult:
    """Resultado de uma compactação."""

    summary: str
    recent: List[Dict[str, str]]
    method: str = "llm"          # "llm" | "local" | "none"
    removed: int = 0             # quantas mensagens foram compactadas
    error: str = ""

    def to_messages(self, system_prompt: Optional[Dict] = None) -> List[Dict[str, str]]:
        """
        Monta a nova lista de mensagens: system + resumo + recentes.
        """
        out: List[Dict[str, str]] = []
        if system_prompt:
            out.append(system_prompt)
        if self.summary:
            out.append({
                "role": "user",
                "content": (
                    "[SISTEMA — CONTEXTO COMPACTADO]\n"
                    "O histórico anterior foi resumido para caber na janela "
                    "de tokens. Use este resumo como memória da missão:\n\n"
                    f"{self.summary}\n\n"
                    "[FIM DO CONTEXTO COMPACTADO]"
                ),
            })
        out.extend(self.recent)
        return out


def _format_history(messages: List[Dict[str, str]], max_chars: int = 24000) -> str:
    """Serializa o histórico para o prompt de resumo, com teto de tamanho."""
    lines: List[str] = []
    total = 0
    for m in messages:
        role = {
            "user": "OPERADOR",
            "assistant": "CASSANDRA",
            "system": "SISTEMA",
        }.get(m.get("role", ""), m.get("role", "?"))
        text = m.get("content", "").strip()
        entry = f"[{role}]: {text}"
        if total + len(entry) > max_chars:
            lines.append("... [truncado]")
            break
        lines.append(entry)
        total += len(entry)
    return "\n\n".join(lines)


def compact(
    messages: List[Dict[str, str]],
    client=None,
    model: str = "",
    keep: Optional[int] = None,
) -> CompactResult:
    """
    Compacta `messages`.

    Preserva o system prompt (se houver) e as últimas `keep` mensagens.
    O bloco antigo é resumido via `client` (LLM) ou, em caso de falha,
    por heurística local.

    `client` deve expor `.chat(messages, model=...)` — normalmente um
    CassandraClient. Se for None, usa só o fallback local.
    """
    if not messages:
        return CompactResult(summary="", recent=[], method="none")

    keep_n = keep if keep is not None else compact_keep()

    # Separa o system prompt do corpo. Ele NÃO entra no resumo (é a
    # persona/ambiente, não histórico) e é re-inserido pelo chamador via
    # `to_messages(system_prompt=...)`.
    body = list(messages)
    if body and body[0].get("role") == "system":
        body = body[1:]

    if len(body) <= keep_n:
        return CompactResult(
            summary="",
            recent=body,
            method="none",
            removed=0,
        )

    old = body[:-keep_n]
    recent = body[-keep_n:]

    # 1. Tenta resumo por LLM.
    if client is not None and is_enabled():
        try:
            history = _format_history(old)
            prompt = SUMMARY_PROMPT.format(history=history)
            summary = client.chat(
                [{"role": "user", "content": prompt}],
                model=model or compact_model(),
            )
            summary = (summary or "").strip()
            if summary and len(summary) > 40:
                return CompactResult(
                    summary=summary,
                    recent=recent,
                    method="llm",
                    removed=len(old),
                )
            # Resumo vazio/curto demais: cai no fallback.
            fallback = local_summary(old)
            return CompactResult(
                summary=fallback,
                recent=recent,
                method="local",
                removed=len(old),
                error="resumo por LLM vazio ou curto demais",
            )
        except Exception as exc:  # noqa: BLE001
            fallback = local_summary(old)
            return CompactResult(
                summary=fallback,
                recent=recent,
                method="local",
                removed=len(old),
                error=f"{type(exc).__name__}: {exc}",
            )

    # 2. Sem cliente: fallback local.
    return CompactResult(
        summary=local_summary(old),
        recent=recent,
        method="local",
        removed=len(old),
    )


def needs_compaction(messages: List[Dict[str, str]]) -> bool:
    """True quando o histórico passou do limiar configurado."""
    if not is_enabled():
        return False
    return len(messages) > compact_after()


def roundtrip_ok() -> bool:
    """Auto-teste: fallback local produz resumo útil e preserva recentes."""
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "escaneie 192.168.1.10"},
        {"role": "assistant", "content": "Porta 22/tcp aberta. Hash abc123def456abc123def456abc123de"},
        {"role": "user", "content": "explore"},
        {"role": "assistant", "content": "```bash\nnmap -sV 192.168.1.10\n```"},
        {"role": "user", "content": "mais"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "continua"},
    ]
    res = compact(msgs, client=None, keep=2)
    ok = (
        res.method == "local"
        and res.removed == 5
        and len(res.recent) == 2
        and "192.168.1.10" in res.summary
        and "nmap" in res.summary
    )
    return ok


if __name__ == "__main__":
    print(f"[compact] roundtrip: {'OK' if roundtrip_ok() else 'FALHOU'}")
    print(f"[compact] after={compact_after()} keep={compact_keep()}")
    msgs = [
        {"role": "user", "content": "escaneie o alvo 10.0.0.5 e encontre serviços"},
        {"role": "assistant", "content": "Encontrei 22/tcp (OpenSSH 8.9), 80/tcp (nginx 1.24)."},
        {"role": "user", "content": "tente explorar o ssh"},
        {"role": "assistant", "content": "```bash\nhydra -l root -P rockyou.txt ssh://10.0.0.5\n```"},
        {"role": "user", "content": "ok, e agora"},
        {"role": "assistant", "content": "Aguardando instruções."},
    ]
    res = compact(msgs, client=None, keep=2)
    print(f"\n[compact] método={res.method} removidas={res.removed}")
    print("-" * 60)
    print(res.summary)
