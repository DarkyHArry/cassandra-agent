#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Provider Registry
=============================

Registro de provedores compatíveis com a API OpenAI Chat Completions
(`/chat/completions`). Cobre NVIDIA NIM, DeepSeek, OpenAI, Anthropic
(compat layer), Groq, Mistral, OpenRouter, Together, xAI, Google Gemini
(compat layer), Perplexity, Fireworks, Cerebras, SambaNova, Hyperbolic,
DeepInfra e qualquer endpoint OpenAI-compatible custom.

Responsabilidades:
  * auto-detecção do provedor pelo formato da chave de API;
  * endpoint base, modelos e headers específicos por provedor;
  * override manual (provedor + base_url + modelo) via .env / CLI / UI.

Nenhuma chave é versionada. Toda chave vem de .env, variável de ambiente
ou do formulário da interface web.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Provider:
    """Um provedor OpenAI-compatible."""

    key: str                       # identificador interno (ex.: "nvidia")
    label: str                     # nome exibido na interface
    base_url: str                  # endpoint raiz, sem barra final
    env_var: str                   # variável de ambiente da chave
    default_model: str             # modelo usado quando nenhum é informado
    models: List[str] = field(default_factory=list)
    # Padrões regex aplicados à chave para auto-detecção. O primeiro
    # provedor cujo padrão casar vence.
    key_patterns: List[str] = field(default_factory=list)
    # Headers extras exigidos pelo provedor (ex.: Anthropic exige
    # anthropic-version; OpenRouter aceita HTTP-Referer).
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Alguns provedores não aceitam o parâmetro "stream_options".
    supports_stream_options: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# REGISTRO
# ---------------------------------------------------------------------------
# A ordem importa: a auto-detecção percorre a lista e usa o primeiro
# provedor cujo regex casar com a chave. Padrões mais específicos primeiro.

PROVIDERS: List[Provider] = [
    Provider(
        key="nvidia",
        label="NVIDIA NIM",
        base_url="https://integrate.api.nvidia.com/v1",
        env_var="NVIDIA_API_KEY",
        default_model="nvidia/nemotron-3-super-120b-a12b",
        models=[
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "deepseek-ai/deepseek-v4.1-flash",
            "stepfun-ai/step-5-preview",
            "stepfun-ai/step-3.7-flash",
        ],
        key_patterns=[r"^nvapi-"],
        notes="Chaves começam com 'nvapi-'. A disponibilidade dos modelos "
              "varia por conta — confirme com GET /v1/models.",
    ),
    Provider(
        key="deepseek",
        label="DeepSeek API",
        base_url="https://api.deepseek.com/v1",
        env_var="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        key_patterns=[r"^sk-[0-9a-f]{32}$"],
        notes="Chave 'sk-' + 32 hexadecimais.",
    ),
    Provider(
        key="anthropic",
        label="Anthropic (Claude)",
        base_url="https://api.anthropic.com/v1",
        env_var="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-20250514",
        models=[
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-haiku-20241022",
        ],
        key_patterns=[r"^sk-ant-"],
        extra_headers={"anthropic-version": "2023-06-01"},
        supports_stream_options=False,
        notes="Chaves começam com 'sk-ant-'. Usa a camada OpenAI-compatible.",
    ),
    Provider(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        env_var="OPENAI_API_KEY",
        default_model="gpt-4o",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"],
        key_patterns=[r"^sk-proj-", r"^sk-[A-Za-z0-9_\-]{40,}$"],
        notes="Chaves 'sk-proj-' ou 'sk-' longas.",
    ),
    Provider(
        key="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        default_model="deepseek/deepseek-chat",
        models=[
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
        ],
        key_patterns=[r"^sk-or-"],
        extra_headers={"HTTP-Referer": "https://localhost", "X-Title": "Cassandra"},
        notes="Chaves começam com 'sk-or-'.",
    ),
    Provider(
        key="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        env_var="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "deepseek-r1-distill-llama-70b",
            "qwen-2.5-32b",
        ],
        key_patterns=[r"^gsk_"],
        notes="Chaves começam com 'gsk_'.",
    ),
    Provider(
        key="xai",
        label="xAI (Grok)",
        base_url="https://api.x.ai/v1",
        env_var="XAI_API_KEY",
        default_model="grok-2-latest",
        models=["grok-2-latest", "grok-2-1212", "grok-beta"],
        key_patterns=[r"^xai-"],
        notes="Chaves começam com 'xai-'.",
    ),
    Provider(
        key="mistral",
        label="Mistral AI",
        base_url="https://api.mistral.ai/v1",
        env_var="MISTRAL_API_KEY",
        default_model="mistral-large-latest",
        models=[
            "mistral-large-latest",
            "mistral-medium-latest",
            "codestral-latest",
            "open-mixtral-8x22b",
        ],
        key_patterns=[],
        notes="Sem prefixo fixo — selecione manualmente.",
    ),
    Provider(
        key="google",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        env_var="GEMINI_API_KEY",
        default_model="gemini-2.0-flash",
        models=["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        key_patterns=[r"^AIza[0-9A-Za-z_\-]{35}$"],
        notes="Chaves começam com 'AIza'.",
    ),
    Provider(
        key="perplexity",
        label="Perplexity",
        base_url="https://api.perplexity.ai",
        env_var="PERPLEXITY_API_KEY",
        default_model="sonar-pro",
        models=["sonar-pro", "sonar", "sonar-reasoning"],
        key_patterns=[r"^pplx-"],
        notes="Chaves começam com 'pplx-'.",
    ),
    Provider(
        key="together",
        label="Together AI",
        base_url="https://api.together.xyz/v1",
        env_var="TOGETHER_API_KEY",
        default_model="deepseek-ai/DeepSeek-V3",
        models=[
            "deepseek-ai/DeepSeek-V3",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ],
        key_patterns=[],
        notes="Sem prefixo fixo — selecione manualmente.",
    ),
    Provider(
        key="fireworks",
        label="Fireworks AI",
        base_url="https://api.fireworks.ai/inference/v1",
        env_var="FIREWORKS_API_KEY",
        default_model="accounts/fireworks/models/deepseek-v3",
        models=[
            "accounts/fireworks/models/deepseek-v3",
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
        ],
        key_patterns=[r"^fw_"],
        notes="Chaves começam com 'fw_'.",
    ),
    Provider(
        key="cerebras",
        label="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        env_var="CEREBRAS_API_KEY",
        default_model="llama-3.3-70b",
        models=["llama-3.3-70b", "llama3.1-8b", "qwen-3-32b"],
        key_patterns=[r"^csk-"],
        notes="Chaves começam com 'csk-'.",
    ),
    Provider(
        key="deepinfra",
        label="DeepInfra",
        base_url="https://api.deepinfra.com/v1/openai",
        env_var="DEEPINFRA_API_KEY",
        default_model="deepseek-ai/DeepSeek-V3",
        models=[
            "deepseek-ai/DeepSeek-V3",
            "meta-llama/Llama-3.3-70B-Instruct",
        ],
        key_patterns=[],
        notes="Sem prefixo fixo — selecione manualmente.",
    ),
    Provider(
        key="hyperbolic",
        label="Hyperbolic",
        base_url="https://api.hyperbolic.xyz/v1",
        env_var="HYPERBOLIC_API_KEY",
        default_model="deepseek-ai/DeepSeek-V3",
        models=["deepseek-ai/DeepSeek-V3", "meta-llama/Llama-3.3-70B-Instruct"],
        key_patterns=[],
        notes="Sem prefixo fixo — selecione manualmente.",
    ),
    Provider(
        key="sambanova",
        label="SambaNova",
        base_url="https://api.sambanova.ai/v1",
        env_var="SAMBANOVA_API_KEY",
        default_model="Meta-Llama-3.3-70B-Instruct",
        models=["Meta-Llama-3.3-70B-Instruct", "DeepSeek-R1"],
        key_patterns=[],
        notes="Sem prefixo fixo — selecione manualmente.",
    ),
    Provider(
        key="ollama",
        label="Ollama (local)",
        base_url="http://127.0.0.1:11434/v1",
        env_var="OLLAMA_API_KEY",
        default_model="llama3.3",
        models=["llama3.3", "qwen2.5-coder", "deepseek-r1"],
        key_patterns=[],
        notes="Servidor local — qualquer chave é aceita.",
    ),
    Provider(
        key="custom",
        label="Custom (OpenAI-compatible)",
        base_url="",
        env_var="CASSANDRA_API_KEY",
        default_model="",
        models=[],
        key_patterns=[],
        notes="Defina CASSANDRA_BASE_URL e CASSANDRA_MODEL no .env.",
    ),
]

PROVIDER_MAP: Dict[str, Provider] = {p.key: p for p in PROVIDERS}


# ---------------------------------------------------------------------------
# AUTO-DETECÇÃO
# ---------------------------------------------------------------------------

def detect_provider(api_key: str) -> Optional[Provider]:
    """Detecta o provedor pelo formato da chave. None se nenhum casar."""
    key = (api_key or "").strip()
    if not key:
        return None
    for provider in PROVIDERS:
        for pattern in provider.key_patterns:
            if re.match(pattern, key):
                return provider
    return None


def get_provider(key: str) -> Optional[Provider]:
    return PROVIDER_MAP.get((key or "").strip().lower())


def resolve_provider(
    api_key: str,
    provider_hint: str = "",
    base_url_override: str = "",
) -> Provider:
    """
    Resolve o provedor efetivo, na ordem:
      1. provider_hint explícito (CLI / UI / .env CASSANDRA_PROVIDER);
      2. auto-detecção pelo formato da chave;
      3. CASSANDRA_BASE_URL definido no .env;
      4. fallback genérico 'custom'.

    Sempre devolve um Provider — nunca None — para que o cliente tenha
    um base_url utilizável. O base_url é sobrescrito quando há override.
    """
    provider: Optional[Provider] = None

    if provider_hint:
        provider = get_provider(provider_hint)

    if provider is None:
        provider = detect_provider(api_key)

    if provider is None:
        env_base = os.getenv("CASSANDRA_BASE_URL", "").strip()
        if env_base:
            provider = get_provider("custom")
        else:
            provider = get_provider("custom")

    # Copia para não mutar o registro global.
    resolved = Provider(
        key=provider.key,
        label=provider.label,
        base_url=provider.base_url,
        env_var=provider.env_var,
        default_model=provider.default_model,
        models=list(provider.models),
        key_patterns=list(provider.key_patterns),
        extra_headers=dict(provider.extra_headers),
        supports_stream_options=provider.supports_stream_options,
        notes=provider.notes,
    )

    override = (base_url_override or os.getenv("CASSANDRA_BASE_URL", "")).strip()
    if override:
        resolved.base_url = override.rstrip("/")

    if not resolved.base_url:
        resolved.base_url = "https://integrate.api.nvidia.com/v1"

    return resolved


def provider_catalog() -> List[Dict]:
    """Catálogo serializável para a interface web."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "base_url": p.base_url,
            "default_model": p.default_model,
            "models": p.models,
            "env_var": p.env_var,
            "notes": p.notes,
            "detectable": bool(p.key_patterns),
        }
        for p in PROVIDERS
    ]
