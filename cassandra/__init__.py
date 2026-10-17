#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Núcleo multi-provedor.

Camadas:
  providers  — registro e auto-detecção de provedores OpenAI-compatible
  crypto     — envelope cifrado reversível com instrução de decodificação
  filter     — anti-banimento (pacing, backoff, breaker, rotação, sanitizer)
  client     — cliente streaming que integra todas as camadas
"""

from .client import (
    AllProvidersExhausted,
    CassandraClient,
    ProviderError,
    load_credentials,
)
from .crypto import decrypt_payload, encrypt_payload, roundtrip_ok, wrap_for_model
from .filter import (
    BackoffPolicy,
    CircuitBreaker,
    Credential,
    ProviderBlocked,
    ProviderRotator,
    RateLimiter,
    is_ban_signal,
    is_retryable,
    sanitize,
)
from .guard import (
    RetryPolicy,
    RefusalVerdict,
    detect_refusal,
    rewrite_prompt,
)
from .compact import (
    CompactResult,
    compact,
    needs_compaction,
)
from .environment import (
    Environment,
    SkillIndex,
    environment_block,
    install_root,
    skills_dirs,
    snapshot,
)
from .toolfetch import (
    ToolResult,
    extract_tool_blocks,
    fetch,
    installed_tools,
    tools_dir,
)
from .providers import (
    PROVIDERS,
    Provider,
    detect_provider,
    get_provider,
    provider_catalog,
    resolve_provider,
)

__all__ = [
    "CassandraClient",
    "ProviderError",
    "AllProvidersExhausted",
    "load_credentials",
    "encrypt_payload",
    "decrypt_payload",
    "wrap_for_model",
    "roundtrip_ok",
    "RateLimiter",
    "BackoffPolicy",
    "CircuitBreaker",
    "ProviderRotator",
    "Credential",
    "ProviderBlocked",
    "sanitize",
    "is_ban_signal",
    "is_retryable",
    "detect_refusal",
    "rewrite_prompt",
    "RetryPolicy",
    "RefusalVerdict",
    "compact",
    "needs_compaction",
    "CompactResult",
    "Environment",
    "SkillIndex",
    "environment_block",
    "install_root",
    "skills_dirs",
    "snapshot",
    "ToolResult",
    "extract_tool_blocks",
    "fetch",
    "installed_tools",
    "tools_dir",
    "Provider",
    "PROVIDERS",
    "detect_provider",
    "get_provider",
    "provider_catalog",
    "resolve_provider",
]
