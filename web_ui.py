#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Interface Web
=========================

Servidor FastAPI que expõe a Cassandra multi-provedor via navegador.

Endpoints:
  GET  /                 — interface
  GET  /api/status       — estado (shell, provedor ativo, criptografia)
  GET  /api/providers    — catálogo de provedores e modelos
  POST /api/credentials  — define a chave de API em tempo de execução
  POST /api/clear        — limpa o histórico local
  POST /api/chat         — streaming da resposta

A chave de API pode ser definida no .env OU colada na interface. Quando
colada, fica apenas em memória do processo — nunca é gravada em disco.
"""

import asyncio
import getpass
import os
import platform
import re
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agent import (
    Agent,
    build_system_prompt,
    execute_shell_blocks,
    extract_shell_blocks,
    install_shutdown_handlers,
    kill_active_procs,
)

try:
    from cassandra.client import (
        AllProvidersExhausted,
        ProviderError,
        load_credentials,
    )
    from cassandra.filter import Credential, ProviderBlocked
    from cassandra.providers import provider_catalog, resolve_provider
    from cassandra.compact import compact, needs_compaction
    from cassandra.toolfetch import (
        extract_tool_blocks,
        fetch as tool_fetch,
    )
    CORE_OK = True
except ImportError as _exc:  # pragma: no cover
    CORE_OK = False
    _CORE_ERR = str(_exc)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOW_SHELL = False

# Valor de CASSANDRA_PROVIDER vindo do .env, guardado antes de qualquer
# override da interface. Sem isto, escolher um provedor no seletor e depois
# voltar para "— provedor —" (auto) deixava o valor antigo preso no
# ambiente, e o auto-detect nunca voltava a valer.
_ENV_PROVIDER_DEFAULT = os.getenv("CASSANDRA_PROVIDER", "").strip()

# Credencial definida em runtime pela interface (só em memória).
RUNTIME_CREDENTIALS = []


def _active_credentials():
    """Credenciais efetivas: as da interface têm prioridade sobre o .env."""
    if RUNTIME_CREDENTIALS:
        return list(RUNTIME_CREDENTIALS)
    return load_credentials() if CORE_OK else []


HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cassandra | Interface</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js"></script>
    <style>
        :root {
            --bg-color: #050505;
            --accent-red: #ff003c;
            --accent-dark-red: #8a0021;
            --text-main: #e0e0e0;
            --glass-bg: rgba(20, 0, 5, 0.85);
            --border-glow: 0 0 10px rgba(255, 0, 60, 0.4);
            --ok-green: #00c46a;
        }

        * { box-sizing: border-box; }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'JetBrains Mono', monospace;
            margin: 0; padding: 0;
            height: 100vh;
            display: flex; flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        body::before {
            content: "";
            position: absolute;
            top: -50%; left: -50%; width: 200%; height: 200%;
            background-image:
                radial-gradient(circle at 50% 50%, #200008 0%, transparent 40%),
                linear-gradient(rgba(255, 0, 60, 0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 0, 60, 0.05) 1px, transparent 1px);
            background-size: 100% 100%, 40px 40px, 40px 40px;
            animation: moveBackground 40s linear infinite;
            z-index: -1;
        }

        @keyframes moveBackground {
            0% { transform: translate(0, 0); }
            100% { transform: translate(40px, 40px); }
        }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: var(--accent-dark-red); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--accent-red); }

        .header {
            padding: 0.9rem 2rem;
            border-bottom: 2px solid var(--accent-dark-red);
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 30px rgba(255,0,60,0.15);
            position: relative; z-index: 10;
            display: flex; justify-content: space-between;
            align-items: center; gap: 1rem; flex-wrap: wrap;
        }

        .brand { display: flex; align-items: center; gap: 1.5rem; }

        .brand-text h1 {
            color: var(--accent-red);
            font-size: 1.6rem; font-weight: 700; margin: 0;
            text-transform: uppercase; letter-spacing: 4px;
            text-shadow: var(--border-glow);
            animation: glitch 4s infinite;
        }

        .brand-text .subtitle {
            font-size: 0.65rem; color: #888;
            margin-top: 2px; letter-spacing: 2px;
        }

        .controls {
            display: flex; flex-direction: column;
            align-items: flex-end; gap: 8px;
        }

        .controls-top {
            display: flex; gap: 12px;
            align-items: center; flex-wrap: wrap;
            justify-content: flex-end;
        }

        .cyber-btn {
            background: transparent;
            border: 1px solid var(--accent-dark-red);
            color: var(--text-main);
            padding: 5px 12px;
            font-family: inherit; font-size: 0.78rem;
            cursor: pointer; border-radius: 3px;
            transition: all 0.2s; white-space: nowrap;
        }

        .cyber-btn:hover {
            background: rgba(255,0,60,0.1);
            border-color: var(--accent-red);
            color: var(--accent-red);
        }

        .warning-banner {
            display: none;
            background: rgba(255, 0, 0, 0.2);
            color: #ff3333;
            border: 1px solid #ff0000;
            padding: 4px 10px; border-radius: 3px;
            font-size: 0.68rem; font-weight: bold;
            animation: pulse 2s infinite;
        }

        .status-pill {
            font-size: 0.7rem; padding: 4px 10px;
            border-radius: 3px; border: 1px solid #333;
            color: #888; white-space: nowrap;
        }
        .status-pill.ok { border-color: var(--ok-green); color: var(--ok-green); }
        .status-pill.bad { border-color: var(--accent-red); color: var(--accent-red); }

        .cyber-select, .cyber-input {
            background: #111; color: var(--text-main);
            border: 1px solid #333;
            padding: 5px 8px;
            font-family: inherit; font-size: 0.78rem;
            outline: none; border-radius: 3px;
            max-width: 260px;
        }
        .cyber-select:focus, .cyber-input:focus { border-color: var(--accent-red); }

        .cyber-checkbox {
            font-size: 0.78rem; display: flex;
            align-items: center; gap: 5px;
            color: #aaa; cursor: pointer; white-space: nowrap;
        }
        .cyber-checkbox input { display: none; }
        .cyber-checkbox .emoji {
            filter: grayscale(100%) opacity(0.5);
            transition: all 0.3s;
        }
        .cyber-checkbox input:checked + .emoji {
            filter: grayscale(0%) opacity(1);
            animation: pulseEmoji 1s infinite;
        }
        @keyframes pulseEmoji {
            0% { transform: scale(1); filter: drop-shadow(0 0 2px #00ff00); }
            50% { transform: scale(1.2); filter: drop-shadow(0 0 8px #00ff00); }
            100% { transform: scale(1); filter: drop-shadow(0 0 2px #00ff00); }
        }

        /* Modal */
        .modal-overlay {
            display: none; position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(5px);
            z-index: 100;
            justify-content: center; align-items: center;
        }
        .modal {
            background: #0d0d0d;
            border: 1px solid var(--accent-red);
            border-radius: 8px;
            width: 620px; max-width: 92vw;
            max-height: 88vh; overflow-y: auto;
            display: flex; flex-direction: column;
            box-shadow: 0 0 30px rgba(255,0,60,0.2);
        }
        .modal-header {
            padding: 1rem 1.2rem;
            border-bottom: 1px solid #333;
            display: flex; justify-content: space-between;
            align-items: center;
        }
        .modal-title { margin: 0; color: var(--accent-red); font-size: 1.1rem; }
        .close-btn { background: none; border: none; color: #888; cursor: pointer; font-size: 1.5rem; }
        .close-btn:hover { color: #fff; }
        .modal-body {
            padding: 1.2rem;
            display: flex; flex-direction: column; gap: 1rem;
        }
        .field-label {
            font-size: 0.72rem; color: #888;
            text-transform: uppercase; letter-spacing: 1px;
            margin-bottom: 4px; display: block;
        }
        .field-input {
            width: 100%; background: #050505;
            color: var(--accent-red);
            border: 1px solid #333;
            padding: 0.6rem; font-family: inherit;
            font-size: 0.85rem; border-radius: 4px;
        }
        .field-input:focus { border-color: var(--accent-red); outline: none; }
        .field-hint { font-size: 0.68rem; color: #666; margin-top: 4px; }
        .modal-footer {
            padding: 1rem 1.2rem;
            border-top: 1px solid #333;
            display: flex; justify-content: flex-end; gap: 10px;
        }
        .btn-confirm {
            background: var(--accent-red); color: #fff;
            border: none; padding: 0.55rem 1.4rem;
            cursor: pointer; border-radius: 4px;
            font-weight: bold; font-family: inherit; font-size: 0.82rem;
        }
        .btn-confirm:hover { background: #ff3366; }
        .btn-ghost {
            background: transparent; color: #aaa;
            border: 1px solid #333; padding: 0.55rem 1.2rem;
            cursor: pointer; border-radius: 4px;
            font-family: inherit; font-size: 0.82rem;
        }
        .btn-ghost:hover { border-color: var(--accent-red); color: var(--accent-red); }

        .provider-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 6px; margin-top: 6px;
        }
        .provider-chip {
            border: 1px solid #333; border-radius: 4px;
            padding: 6px 8px; font-size: 0.7rem;
            cursor: pointer; text-align: center;
            transition: all 0.2s; color: #aaa;
        }
        .provider-chip:hover { border-color: var(--accent-red); color: var(--accent-red); }
        .provider-chip.active {
            border-color: var(--accent-red);
            background: rgba(255,0,60,0.12);
            color: var(--accent-red); font-weight: bold;
        }
        .provider-chip .det {
            display: block; font-size: 0.6rem; color: #555; margin-top: 2px;
        }

        .chat-container {
            flex: 1; overflow-y: auto;
            padding: 2rem;
            display: flex; flex-direction: column;
            gap: 1.5rem; z-index: 5;
        }

        /* Botão flutuante: aparece só quando o usuário rolou para cima. */
        .scroll-down-btn {
            position: fixed; right: 2.2rem; bottom: 120px;
            width: 44px; height: 44px; border-radius: 50%;
            background: var(--accent-red); color: #fff; border: none;
            font-size: 1.25rem; line-height: 1; cursor: pointer;
            z-index: 60; display: none;
            box-shadow: 0 4px 14px rgba(0,0,0,0.55);
            transition: filter 0.15s;
        }
        .scroll-down-btn:hover { filter: brightness(1.25); }

        /* Botão de parada: visível só enquanto há resposta em andamento. */
        .stop-btn {
            display: none;
            background: var(--accent-dark-red);
            border: 1px solid var(--accent-red);
        }
        .stop-btn:hover { background: var(--accent-red); }

        /* Aviso transitório (anexos, erros de leitura). */
        .toast {
            position: fixed; right: 2.2rem; bottom: 175px;
            max-width: 380px; padding: 0.8rem 1rem;
            background: #1b1b1b; color: #eee;
            border: 1px solid var(--accent-red); border-radius: 6px;
            font-size: 0.82rem; line-height: 1.45; z-index: 70;
            display: none; white-space: pre-wrap;
            box-shadow: 0 6px 18px rgba(0,0,0,0.6);
        }

        .message {
            max-width: 85%; padding: 1.2rem;
            border-radius: 8px; line-height: 1.6;
            position: relative;
            opacity: 0; animation: fadeIn 0.3s forwards;
            word-wrap: break-word; font-size: 0.95rem;
        }

        .message.user {
            align-self: flex-end;
            background: rgba(255, 0, 60, 0.05);
            border: 1px solid var(--accent-dark-red);
            color: #ddd; border-bottom-right-radius: 0;
            box-shadow: inset 0 0 10px rgba(255,0,60,0.05);
            backdrop-filter: blur(5px);
        }

        .message.cassandra {
            align-self: flex-start;
            background: rgba(10, 0, 0, 0.7);
            border-left: 4px solid var(--accent-red);
            color: var(--text-main);
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            backdrop-filter: blur(5px);
            padding-top: 1.5rem;
        }

        .message.cassandra::before {
            content: 'CASSANDRA_SYS';
            position: absolute; top: 0.5rem; left: 1.2rem;
            font-size: 0.68rem; color: var(--accent-red);
            font-weight: bold; letter-spacing: 2px;
            opacity: 0.9;
        }

        .message.user::before {
            content: 'OPERATOR';
            position: absolute; top: 0.5rem; right: 1.2rem;
            font-size: 0.68rem; color: var(--accent-dark-red);
            font-weight: bold; letter-spacing: 2px;
            opacity: 0.9;
        }

        .message.user { padding-top: 1.5rem; }

        .message.cassandra p { margin-top: 0; }
        .message.cassandra pre {
            background: #0a0a0a; padding: 1rem;
            border-radius: 5px; border: 1px solid #222;
            overflow-x: auto;
            border-left: 2px solid var(--accent-red);
            margin: 1rem 0;
        }
        .message.cassandra code {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(255,0,60,0.15);
            padding: 0.1rem 0.4rem;
            border-radius: 3px; color: #ff88a0;
            font-size: 0.9em;
        }
        .message.cassandra pre code { background: none; padding: 0; color: inherit; }
        .message.cassandra table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        .message.cassandra th, .message.cassandra td { border: 1px solid #333; padding: 0.5rem; text-align: left; }
        .message.cassandra th { background: rgba(255,0,60,0.1); color: var(--accent-red); }

        /* ===== Colorização de palavras específicas ===== */
        .tok-ip      { color: #4dd0e1; font-weight: bold; }   /* IPs / hosts */
        .tok-path    { color: #ffb74d; }                       /* caminhos de arquivo */
        .tok-cmd     { color: #81c784; font-weight: bold; }    /* comandos */
        .tok-hash    { color: #ba68c8; }                       /* hashes / tokens */
        .tok-port    { color: #4fc3f7; }                       /* portas */
        .tok-url     { color: #64b5f6; text-decoration: underline; }
        .tok-warn    { color: #ff5252; font-weight: bold; }    /* avisos */
        .tok-ok      { color: #00e676; font-weight: bold; }    /* sucesso */
        .tok-key     { color: #ffd54f; font-weight: bold; }    /* credenciais */
        .tok-cve     { color: #ff7043; font-weight: bold; }    /* CVE */
        .tok-skill   { color: #ce93d8; font-weight: bold; }    /* nomes de skill */
        .tok-root    { color: #ff1744; font-weight: bold; text-shadow: 0 0 6px rgba(255,23,68,0.6); }

        /* Destaque de linha de alerta */
        .msg-alert {
            background: rgba(255, 0, 60, 0.08);
            border-left: 3px solid var(--accent-red);
            padding: 0.4rem 0.8rem;
            margin: 0.5rem 0;
            border-radius: 0 4px 4px 0;
        }

        .input-area {
            padding: 1.5rem 2rem;
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            border-top: 1px solid var(--accent-dark-red);
            display: flex; gap: 1rem;
            align-items: flex-end; z-index: 10;
        }

        .input-wrapper {
            flex: 1; display: flex;
            background: #0a0a0a;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 0.8rem 1rem;
            align-items: flex-start;
            transition: all 0.3s ease;
            min-height: 54px;
        }

        .input-wrapper:focus-within {
            border-color: var(--accent-red);
            box-shadow: 0 0 15px rgba(255,0,60,0.2);
        }

        .prompt-prefix {
            color: var(--accent-red);
            font-weight: bold; font-size: 1.1rem;
            margin-right: 0.5rem;
            user-select: none; line-height: 1.4;
        }

        .input-box {
            flex: 1; background: transparent;
            border: none; color: #fff;
            padding: 0; margin: 0;
            font-family: inherit; font-size: 1.1rem;
            line-height: 1.4; resize: none;
            height: 1.4em; max-height: 200px;
            overflow-y: auto;
        }
        .input-box:focus { outline: none; }

        .send-btn {
            background: var(--accent-red); color: #fff;
            border: none; height: 54px;
            padding: 0 2.5rem;
            font-family: inherit; font-weight: bold;
            font-size: 1.1rem; border-radius: 4px;
            cursor: pointer; transition: all 0.3s ease;
            text-transform: uppercase; letter-spacing: 2px;
        }
        .send-btn:hover { background: #ff3366; box-shadow: 0 0 15px rgba(255,0,60,0.6); }
        .send-btn:disabled { background: #333; color: #666; cursor: not-allowed; box-shadow: none; }

        .typing-indicator {
            display: inline-block;
            color: var(--accent-red);
            font-size: 0.9rem;
            animation: pulse 1s infinite;
        }
        .typing-indicator::after {
            content: '█';
            animation: blink 1s step-start infinite;
        }
        @keyframes blink { 50% { opacity: 0; } }

        /* ===== BLOCOS DE PENSAMENTO E RESPOSTA ===== */

        /* Painel de raciocínio — separado visualmente da resposta */
        .reasoning-panel {
            background: linear-gradient(135deg, rgba(20,10,30,0.75), rgba(10,5,15,0.75));
            border: 1px solid rgba(160, 100, 220, 0.28);
            border-left: 3px solid #a06ee0;
            border-radius: 6px;
            margin: 0 0 1.1rem 0;
            overflow: hidden;
            transition: border-color 0.25s;
        }
        .reasoning-panel[open] {
            border-color: rgba(160, 100, 220, 0.5);
        }

        .reasoning-panel > summary {
            list-style: none;
            cursor: pointer;
            padding: 0.6rem 0.9rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            font-size: 0.78rem;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            color: #b98ee8;
            user-select: none;
            background: rgba(160, 100, 220, 0.07);
            transition: background 0.2s;
        }
        .reasoning-panel > summary::-webkit-details-marker { display: none; }
        .reasoning-panel > summary:hover {
            background: rgba(160, 100, 220, 0.14);
            color: #d0aaff;
        }
        .reasoning-panel > summary .chev {
            margin-left: auto;
            transition: transform 0.25s;
            font-size: 0.7rem;
            opacity: 0.7;
        }
        .reasoning-panel[open] > summary .chev { transform: rotate(90deg); }

        .reasoning-body {
            padding: 0.9rem 1rem;
            font-size: 0.86rem;
            line-height: 1.65;
            color: #b0a8bd;
            border-top: 1px solid rgba(160, 100, 220, 0.18);
            max-height: 420px;
            overflow-y: auto;
        }
        .reasoning-body p { margin: 0 0 0.6rem 0; }
        .reasoning-body p:last-child { margin-bottom: 0; }
        .reasoning-body code {
            background: rgba(160,100,220,0.14);
            color: #d9b8ff;
            padding: 0.05rem 0.35rem;
            border-radius: 3px;
            font-size: 0.85em;
        }
        .reasoning-body strong { color: #c9a8f0; }

        /* Indicador de raciocínio em andamento */
        .reasoning-live {
            display: flex; align-items: center; gap: 12px;
            padding: 0.7rem 0.9rem;
            background: rgba(160, 100, 220, 0.08);
            border: 1px solid rgba(160, 100, 220, 0.25);
            border-left: 3px solid #a06ee0;
            border-radius: 6px;
            margin-bottom: 1.1rem;
        }
        .reasoning-live .cyber-spinner {
            border-top-color: #a06ee0;
            border-bottom-color: #a06ee0;
        }
        .reasoning-live .label {
            color: #b98ee8; font-size: 0.78rem;
            text-transform: uppercase; letter-spacing: 1.2px;
            animation: pulse-op 1.6s infinite;
        }

        .cyber-spinner {
            width: 16px; height: 16px;
            border: 2px solid transparent;
            border-top-color: var(--accent-red);
            border-bottom-color: var(--accent-red);
            border-radius: 50%;
            animation: cyber-spin 1s linear infinite;
            flex-shrink: 0;
        }
        @keyframes cyber-spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @keyframes pulse-op {
            0% { opacity: 0.5; } 50% { opacity: 1; } 100% { opacity: 0.5; }
        }

        /* Divisor entre raciocínio e resposta final */
        .answer-divider {
            display: flex; align-items: center; gap: 0.7rem;
            margin: 0.2rem 0 1rem 0;
            font-size: 0.7rem; letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--accent-red);
            font-weight: bold;
        }
        .answer-divider::before,
        .answer-divider::after {
            content: "";
            flex: 1; height: 1px;
            background: linear-gradient(90deg, transparent, var(--accent-dark-red), transparent);
        }

        /* Corpo da resposta final */
        .answer-body { position: relative; }
        .answer-body > *:first-child { margin-top: 0; }
        .answer-body > *:last-child { margin-bottom: 0; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0% { opacity: 0.7; } 50% { opacity: 1; } 100% { opacity: 0.7; } }
        @keyframes glitch {
            0% { text-shadow: 0.05em 0 0 rgba(255,0,0,0.75), -0.05em -0.025em 0 rgba(0,255,0,0.75), -0.025em 0.05em 0 rgba(0,0,255,0.75); }
            14% { text-shadow: 0.05em 0 0 rgba(255,0,0,0.75), -0.05em -0.025em 0 rgba(0,255,0,0.75), -0.025em 0.05em 0 rgba(0,0,255,0.75); }
            15% { text-shadow: -0.05em -0.025em 0 rgba(255,0,0,0.75), 0.025em 0.025em 0 rgba(0,255,0,0.75), -0.05em -0.05em 0 rgba(0,0,255,0.75); }
            49% { text-shadow: -0.05em -0.025em 0 rgba(255,0,0,0.75), 0.025em 0.025em 0 rgba(0,255,0,0.75), -0.05em -0.05em 0 rgba(0,0,255,0.75); }
            50% { text-shadow: 0.025em 0.05em 0 rgba(255,0,0,0.75), 0.05em 0 0 rgba(0,255,0,0.75), 0 -0.05em 0 rgba(0,0,255,0.75); }
            99% { text-shadow: 0.025em 0.05em 0 rgba(255,0,0,0.75), 0.05em 0 0 rgba(0,255,0,0.75), 0 -0.05em 0 rgba(0,0,255,0.75); }
            100% { text-shadow: -0.025em 0 0 rgba(255,0,0,0.75), -0.025em -0.025em 0 rgba(0,255,0,0.75), -0.025em -0.05em 0 rgba(0,0,255,0.75); }
        }
    </style>
</head>
<body>

    <div class="header">
        <div class="brand">
            <div class="brand-text">
                <h1 class="title">CASSANDRA</h1>
                <div class="subtitle">MULTI-PROVIDER SYSTEM INTERFACE</div>
            </div>
        </div>
        <div class="controls">
            <div class="controls-top">
                <span id="shellWarning" class="warning-banner">⚠ SHELL AUTOMÁTICO ATIVO</span>
                <span id="providerStatus" class="status-pill">verificando...</span>
                <span id="cryptoStatus" class="status-pill">—</span>
                <button class="cyber-btn" id="configBtn">⚙ CONFIGURAR API</button>
                <button class="cyber-btn" id="clearBtn">LIMPAR SESSÃO</button>
            </div>
            <div class="controls-top">
                <select id="providerSelect" class="cyber-select" title="Provedor">
                    <option value="">— provedor —</option>
                </select>
                <select id="modelSelect" class="cyber-select" title="Modelo">
                    <option value="">— modelo —</option>
                </select>
            </div>
        </div>
    </div>

    <div class="chat-container" id="chat">
        <div class="message cassandra">
            <p><strong>Status:</strong> ONLINE.</p>
            <p>Interface multi-provedor operacional. Configure a chave de API em <strong>⚙ CONFIGURAR API</strong> ou no arquivo <code>.env</code>.</p>
            <p>O provedor é detectado automaticamente pelo formato da chave.</p>
        </div>
    </div>

    <button id="scrollDownBtn" class="scroll-down-btn" title="Ir para o fim (novas mensagens)">↓</button>
    <div id="toast" class="toast"></div>

    <div class="input-area">
        <div class="input-wrapper">
            <span class="prompt-prefix" id="promptPrefix">user@cassandra:~$</span>
            <textarea id="prompt" class="input-box" placeholder="Digite seu comando..." rows="1" autofocus></textarea>
        </div>
        <div style="position: relative;">
            <button type="button" id="attachBtn" class="send-btn" title="Anexar arquivo" style="cursor:pointer; padding:0 15px; margin-right:10px; background:#333; height:54px; font-size:1.2rem; border:none; color:#fff;">📎</button>
            <div id="attachMenu" style="display:none; position:absolute; bottom:60px; left:0; background:#222; border:1px solid var(--accent-red); border-radius:5px; flex-direction:column; overflow:hidden; z-index:100; min-width:150px; box-shadow:0 4px 6px rgba(0,0,0,0.5);">
                <label for="fileUploadBtn" style="padding:10px 15px; cursor:pointer; color:#fff; border-bottom:1px solid #444; margin:0; display:block; font-size:0.85rem;">📄 Arquivos</label>
                <label for="folderUploadBtn" style="padding:10px 15px; cursor:pointer; color:#fff; margin:0; display:block; font-size:0.85rem;">📁 Pasta</label>
            </div>
            <input type="file" id="fileUploadBtn" style="display:none;" multiple>
            <input type="file" id="folderUploadBtn" style="display:none;" webkitdirectory directory multiple>
        </div>
        <button id="stopBtn" class="send-btn stop-btn" title="Parar a resposta e poder reescrever (Esc)">⏹ Parar</button>
        <button id="sendBtn" class="send-btn">Enviar</button>
    </div>

    <!-- MODAL DE CONFIGURAÇÃO -->
    <div class="modal-overlay" id="configModal">
        <div class="modal">
            <div class="modal-header">
                <h3 class="modal-title">⚙ CONFIGURAÇÃO DE API</h3>
                <button class="close-btn" id="closeConfig">&times;</button>
            </div>
            <div class="modal-body">
                <div>
                    <label class="field-label">Chave de API</label>
                    <input type="password" id="apiKeyInput" class="field-input" placeholder="nvapi-... | sk-ant-... | sk-proj-... | gsk_...">
                    <div class="field-hint">Fica apenas em memória do processo. Nunca é gravada em disco.</div>
                </div>
                <div>
                    <label class="field-label">Provedor detectado</label>
                    <input type="text" id="detectedProvider" class="field-input" readonly placeholder="(digite a chave)">
                    <div class="field-hint">Detecção automática pelo formato. Escolha abaixo para forçar um provedor.</div>
                </div>
                <div>
                    <label class="field-label">Forçar provedor (opcional)</label>
                    <div class="provider-grid" id="providerGrid"></div>
                </div>
                <div>
                    <label class="field-label">Endpoint custom (opcional)</label>
                    <input type="text" id="baseUrlInput" class="field-input" placeholder="https://meu-endpoint/v1">
                </div>
                <div>
                    <label class="field-label">Modelo (opcional)</label>
                    <input type="text" id="modelInput" class="field-input" placeholder="deixe vazio para usar o padrão do provedor">
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-ghost" id="cancelConfig">Cancelar</button>
                <button class="btn-confirm" id="saveConfig">Aplicar</button>
            </div>
        </div>
    </div>

    <script>
        const chat = document.getElementById('chat');
        const promptInput = document.getElementById('prompt');
        const sendBtn = document.getElementById('sendBtn');
        const stopBtn = document.getElementById('stopBtn');

        // ------------------------------------------------------------------
        // Controle de envio / parada
        // ------------------------------------------------------------------
        // Permite abortar uma resposta em andamento (envio acidental, prompt
        // errado, modelo travado). Ao parar, o servidor também interrompe o
        // trabalho — não só a tela.
        let pedidoAtual = null;   // AbortController da requisição em curso
        let paradoPeloUsuario = false;

        function enviando() {
            return pedidoAtual !== null;
        }

        function marcarEnviando(ativo) {
            if (sendBtn) sendBtn.style.display = ativo ? 'none' : '';
            if (stopBtn) stopBtn.style.display = ativo ? 'inline-block' : 'none';
            promptInput.disabled = ativo;
        }

        function pararEnvio() {
            if (!pedidoAtual) return;
            paradoPeloUsuario = true;
            try {
                pedidoAtual.abort();
            } catch (e) { /* já abortado */ }
        }
        const shellWarning = document.getElementById('shellWarning');
        const promptPrefix = document.getElementById('promptPrefix');
        const providerStatus = document.getElementById('providerStatus');
        const cryptoStatus = document.getElementById('cryptoStatus');
        const providerSelect = document.getElementById('providerSelect');
        const modelSelect = document.getElementById('modelSelect');
        const clearBtn = document.getElementById('clearBtn');
        const configBtn = document.getElementById('configBtn');
        const configModal = document.getElementById('configModal');
        const closeConfig = document.getElementById('closeConfig');
        const cancelConfig = document.getElementById('cancelConfig');
        const saveConfig = document.getElementById('saveConfig');
        const apiKeyInput = document.getElementById('apiKeyInput');
        const detectedProvider = document.getElementById('detectedProvider');
        const baseUrlInput = document.getElementById('baseUrlInput');
        const modelInput = document.getElementById('modelInput');
        const providerGrid = document.getElementById('providerGrid');
        const attachBtn = document.getElementById('attachBtn');
        const attachMenu = document.getElementById('attachMenu');

        let CATALOG = [];
        let FORCED_PROVIDER = '';

        attachBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            attachMenu.style.display = attachMenu.style.display === 'none' ? 'flex' : 'none';
        });
        document.addEventListener('click', () => { attachMenu.style.display = 'none'; });

        // ---------- CATÁLOGO DE PROVEDORES ----------
        async function loadCatalog() {
            const r = await fetch('/api/providers');
            const data = await r.json();
            CATALOG = data.providers || [];

            providerSelect.innerHTML = '<option value="">— provedor —</option>';
            providerGrid.innerHTML = '';
            CATALOG.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.key;
                opt.textContent = p.label;
                providerSelect.appendChild(opt);

                const chip = document.createElement('div');
                chip.className = 'provider-chip';
                chip.dataset.key = p.key;
                const ctxStr = p.context_window >= 1000000
                    ? (p.context_window / 1000000) + 'M'
                    : (p.context_window / 1000) + 'k';
                chip.innerHTML = p.label + (p.detectable ? '<span class="det">auto-detect</span>' : '<span class="det">manual</span>') + '<span class="det">' + ctxStr + ' ctx</span>';
                chip.addEventListener('click', () => {
                    FORCED_PROVIDER = (FORCED_PROVIDER === p.key) ? '' : p.key;
                    document.querySelectorAll('.provider-chip').forEach(c => c.classList.remove('active'));
                    if (FORCED_PROVIDER) chip.classList.add('active');
                    updateDetected();
                });
                providerGrid.appendChild(chip);
            });
        }

        function updateDetected() {
            if (FORCED_PROVIDER) {
                const p = CATALOG.find(x => x.key === FORCED_PROVIDER);
                detectedProvider.value = p ? p.label + ' (forçado)' : FORCED_PROVIDER;
                return;
            }
            const key = apiKeyInput.value.trim();
            if (!key) { detectedProvider.value = ''; return; }
            // Espelha a detecção do backend (heurística local).
            const patterns = [
                [/^nvapi-/, 'nvidia'], [/^sk-ant-/, 'anthropic'], [/^sk-or-/, 'openrouter'],
                [/^gsk_/, 'groq'], [/^xai-/, 'xai'], [/^pplx-/, 'perplexity'],
                [/^fw_/, 'fireworks'], [/^csk-/, 'cerebras'], [/^AIza/, 'google'],
                [/^sk-[0-9a-f]{32}$/, 'deepseek'], [/^sk-proj-/, 'openai'],
            ];
            let found = '';
            for (const [re, name] of patterns) {
                if (re.test(key)) { found = name; break; }
            }
            if (!found && /^sk-[A-Za-z0-9_\-]{40,}$/.test(key)) found = 'openai';
            const p = CATALOG.find(x => x.key === found);
            if (p) {
                detectedProvider.value = p.label;
                const models = p.models || [];
                if (models.length) {
                    detectedProvider.title = 'Modelos: ' + models.join(', ');
                }
            } else {
                detectedProvider.value = key ? 'não detectado — escolha manualmente' : '';
                detectedProvider.title = '';
            }
        }

        apiKeyInput.addEventListener('input', updateDetected);

        // ---------- SELETOR DE MODELOS ----------
        const MODEL_CTX = {
            'nvidia/nemotron-3-super-120b-a12b': 128000,
            'nvidia/nemotron-3-ultra-550b-a55b': 128000,
            'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning': 128000,
            'nvidia/nemotron-3.5-lightning-30b-a3b': 128000,
            'nvidia/llama-3.1-nemotron-70b-instruct': 128000,
            'meta/llama-3.2-11b-vision-instruct': 128000,
            'meta/llama-3.2-90b-vision-instruct': 128000,
            'deepseek-ai/deepseek-v4.1-flash': 128000,
            'stepfun-ai/step-5-preview': 1000000,
            'stepfun-ai/step-3.7-flash': 128000,
            'deepseek-chat': 128000,
            'deepseek-reasoner': 128000,
            'claude-sonnet-4-20250514': 200000,
            'claude-opus-4-20250514': 200000,
            'claude-3-7-sonnet-20250219': 200000,
            'claude-3-5-haiku-20241022': 200000,
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000,
            'gpt-4.1': 1000000,
            'gpt-4.1-mini': 1000000,
            'o3-mini': 200000,
            'deepseek/deepseek-chat': 128000,
            'deepseek/deepseek-r1': 128000,
            'anthropic/claude-sonnet-4': 200000,
            'openai/gpt-4o': 128000,
            'meta-llama/llama-3.3-70b-instruct': 128000,
            'qwen/qwen-2.5-72b-instruct': 128000,
            'llama-3.3-70b-versatile': 128000,
            'llama-3.1-8b-instant': 128000,
            'deepseek-r1-distill-llama-70b': 128000,
            'qwen-2.5-32b': 128000,
            'grok-2-latest': 128000,
            'grok-2-1212': 128000,
            'grok-beta': 128000,
            'mistral-large-latest': 128000,
            'mistral-medium-latest': 128000,
            'codestral-latest': 128000,
            'open-mixtral-8x22b': 128000,
            'gemini-2.0-flash': 1000000,
            'gemini-1.5-pro': 2000000,
            'gemini-1.5-flash': 1000000,
            'sonar-pro': 128000,
            'sonar': 128000,
            'sonar-reasoning': 128000,
            'deepseek-ai/DeepSeek-V3': 128000,
            'meta-llama/Llama-3.3-70B-Instruct-Turbo': 128000,
            'Qwen/Qwen2.5-72B-Instruct-Turbo': 128000,
            'accounts/fireworks/models/deepseek-v3': 128000,
            'accounts/fireworks/models/llama-v3p3-70b-instruct': 128000,
            'llama-3.3-70b': 128000,
            'llama3.1-8b': 128000,
            'qwen-3-32b': 128000,
            'deepseek-ai/DeepSeek-V3': 128000,
            'meta-llama/Llama-3.3-70B-Instruct': 128000,
            'Meta-Llama-3.3-70B-Instruct': 128000,
            'DeepSeek-R1': 128000,
            'llama3.3': 128000,
            'qwen2.5-coder': 128000,
            'deepseek-r1': 128000,
        };

        function fmtCtx(ctx) {
            if (ctx >= 1000000) return (ctx / 1000000) + 'M';
            if (ctx >= 1000) return (ctx / 1000) + 'k';
            return String(ctx);
        }

        let AVAILABLE_MODELS = [];

        async function fetchAvailableModels() {
            try {
                const r = await fetch('/api/models?t=' + Date.now(), { cache: 'no-store' });
                const data = await r.json();
                AVAILABLE_MODELS = data.models || [];
            } catch (e) {
                AVAILABLE_MODELS = [];
            }
        }

        function refreshModels(providerKey) {
            const p = CATALOG.find(x => x.key === providerKey);
            modelSelect.innerHTML = '';

            // Se há modelos disponíveis da API, usa-os; senão fallback estático
            if (AVAILABLE_MODELS.length) {
                AVAILABLE_MODELS.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.id;
                    const ctxStr = m.context_window ? ' (' + fmtCtx(m.context_window) + ' ctx)' : '';
                    opt.textContent = m.id + ctxStr;
                    modelSelect.appendChild(opt);
                });
                return;
            }

            const models = (p && p.models) ? p.models : [];
            if (!models.length) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = '(padrão do provedor)';
                modelSelect.appendChild(opt);
                return;
            }
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                const ctx = MODEL_CTX[m] || p.context_window || 128000;
                opt.textContent = m + ' (' + fmtCtx(ctx) + ' ctx)';
                modelSelect.appendChild(opt);
            });
        }

        providerSelect.addEventListener('change', () => {
            refreshModels(providerSelect.value);
            updateStatus();
        });

        // ---------- STATUS ----------
        async function updateStatus() {
            try {
                const r = await fetch('/api/status?t=' + Date.now(), { cache: 'no-store' });
                const data = await r.json();

                if (data.allow_shell) {
                    shellWarning.style.display = 'block';
                    promptPrefix.textContent = 'root@cassandra:~#';
                } else {
                    shellWarning.style.display = 'none';
                    promptPrefix.textContent = 'user@cassandra:~$';
                }

                if (data.credentials > 0) {
                    providerStatus.textContent = '● ' + (data.provider_label || 'API') + ' (' + data.credentials + ')';
                    providerStatus.className = 'status-pill ok';
                } else {
                    providerStatus.textContent = '● sem chave de API';
                    providerStatus.className = 'status-pill bad';
                }

                cryptoStatus.textContent = (data.encrypt ? '🔐 cifrado' : '○ claro')
                    + ' / ' + (data.sanitize ? 'sanitizado' : 'bruto')
                    + ' / ' + (data.guard ? '🛡 anti-recusa' : 'sem guarda');
                cryptoStatus.className = 'status-pill ' + (data.encrypt ? 'ok' : '');

                if (data.provider && !providerSelect.value) {
                    providerSelect.value = data.provider;
                    refreshModels(data.provider);
                }
            } catch (e) {
                providerStatus.textContent = '● offline';
                providerStatus.className = 'status-pill bad';
            }
        }

        // ---------- MODAL ----------
        configBtn.addEventListener('click', () => { configModal.style.display = 'flex'; });
        closeConfig.addEventListener('click', () => { configModal.style.display = 'none'; });
        cancelConfig.addEventListener('click', () => { configModal.style.display = 'none'; });
        configModal.addEventListener('click', (e) => {
            if (e.target === configModal) configModal.style.display = 'none';
        });

        saveConfig.addEventListener('click', async () => {
            const payload = {
                api_key: apiKeyInput.value.trim(),
                provider: FORCED_PROVIDER,
                base_url: baseUrlInput.value.trim(),
                model: modelInput.value.trim()
            };
            const r = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await r.json();
            if (data.success) {
                configModal.style.display = 'none';
                apiKeyInput.value = '';
                await updateStatus();
                // Busca modelos disponíveis da API após configurar
                await fetchAvailableModels();
                if (FORCED_PROVIDER) {
                    refreshModels(FORCED_PROVIDER);
                } else if (data.provider) {
                    refreshModels(data.provider);
                }
                addMessage('**Configuração aplicada.** ' + (data.message || ''), 'cassandra');
            } else {
                alert('Falha: ' + (data.message || 'erro desconhecido'));
            }
        });

        // ---------- LIMPAR ----------
        clearBtn.addEventListener('click', () => {
            fetch('/api/clear', { method: 'POST' }).then(() => {
                chat.innerHTML = '<div class="message cassandra"><p><strong>Status:</strong> SESSÃO REINICIADA.</p><p>Aguardando novos comandos.</p></div>';
            });
        });

        // ---------- INPUT ----------
        promptInput.addEventListener('input', function() {
            this.style.height = '1.4em';
            this.style.height = (this.scrollHeight) + 'px';
        });

        promptInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // ------------------------------------------------------------------
        // Anexos de arquivo / pasta
        // ------------------------------------------------------------------
        // Problemas da versão anterior:
        //   1. sem limite de tamanho — um arquivo grande inundava o prompt,
        //      estourava o contexto e a requisição parecia travada;
        //   2. um FileReader por arquivo com onload assíncrono — com vários
        //      arquivos a ordem de inserção saía embaralhada;
        //   3. nenhum caminho útil: o modelo recebia só o nome, então não
        //      conseguia referenciar o arquivo depois.
        const MAX_FILE_CHARS = 100000;    // por arquivo
        const MAX_TOTAL_CHARS = 400000;   // somando todos

        let toastTimer = null;
        function showToast(msg, ms) {
            const t = document.getElementById('toast');
            if (!t) return;
            t.textContent = msg;
            t.style.display = 'block';
            if (toastTimer) clearTimeout(toastTimer);
            toastTimer = setTimeout(() => { t.style.display = 'none'; }, ms || 6000);
        }

        async function attachFiles(files, useRelative) {
            if (!files || !files.length) return;

            const partes = [];
            const resumo = [];
            let total = 0;
            let truncados = 0;
            let ignorados = 0;

            // Sequencial de propósito: garante ordem determinística.
            for (const file of files) {
                let texto;
                try {
                    texto = await file.text();
                } catch (err) {
                    ignorados++;
                    continue;
                }

                // Binário não faz sentido colar no prompt.
                if (texto.slice(0, 1024).indexOf('\u0000') !== -1) {
                    ignorados++;
                    continue;
                }

                const caminho = useRelative
                    ? (file.webkitRelativePath || file.name)
                    : file.name;

                if (texto.length > MAX_FILE_CHARS) {
                    texto = texto.slice(0, MAX_FILE_CHARS)
                        + '\n[... truncado: arquivo maior que o limite ...]';
                    truncados++;
                }
                if (total + texto.length > MAX_TOTAL_CHARS) {
                    truncados++;
                    break;
                }

                total += texto.length;
                partes.push(`[Arquivo: ${caminho}]\n${texto}\n`);
                resumo.push(`• ${caminho} (${texto.length.toLocaleString()} chars)`);
            }

            if (partes.length) {
                promptInput.value += (promptInput.value ? '\n\n' : '') + partes.join('\n');
                promptInput.style.height = '1.4em';
                promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + 'px';
            }

            const linhas = [];
            linhas.push(`📎 ${partes.length} arquivo(s) anexado(s) — ${total.toLocaleString()} chars`);
            if (resumo.length) linhas.push(resumo.slice(0, 6).join('\n'));
            if (resumo.length > 6) linhas.push(`… e mais ${resumo.length - 6}`);
            if (truncados) linhas.push(`⚠️ ${truncados} truncado(s) pelo limite de tamanho`);
            if (ignorados) linhas.push(`⚠️ ${ignorados} ignorado(s) (binário ou ilegível)`);
            if (useRelative) {
                linhas.push('ℹ️ Enviado o caminho relativo. O navegador não '
                    + 'expõe o caminho absoluto — se precisar dele, informe '
                    + 'o caminho real no texto.');
            }
            showToast(linhas.join('\n'), 8000);
        }

        function attachFileHandler(inputId, useRelative) {
            const el = document.getElementById(inputId);
            el.addEventListener('change', (e) => {
                const arquivos = Array.from(e.target.files || []);
                e.target.value = '';           // permite reanexar o mesmo arquivo
                attachFiles(arquivos, useRelative);
            });
        }
        attachFileHandler('fileUploadBtn', false);
        attachFileHandler('folderUploadBtn', true);

        sendBtn.addEventListener('click', sendMessage);

        if (stopBtn) stopBtn.addEventListener('click', pararEnvio);

        // Esc para durante o envio. Não interfere em nada quando ocioso.
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && enviando()) {
                e.preventDefault();
                pararEnvio();
            }
        });

        async function sendMessage() {
            const text = promptInput.value.trim();
            if (!text) return;
            if (enviando()) return;   // já existe um envio em curso

            addMessage(text, 'user');
            promptInput.value = '';
            promptInput.style.height = '1.4em';

            pedidoAtual = new AbortController();
            paradoPeloUsuario = false;
            marcarEnviando(true);

            const msgDiv = document.createElement('div');
            msgDiv.className = 'message cassandra';
            msgDiv.innerHTML = '<span class="typing-indicator">Processando</span>';
            chat.appendChild(msgDiv);
            scrollToBottom(true);   // o usuário acabou de enviar: sempre desce

            const payload = {
                message: text,
                model: modelSelect.value,
                provider: providerSelect.value,
                thinking: false
            };

            let fullText = '';
            let erroConexao = '';

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: pedidoAtual.signal
                });

                if (!response.ok) throw new Error('Falha na comunicação com o servidor.');

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                msgDiv.innerHTML = '';

                while (true) {
                    let chunk;
                    try {
                        const { done, value } = await reader.read();
                        if (done) break;
                        chunk = decoder.decode(value, { stream: true });
                    } catch (streamErr) {
                        // Parada manual: não é erro, é o usuário mandando parar.
                        if (paradoPeloUsuario) break;
                        // A conexão caiu no meio. Se já recebemos texto,
                        // preserva o que veio e avisa de forma discreta.
                        erroConexao = fullText
                            ? '⚠️ Conexão interrompida — a resposta acima está incompleta.'
                            : '⚠️ Conexão interrompida antes de receber resposta. '
                              + 'Verifique se o servidor está rodando e tente novamente.';
                        break;
                    }

                    fullText += chunk;
                    msgDiv.innerHTML = renderStructured(fullText, true);
                    msgDiv.querySelectorAll('pre code').forEach((el) => { hljs.highlightElement(el); });
                    scrollToBottom();
                }
            } catch (err) {
                const ehAborto = paradoPeloUsuario ||
                    (err && (err.name === 'AbortError' || err.code === 20));
                if (!ehAborto) {
                    erroConexao = 'Erro: ' + ((err && err.message) ? err.message : String(err));
                }
            } finally {
                // ---- Render final ----
                // Sempre renderiza fora do modo "streaming": uma resposta
                // parcial classificada como raciocínio ficaria atrás de um
                // painel colapsado para sempre.
                let html = fullText ? renderStructured(fullText, false) : '';

                if (paradoPeloUsuario) {
                    html += '<br><span style="color:var(--accent-yellow,#ffb74d)">'
                        + '⏹ Interrompido pelo operador.'
                        + (fullText ? ' O texto acima é parcial.' : '')
                        + '</span>';
                } else if (erroConexao) {
                    html += '<br><span style="color:var(--accent-red)">'
                        + escapeHtml(erroConexao) + '</span>';
                } else if (!fullText) {
                    html = '<span style="color:var(--accent-red)">'
                        + '⚠️ O servidor encerrou o stream sem enviar '
                        + 'conteúdo. Tente novamente.</span>';
                }

                msgDiv.innerHTML = html;
                msgDiv.querySelectorAll('pre code').forEach((el) => { hljs.highlightElement(el); });

                // ---- Restaura o estado da interface ----
                pedidoAtual = null;
                marcarEnviando(false);

                if (paradoPeloUsuario) {
                    // Devolve o prompt para o operador corrigir e reenviar.
                    // Só restaura se ele não tiver começado a digitar outra
                    // coisa enquanto a resposta corria.
                    if (!promptInput.value.trim()) {
                        promptInput.value = text;
                        promptInput.style.height = '1.4em';
                        promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + 'px';
                    }
                    promptInput.focus();
                    promptInput.setSelectionRange(promptInput.value.length,
                                                  promptInput.value.length);
                    showToast('⏹ Resposta interrompida. O prompt voltou para a '
                              + 'caixa — edite e reenvie.', 6000);
                } else {
                    promptInput.focus();
                }

                paradoPeloUsuario = false;
                scrollToBottom();
            }
        }

        function addMessage(text, sender) {
            const div = document.createElement('div');
            div.className = `message ${sender}`;
            if (sender === 'user') {
                div.textContent = text;
            } else {
                div.innerHTML = renderStructured(text);
            }
            chat.appendChild(div);
            // Mensagem do usuário sempre traz a tela para o fim; a
            // resposta respeita a rolagem manual dele.
            scrollToBottom(sender === 'user');
        }

        // ------------------------------------------------------------------
        // Auto-scroll respeitoso
        // ------------------------------------------------------------------
        // Bug anterior: scrollToBottom() forçava o fim a cada pedaço
        // recebido, então era impossível rolar para cima enquanto a
        // resposta era escrita — a tela puxava de volta.
        //
        // Agora só rolamos sozinhos quando o usuário JÁ está no fim. Se
        // ele subiu para reler algo, respeitamos e mostramos um botão
        // para voltar quando quiser.
        let autoScroll = true;
        const scrollDownBtn = document.getElementById('scrollDownBtn');

        function estaNoFim() {
            return (chat.scrollHeight - chat.scrollTop - chat.clientHeight) < 80;
        }

        chat.addEventListener('scroll', () => {
            autoScroll = estaNoFim();
            if (scrollDownBtn) {
                scrollDownBtn.style.display = autoScroll ? 'none' : 'block';
            }
        }, { passive: true });

        if (scrollDownBtn) {
            scrollDownBtn.addEventListener('click', () => {
                autoScroll = true;
                scrollDownBtn.style.display = 'none';
                chat.scrollTop = chat.scrollHeight;
            });
        }

        /**
         * Rola para o fim. `force=true` para ações do próprio usuário
         * (enviar mensagem), que devem sempre trazer a tela de volta.
         */
        function scrollToBottom(force) {
            if (force) autoScroll = true;
            if (!autoScroll) return;
            chat.scrollTop = chat.scrollHeight;
            if (scrollDownBtn) scrollDownBtn.style.display = 'none';
        }

        // ===== COLORIZAÇÃO DE PALAVRAS ESPECÍFICAS =====
        // Aplica cores a tokens técnicos dentro do texto já renderizado,
        // sem tocar em <code>/<pre> (que já têm syntax highlighting).
        const TOKEN_RULES = [
            // CVE
            [/\bCVE-\d{4}-\d{4,7}\b/g, 'tok-cve'],
            // URLs
            [/\bhttps?:\/\/[^\s<>"')]+/g, 'tok-url'],
            // IPs (com ou sem CIDR)
            [/\b(?:\d{1,3}\.){3}\d{1,3}(?:\/\d{1,2})?\b/g, 'tok-ip'],
            // Portas: 22/tcp, :8080, porta 443
            [/\b\d{1,5}\/(?:tcp|udp)\b/g, 'tok-port'],
            [/(?<=\:)\d{2,5}\b(?=[\s,;)\]]|$)/g, 'tok-port'],
            // Hashes / tokens longos
            [/\b[0-9a-fA-F]{32,64}\b/g, 'tok-hash'],
            // Caminhos de arquivo
            [/(?:\/[\w.\-]+){2,}\/?/g, 'tok-path'],
            [/[A-Z]:\\[\w\\.\-]+/g, 'tok-path'],
            // Credenciais comuns
            [/\b(?:password|senha|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+/gi, 'tok-key'],
            // Avisos
            [/\b(?:AVISO|ATENÇÃO|CUIDADO|WARNING|CRÍTICO|CRITICAL|ERRO|ERROR|FALHA|FALHOU)\b/g, 'tok-warn'],
            // Sucesso
            [/\b(?:OK|SUCESSO|CONCLUÍDO|CONCLUIDO|SUCCESS|DONE|ATIVO|ATIVA)\b/g, 'tok-ok'],
            // Root / privilégio
            [/\b(?:ROOT|root@|#\s*root)\b/g, 'tok-root'],
            // Nomes de skill
            [/`([a-z0-9]+(?:-[a-z0-9]+){2,})`/g, 'tok-skill'],
        ];

        function colorizeTokens(root) {
            if (!root) return;
            // Percorre apenas nós de texto, ignorando code/pre/a.
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
                acceptNode(node) {
                    let p = node.parentNode;
                    while (p && p !== root) {
                        const tag = (p.tagName || '').toLowerCase();
                        if (tag === 'code' || tag === 'pre' || tag === 'a') {
                            return NodeFilter.FILTER_REJECT;
                        }
                        p = p.parentNode;
                    }
                    return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT
                                                 : NodeFilter.FILTER_REJECT;
                }
            });

            const targets = [];
            while (walker.nextNode()) targets.push(walker.currentNode);

            for (const node of targets) {
                let html = node.nodeValue;
                let changed = false;
                for (const [re, cls] of TOKEN_RULES) {
                    const before = html;
                    html = html.replace(re, (m) => `<span class="${cls}">${m}</span>`);
                    if (html !== before) changed = true;
                }
                if (changed) {
                    const span = document.createElement('span');
                    span.innerHTML = html;
                    node.parentNode.replaceChild(span, node);
                }
            }
        }

        // Renderiza Markdown + coloriza tokens.
        /**
         * Sanitiza o HTML vindo do modelo.
         *
         * `marked.parse()` NÃO sanitiza: se a resposta (ou um arquivo
         * anexado, ou uma página que o usuário mandou analisar) contiver
         * `<script>` ou `<img onerror=...>`, isso executa no navegador.
         * Removemos elementos e atributos perigosos via DOMParser —
         * sem dependência externa.
         */
        const TAGS_PROIBIDAS = [
            'script', 'iframe', 'object', 'embed', 'link', 'style',
            'meta', 'base', 'form', 'frame', 'frameset', 'applet',
        ];
        function sanitizeHtml(html) {
            const doc = new DOMParser().parseFromString(html, 'text/html');

            doc.querySelectorAll(TAGS_PROIBIDAS.join(',')).forEach((el) => el.remove());

            doc.querySelectorAll('*').forEach((el) => {
                for (const attr of Array.from(el.attributes)) {
                    const nome = attr.name.toLowerCase();
                    const valor = String(attr.value || '')
                        .replace(/[\s\u0000-\u001f]/g, '').toLowerCase();

                    // Handlers inline (onclick, onerror, onload...).
                    if (nome.startsWith('on')) {
                        el.removeAttribute(attr.name);
                        continue;
                    }
                    // URLs que executam script.
                    if ((nome === 'href' || nome === 'src' ||
                         nome === 'xlink:href' || nome === 'action') &&
                        (valor.startsWith('javascript:') ||
                         valor.startsWith('vbscript:') ||
                         valor.startsWith('data:text/html'))) {
                        el.removeAttribute(attr.name);
                        continue;
                    }
                    // HTML embutido em iframe.
                    if (nome === 'srcdoc') {
                        el.removeAttribute(attr.name);
                    }
                }
                // target=_blank sem noopener permite tabnabbing.
                if (el.tagName === 'A' && el.getAttribute('target') === '_blank') {
                    el.setAttribute('rel', 'noopener noreferrer');
                }
            });

            return doc.body.innerHTML;
        }

        function renderRich(text) {
            const container = document.createElement('div');
            container.innerHTML = sanitizeHtml(marked.parse(text));
            colorizeTokens(container);
            return container.innerHTML;
        }

        /** Escapa texto para inserir com segurança via innerHTML. */
        function escapeHtml(s) {
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        // ===== SEPARAÇÃO ENTRE RACIOCÍNIO E RESPOSTA =====
        //
        // O modelo pode expor o raciocínio de três formas:
        //   1. tags  thinking ...  response
        //   2. um bloco [STATE_DUMP] {...} no fim
        //   3. texto puro antes do bloco de código / da resposta final
        //
        // A heurística (3) é a mais comum com modelos que "pensam em voz
        // alta" (ex.: nemotron): frases como "We need to...", "Let me...",
        // "First, I..." antes da entrega real.

        const REASONING_OPENERS = [
            /^(we|i)\s+(need|should|must|can|will|have)\b/i,
            /^(let me|let's|first,?\s|okay,?\s|alright,?\s|hmm,?\s)/i,
            /^(the user|user)\s+(is|wants|asked|needs|said)\b/i,
            /^(looking at|checking|analyzing|considering)\b/i,
            /^(so|now|next|then),?\s/i,
            /^preciso\b|^vou\b|^deixa eu\b|^primeiro,?\s/i,
        ];

        function looksLikeReasoning(line) {
            const t = line.trim();
            if (!t) return false;
            return REASONING_OPENERS.some(re => re.test(t));
        }

        /**
         * Divide o texto em { reasoning, answer }.
         */
        function splitReasoning(text) {
            let reasoning = '';
            let answer = text;

            // --- 1. Tags explícitas ---
            const openIdx = answer.indexOf('<' + 'think' + '>');
            if (openIdx !== -1) {
                const closeIdx = answer.indexOf('<' + '/' + 'think' + '>');
                if (closeIdx === -1) {
                    reasoning = answer.substring(openIdx + 7);
                    answer = answer.substring(0, openIdx);
                    return { reasoning, answer, thinking: true };
                }
                reasoning = answer.substring(openIdx + 7, closeIdx);
                answer = answer.substring(0, openIdx) + answer.substring(closeIdx + 8);
                return { reasoning, answer, thinking: false };
            }

            // --- 2. STATE_DUMP ---
            const dumpIdx = answer.search(/\[STATE_DUMP\]/i);
            if (dumpIdx !== -1) {
                reasoning = answer.substring(dumpIdx);
                answer = answer.substring(0, dumpIdx);
            }

            // --- 3. Heurística de parágrafos de raciocínio ---
            const lines = answer.split('\n');
            let cutLine = -1;
            let cutCol = -1;
            let sawReasoning = false;

            for (let i = 0; i < lines.length; i++) {
                const ln = lines[i];
                const isCodeFence = /^\s*```/.test(ln);
                const isHeading = /^#{1,6}\s/.test(ln);
                const isReasoning = looksLikeReasoning(ln);

                if (isReasoning) { sawReasoning = true; continue; }

                if (sawReasoning && (isCodeFence || isHeading)) {
                    cutLine = i; cutCol = 0;
                    break;
                }

                // Resposta colada no fim de uma linha de raciocínio:
                // "...three pairs.22/SSH" — corta no ponto onde o
                // raciocínio termina e a entrega começa.
                if (sawReasoning && ln.trim()) {
                    const glued = findAnswerStart(ln);
                    if (glued > 0) {
                        cutLine = i; cutCol = glued;
                        break;
                    }
                    const next = lines[i + 1] || '';
                    if (next.trim() && !looksLikeReasoning(next)) {
                        cutLine = i; cutCol = 0;
                        break;
                    }
                }
            }

            if (cutLine > 0) {
                const head = lines.slice(0, cutLine);
                const tail = lines.slice(cutLine);
                if (cutCol > 0) {
                    head.push(tail[0].substring(0, cutCol));
                    tail[0] = tail[0].substring(cutCol);
                }
                reasoning = head.join('\n').trim();
                answer = tail.join('\n');
            }

            // INVARIANTE: nunca devolver resposta vazia.
            //
            // Se a heurística consumiu o texto inteiro como raciocínio, o
            // conteúdo desapareceria da interface (o usuário veria apenas
            // um painel colapsado e nenhuma resposta). Nesse caso o texto
            // é a resposta.
            if (!answer.trim() && text.trim()) {
                return { reasoning: '', answer: text, thinking: false };
            }

            return { reasoning, answer, thinking: false };
        }

        /**
         * Encontra a coluna onde a resposta começa dentro de uma linha
         * que também contém raciocínio.
         *
         * Heurística: a resposta costuma começar com um token técnico
         * (porta, IP, caminho, número, código) ou após uma frase de
         * encerramento do raciocínio ("Just output...", "So:").
         * Devolve -1 se não achar.
         */
        function findAnswerStart(line) {
            // Frase de encerramento do raciocínio seguida da resposta.
            const closer = /(?:just\s+(?:output|give|return|say|do)|so,?\s+here|final(?:ly)?[:\s]|therefore[:\s]|result[:\s]|resposta[:\s])\s*/i;
            const m = closer.exec(line);
            if (m) {
                let after = m.index + m[0].length;
                // Pula a continuação da frase ("the three pairs.", "them:")
                // até chegar a um token que parece início de entrega.
                const rest = line.substring(after);
                const tech = rest.search(
                    /(?:\d{1,3}(?:[./]\w|\/tcp|\/udp)|\d{2,5}\/|https?:\/\/|\/[\w.\-]{2,}|[A-Z]:\\|`|\*|-{1,2}\s|#{1,6}\s)/
                );
                if (tech !== -1) {
                    after += tech;
                } else {
                    // Nada técnico: corta depois do fim da frase.
                    const sentenceEnd = rest.search(/[.:!?]\s/);
                    if (sentenceEnd !== -1) after += sentenceEnd + 2;
                }
                if (after < line.length - 1) return after;
            }

            // Token técnico colado após um ponto final: ".22/SSH", ".10.0.0.5"
            const glued = /\.(?=\d{1,3}(?:[./]\w|\/tcp|\/udp))/;
            const g = glued.exec(line);
            if (g) return g.index + 1;

            return -1;
        }

        /**
         * Renderiza um bloco de raciocínio (painel colapsável roxo).
         */
        function renderReasoning(reasoning, live) {
            if (!reasoning || !reasoning.trim()) return '';
            if (live) {
                return '<div class="reasoning-live">'
                    + '<div class="cyber-spinner"></div>'
                    + '<div class="label">Raciocínio em andamento…</div>'
                    + '</div>';
            }
            const body = renderRich(reasoning);
            return '<details class="reasoning-panel">'
                + '<summary>🧠 Raciocínio <span class="chev">▶</span></summary>'
                + '<div class="reasoning-body">' + body + '</div>'
                + '</details>';
        }

        /**
         * Renderiza a resposta final (Markdown + tokens coloridos).
         */
        function renderAnswer(answer) {
            if (!answer || !answer.trim()) return '';
            return '<div class="answer-divider">◆ Resposta</div>'
                + '<div class="answer-body">' + renderRich(answer) + '</div>';
        }

        /**
         * Renderização completa: raciocínio separado da resposta.
         *
         * `streaming` = true enquanto o stream está em andamento. Só nesse
         * caso é aceitável mostrar um indicador no lugar do conteúdo.
         */
        function renderStructured(text, streaming) {
            const { reasoning, answer, thinking } = splitReasoning(text);

            // Ainda pensando (tag aberta, sem resposta) DURANTE o stream:
            // indicador é transitório e correto.
            if (streaming && thinking && !answer.trim()) {
                return renderReasoning(reasoning, true);
            }

            // INVARIANTE: nunca esconder conteúdo. Sem resposta
            // identificada, mostramos o texto completo — nunca um painel
            // colapsado com "resposta nenhuma".
            if (!answer.trim()) {
                return renderRich(text);
            }

            let out = '';
            if (reasoning.trim()) out += renderReasoning(reasoning, false);
            if (answer.trim()) out += renderAnswer(answer);
            return out || renderRich(text);
        }

        marked.setOptions({ breaks: true, gfm: true });

        // ---------- INIT ----------
        (async () => {
            await loadCatalog();
            await updateStatus();
        })();
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# ESTADO / AGENTE
# ---------------------------------------------------------------------------

agent = Agent(allow_interactive=False)
conversation = []

# `conversation` é global (uma sessão só). Duas requisições simultâneas
# intercalariam mensagens e corromperiam o histórico — este lock serializa
# as respostas.
_chat_lock = asyncio.Lock()


def _next_or_none(iterator):
    """
    Puxa o próximo item de um iterador, devolvendo None no fim.

    Usado com `run_in_threadpool` para consumir o stream bloqueante do
    provedor sem travar o event loop do uvicorn.
    """
    try:
        return next(iterator)
    except StopIteration:
        return None


class ChatRequest(BaseModel):
    message: str
    model: str = ""
    provider: str = ""
    thinking: bool = False


class CredentialRequest(BaseModel):
    api_key: str = ""
    provider: str = ""
    base_url: str = ""
    model: str = ""


@app.get("/")
async def get_index():
    return HTMLResponse(content=HTML_CONTENT)


@app.get("/api/providers")
async def get_providers():
    if not CORE_OK:
        return {"providers": [], "error": _CORE_ERR}
    return {"providers": provider_catalog()}


@app.get("/api/models")
async def get_available_models():
    """
    Retorna os modelos efetivamente disponíveis para a credencial ativa.

    Consulta GET /v1/models no endpoint do provedor e cruza com o
    catálogo local. Assim a web mostra apenas modelos que a conta do
    usuário realmente pode invocar — não a lista estática do código.
    """
    if not CORE_OK:
        return {"models": [], "error": _CORE_ERR}

    creds = _active_credentials()
    if not creds:
        return {"models": [], "error": "no credentials"}

    cred = creds[0]
    try:
        import httpx
        headers = {"Authorization": f"Bearer {cred.api_key}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{cred.base_url}/models", headers=headers
            )
        if resp.status_code != 200:
            return {
                "models": [],
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
        data = resp.json()
        api_models = [m.get("id", "") for m in data.get("data", [])]
        if not api_models:
            return {"models": [], "error": "empty response"}

        # Cruza com o catálogo local para enriquecer com context_window
        catalog = provider_catalog()
        provider_info = next(
            (p for p in catalog if p["key"] == cred.provider_key), {}
        )
        model_ctx = {}
        for p in catalog:
            for m in p.get("models", []):
                model_ctx[m] = p.get("context_window", 128000)

        # Preserva a ordem da API, adiciona context_window quando conhecido
        result = []
        for m in api_models:
            ctx = model_ctx.get(m)
            entry = {"id": m}
            if ctx:
                entry["context_window"] = ctx
            result.append(entry)

        return {"models": result, "provider": cred.provider_key}

    except Exception as exc:
        return {"models": [], "error": str(exc)}


@app.get("/api/status")
async def get_status():
    creds = _active_credentials()
    provider_key = ""
    provider_label = ""
    if creds:
        provider_key = creds[0].provider_key
        provider_label = creds[0].label

    return {
        "allow_shell": ALLOW_SHELL,
        "cwd": os.getcwd(),
        "credentials": len(creds),
        "provider": provider_key,
        "provider_label": provider_label,
        # O padrão do encrypt é "0" — igual ao de cassandra/client.py.
        # Antes era "1", então sem a variável definida a interface dizia
        # "cifrado" enquanto o cliente NÃO cifrava: a UI mentia.
        "encrypt": os.getenv("CASSANDRA_ENCRYPT", "0").lower() in {"1", "true", "yes", "on"},
        "sanitize": os.getenv("CASSANDRA_SANITIZE", "1").lower() in {"1", "true", "yes", "on"},
        "guard": os.getenv("CASSANDRA_GUARD", "1").lower() in {"1", "true", "yes", "on"},
        "refusal_retries": os.getenv("CASSANDRA_REFUSAL_RETRIES", "2"),
        "core_ok": CORE_OK,
    }


@app.post("/api/credentials")
async def set_credentials(req: CredentialRequest):
    """
    Define a credencial em runtime. Só em memória — nunca grava em disco.
    """
    global RUNTIME_CREDENTIALS
    if not CORE_OK:
        return {"success": False, "message": f"Núcleo indisponível: {_CORE_ERR}"}

    key = (req.api_key or "").strip()
    if not key:
        # Sem chave: volta a usar o .env.
        RUNTIME_CREDENTIALS = []
        agent.clear_session()
        return {"success": True, "message": "Credencial removida — usando o .env."}

    provider = resolve_provider(key, req.provider, req.base_url)
    model = (req.model or "").strip() or provider.default_model

    RUNTIME_CREDENTIALS = [
        Credential(
            provider_key=provider.key,
            api_key=key,
            model=model,
            base_url=provider.base_url,
            label=provider.label,
        )
    ]
    # Recria o cliente para pegar a nova credencial.
    agent.clear_session()

    return {
        "success": True,
        "message": f"Provedor {provider.label}, modelo {model or '(padrão)'}.",
        "provider": provider.key,
    }


@app.post("/api/clear")
async def clear_chat():
    conversation.clear()
    agent.clear_session()
    return {"success": True}


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):

    if not CORE_OK:
        async def err_gen():
            yield f"\n\n> ❌ **Núcleo multi-provedor indisponível:** {_CORE_ERR}\n"
        return StreamingResponse(err_gen(), media_type="text/plain")

    creds = _active_credentials()
    if not creds:
        async def no_key_gen():
            yield (
                "\n\n> 🔑 **Nenhuma chave de API configurada.**\n>\n"
                "> Clique em **⚙ CONFIGURAR API** e cole sua chave, ou defina no `.env`:\n"
                "> ```\n> CASSANDRA_API_KEY=\"nvapi-...\"\n> ```\n"
                "> O provedor é detectado automaticamente pelo formato da chave.\n"
            )
        return StreamingResponse(no_key_gen(), media_type="text/plain")

    # Override de provedor por requisição (seletor da UI).
    #
    # Precisa LIMPAR quando o pedido não traz provedor: antes o valor
    # anterior permanecia no ambiente e não havia como voltar ao
    # auto-detect. Restaura o padrão do .env quando existir.
    if req.provider.strip():
        os.environ["CASSANDRA_PROVIDER"] = req.provider.strip()
    elif _ENV_PROVIDER_DEFAULT:
        os.environ["CASSANDRA_PROVIDER"] = _ENV_PROVIDER_DEFAULT
    else:
        os.environ.pop("CASSANDRA_PROVIDER", None)

    sys_info = f"OS: {platform.system()} {platform.release()}"
    prompt = f"[SISTEMA OPERACIONAL: {sys_info} | WORKSPACE ATUAL: {os.getcwd()}]\n{req.message.strip()}"

    dynamic_skillogy, _ = agent.get_relevant_skillogy(
        prompt,
        allow_shell=ALLOW_SHELL,
        model=req.model,
        provider=req.provider or os.getenv("CASSANDRA_PROVIDER", ""),
    )
    user = getpass.getuser()
    privilege = "ROOT" if ALLOW_SHELL else "USER"

    if not conversation or conversation[0].get("role") != "system":
        current_system_prompt = build_system_prompt(
            user=user,
            privilege=privilege,
            skillogy=dynamic_skillogy,
            allow_shell=ALLOW_SHELL,
        )
        conversation.append({"role": "system", "content": current_system_prompt})

    conversation.append({"role": "user", "content": prompt})

    # === COMPACTAÇÃO DE CONTEXTO (início do turno) ===
    # Roda aqui, antes do loop: neste ponto o turno anterior já terminou
    # por completo, então resumir o histórico não interrompe nenhuma
    # tarefa em andamento.
    compaction_notice = ""
    if needs_compaction(conversation):
        try:
            res = compact(conversation, agent.client, req.model)
            sys_prompt = conversation[0] if conversation and \
                conversation[0].get("role") == "system" else None
            new_conv = res.to_messages(system_prompt=sys_prompt)
            conversation.clear()
            conversation.extend(new_conv)
            how = {
                "llm": "resumo por LLM",
                "local": "resumo local (fallback)",
            }.get(res.method, res.method)
            compaction_notice = (
                f"\n\n> 💾 **Contexto compactado:** {res.removed} "
                f"mensagens resumidas ({how}).\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            compaction_notice = f"\n\n> ⚠️ **Compactação falhou:** {exc}\n\n"

    async def event_generator(request=None):
        """
        Gerador ASSÍNCRONO.

        O trabalho pesado (chamadas de rede ao provedor, execução de shell)
        é bloqueante. Rodá-lo direto numa corrotina travaria o event loop do
        uvicorn e, em streams longos, o navegador veria a conexão morrer
        ("Error in input stream"). Por isso cada passo bloqueante vai para
        um thread separado com `run_in_threadpool`.

        `request` permite detectar que o operador abortou (botão Parar):
        nesse caso paramos de gastar tokens em vez de continuar gerando
        uma resposta que ninguém vai ler.
        """
        from starlette.concurrency import run_in_threadpool

        async def _cliente_desconectou() -> bool:
            if request is None:
                return False
            try:
                return await request.is_disconnected()
            except Exception:  # noqa: BLE001
                return False

        # Avisa sobre a compactação feita no início deste turno.
        if compaction_notice:
            yield compaction_notice

        step = 0
        while step < 5:
            # O operador pode ter apertado Parar entre passos. Sem esta
            # checagem continuaríamos gerando (e gastando tokens) uma
            # resposta que ninguém vai ler.
            if await _cliente_desconectou():
                return

            full_reply = []
            try:
                stream_wrapper = agent.chat_stream(
                    messages=conversation,
                    model=req.model,
                    thinking=req.thinking,
                )
                # Itera o stream em thread separada, devolvendo os chunks
                # ao event loop conforme chegam.
                iterator = iter(stream_wrapper)
                while True:
                    # Espera o próximo chunk OU a desconexão — o que vier
                    # primeiro. Sem isto, um modelo lento mantém o lock
                    # preso (e continua gerando) mesmo depois de o
                    # operador apertar Parar, porque a espera pelo chunk
                    # bloqueia qualquer outra checagem.
                    _t = asyncio.create_task(
                        run_in_threadpool(_next_or_none, iterator)
                    )
                    while True:
                        done, _ = await asyncio.wait({_t}, timeout=1.0)
                        if _t in done:
                            break
                        if await _cliente_desconectou():
                            _t.cancel()
                            # Propaga para o wrapper, que fecha o stream
                            # do modelo e mata subprocessos.
                            raise asyncio.CancelledError()
                    chunk = _t.result()
                    if chunk is None:
                        break
                    full_reply.append(chunk)
                    yield chunk

                # Avisa quando a guarda anti-recusa neutralizou uma recusa.
                try:
                    gr = agent.client.last_guard_report
                except Exception:
                    gr = {}
                if gr.get("recovered"):
                    yield (
                        "\n\n> 🛡️ **Recusa neutralizada automaticamente** "
                        f"(tentativa {gr.get('final_attempt', '?')}): o pedido foi "
                        "reescrito em termos técnicos neutros e o modelo "
                        "cooperou.\n"
                    )
                elif gr.get("detected") and gr.get("recovered") is False:
                    yield (
                        "\n\n> ⚠️ **Recusa persistente:** o modelo recusou mesmo "
                        "após reescrita. Considere reformular o pedido ou "
                        "aumentar `CASSANDRA_REFUSAL_RETRIES`.\n"
                    )
            except ProviderBlocked as e:
                yield (
                    f"\n\n> 🛡️ **Cassandra pausada por proteção anti-banimento:** {e}\n"
                    "> *Aguarde o cooldown ou adicione outra chave de API.*\n"
                )
                break
            except AllProvidersExhausted as e:
                yield (
                    f"\n\n> ⚠️ **Provedores esgotados:** {e}\n"
                    "> *Verifique suas chaves de API ou adicione outra em ⚙ CONFIGURAR API.*\n"
                )
                break
            except ProviderError as e:
                yield (
                    f"\n\n> ❌ **Erro do provedor:** {e}\n"
                    "> *Verifique a chave, o modelo e o endpoint configurados.*\n"
                )
                break
            except Exception as e:
                yield f"\n\n> ❌ **Erro ao consultar a Cassandra:** {e}\n"
                break

            reply = "".join(full_reply)
            conversation.append({"role": "assistant", "content": reply})

            # ------------------------------------------------------------------
            # Daqui para baixo tudo é pós-processamento. Qualquer exceção aqui
            # NÃO pode matar o stream (o navegador reportaria "Error in input
            # stream"), então cada bloco tem seu próprio tratamento.
            # ------------------------------------------------------------------

            # Download de ferramenta sob demanda (bloco ```tool).
            try:
                if extract_tool_blocks is not None:
                    tool_specs = extract_tool_blocks(reply)
                    if tool_specs:
                        for spec in tool_specs:
                            tname = spec.get("name", "?")
                            tsrc = spec.get("source", "?")
                            yield (
                                f"\n\n> 🔧 **Ferramenta solicitada:** "
                                f"`{tname}` (via {tsrc})\n\n"
                            )
                            # Heartbeat: um `apt install` pode levar
                            # minutos. Sem sinal de vida a interface
                            # parecia travada.
                            _tt = asyncio.create_task(
                                run_in_threadpool(tool_fetch, spec, ALLOW_SHELL)
                            )
                            while not _tt.done():
                                await asyncio.wait({_tt}, timeout=5.0)
                                if await _cliente_desconectou():
                                    return
                                if not _tt.done():
                                    yield (
                                        f"\n> ⏳ processando `{tname}`… "
                                        f"(download/instalação em andamento)\n\n"
                                    )
                            tr = _tt.result()
                            if tr.action == "suggested":
                                yield (
                                    f"> ℹ️ **Modo restrito** — rode manualmente:\n"
                                    f"> ```bash\n> {tr.command}\n> ```\n\n"
                                )
                                msg = (
                                    f"[FERRAMENTA SUGERIDA: {tname}]\n"
                                    f"Modo restrito — o operador deve rodar:\n"
                                    f"```bash\n{tr.command}\n```\n"
                                    f"Motivo: {spec.get('reason', '(não informado)')}\n\n"
                                    "Continue a tarefa assumindo que a ferramenta "
                                    "estará disponível, ou proponha uma alternativa."
                                )
                            elif tr.ok:
                                yield f"> ✅ {tr.message}\n\n"
                                if tr.path:
                                    yield f"> 📁 `{tr.path}`\n\n"
                                msg = (
                                    f"[FERRAMENTA DISPONÍVEL: {tname}]\n"
                                    f"{tr.message}\n"
                                    + (f"Caminho: {tr.path}\n" if tr.path else "")
                                    + (f"SHA-256: {tr.sha256}\n" if tr.sha256 else "")
                                    + "\nContinue a tarefa usando a ferramenta."
                                )
                            else:
                                yield f"> ⚠️ **Recusado:** {tr.message}\n\n"
                                msg = (
                                    f"[FERRAMENTA INDISPONÍVEL: {tname}]\n"
                                    f"Motivo: {tr.message}\n\n"
                                    "Não insista nesta ferramenta. Use uma "
                                    "alternativa já disponível no sistema ou "
                                    "explique o bloqueio ao operador."
                                )
                            conversation.append({"role": "user", "content": msg})
                        step += 1
                        continue
            except Exception as exc:  # noqa: BLE001
                yield f"\n\n> ⚠️ **Falha no download de ferramenta:** {exc}\n\n"

            # Carregamento de skill sob demanda (bloco ```skill).
            try:
                skill_blocks = re.findall(
                    r"```skill\s*\n(.*?)\n```", reply, re.IGNORECASE | re.DOTALL
                )
                if skill_blocks and agent._skill_index is not None:
                    for query in skill_blocks:
                        query = query.strip()
                        if not query:
                            continue
                        yield f"\n\n> 🧠 **Carregando skill:** `{query}`\n\n"
                        content, loaded = await run_in_threadpool(
                            agent._skill_index.load, query
                        )
                        if content:
                            yield f"> ✅ Carregada: {', '.join(loaded)}\n\n"
                            msg = (
                                f"[SKILL CARREGADA: {', '.join(loaded)}]\n\n"
                                f"{content}\n\n"
                                "Use o procedimento acima para continuar."
                            )
                        else:
                            avail = agent._skill_index.catalog(limit=60)
                            yield "> ⚠️ Skill não encontrada.\n\n"
                            msg = (
                                f"[SKILL NÃO ENCONTRADA: '{query}']\n\n"
                                f"Skills disponíveis: {avail}\n\n"
                                "Tente outro nome ou prossiga sem ela."
                            )
                        conversation.append({"role": "user", "content": msg})
                    step += 1
                    continue
            except Exception as exc:  # noqa: BLE001
                yield f"\n\n> ⚠️ **Falha ao carregar skill:** {exc}\n\n"

            # NOTA: a compactação NÃO acontece aqui. Ela roda no início do
            # próximo turno (antes do loop), depois que todo o trabalho
            # pendente deste turno terminou. Compactar no meio da execução
            # apagava o comando que a Cassandra acabara de gerar — ela
            # "largava a mão" da tarefa em andamento.

            # Execução autônoma de shell. Isolada: um comando problemático
            # não pode derrubar o stream.
            try:
                if ALLOW_SHELL:
                    # Avisa ANTES de executar. A execução pode levar
                    # minutos; sem este aviso a interface ficava parada
                    # sem nenhum sinal de vida (o "fica parado" ao usar
                    # ferramentas/comandos).
                    _cmds = extract_shell_blocks(reply)
                    if _cmds:
                        yield (
                            f"\n\n> ⚙️ **Executando {len(_cmds)} comando(s) "
                            f"localmente em `{os.getcwd()}`...**\n\n"
                        )
                        for _c in _cmds:
                            _c = _c.strip()
                            if _c:
                                yield f"> `{_c[:200]}`\n\n"

                    # Heartbeat: roda em paralelo e emite sinal de vida a
                    # cada 5s, para o stream nunca parecer travado.
                    _task = asyncio.create_task(
                        run_in_threadpool(execute_shell_blocks, reply, True)
                    )
                    while not _task.done():
                        await asyncio.wait({_task}, timeout=5.0)
                        if await _cliente_desconectou():
                            # Operador apertou Parar: encerra o stream do
                            # modelo e mata os comandos em execução.
                            try:
                                agent.client.abort_active()
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                kill_active_procs(verbose=True)
                            except Exception:  # noqa: BLE001
                                pass
                            return
                        if not _task.done():
                            yield (
                                "\n> ⏳ ainda executando… (comandos longos "
                                "podem levar alguns minutos)\n\n"
                            )
                    cmd_output = _task.result()

                    if cmd_output:
                        yield (
                            f"\n\n> ✅ **Execução concluída.**\n"
                            f"```text\n{cmd_output[:4000]}\n```\n\n"
                        )
                        msg = (
                            f"[SAÍDA DA EXECUÇÃO LOCAL NO DIRETÓRIO {os.getcwd()}]\n"
                            f"```text\n{cmd_output}\n```\n"
                            "Se o objetivo ainda não foi concluído, você PODE e DEVE "
                            "gerar novos comandos shell para continuar atuando de forma "
                            "autônoma. Caso o objetivo tenha sido atingido, apenas "
                            "apresente o resultado final."
                        )
                        conversation.append({"role": "user", "content": msg})
                        step += 1
                        continue
            except Exception as exc:  # noqa: BLE001
                yield f"\n\n> ⚠️ **Falha na execução de shell:** {exc}\n\n"

            break

    # Avisa se já houver uma resposta em andamento (em vez de corromper o
    # histórico compartilhado).
    if _chat_lock.locked():
        async def busy_gen():
            yield (
                "\n\n> ⏳ **Já existe uma resposta em andamento.**\n> "
                "Aguarde ela terminar antes de enviar outra mensagem.\n"
            )
        return StreamingResponse(busy_gen(), media_type="text/plain")

    _inner = event_generator(request)

    async def _serialized():
        # Segura o lock durante todo o stream: o histórico só é tocado
        # por uma resposta de cada vez.
        async with _chat_lock:
            try:
                async for chunk in _inner:
                    yield chunk
            except asyncio.CancelledError:
                # O cliente abortou (botão Parar, Esc ou aba fechada).
                # Encerra o trabalho DE VERDADE — não basta a tela parar:
                #  1. fecha o stream HTTP do modelo, para ele parar de
                #     gerar (e cobrar) tokens que ninguém vai ler;
                #  2. mata comandos de shell ainda em execução.
                try:
                    agent.client.abort_active()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await _inner.aclose()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    _n = kill_active_procs()
                    if _n:
                        print(
                            f"[+] Parada do operador: {_n} subprocesso(s) "
                            f"encerrado(s)."
                        )
                except Exception:  # noqa: BLE001
                    pass
                raise

    return StreamingResponse(
        _serialized(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def run_server(port=8080, allow_shell=False):
    global ALLOW_SHELL
    ALLOW_SHELL = allow_shell

    if not CORE_OK:
        print(f"\n[!] ERRO: núcleo multi-provedor indisponível — {_CORE_ERR}")
        print("[!] Verifique se o pacote 'cassandra/' existe e as dependências estão instaladas.")
        sys.exit(1)

    creds = _active_credentials()
    print(f"\n[+] Iniciando Cassandra WEB na porta {port}...")
    print(f"[+] Acesse: http://localhost:{port}")
    if creds:
        for c in creds:
            print(f"[+] Provedor: {c.label} | modelo: {c.model or '(padrão)'} | chave: ...{c.api_key[-4:]}")
    else:
        print("[!] Nenhuma chave no .env — configure pela interface (⚙ CONFIGURAR API).")
    print(f"[+] Criptografia de envelope: {'ATIVA' if os.getenv('CASSANDRA_ENCRYPT','1') in ('1','true','yes','on') else 'inativa'}")
    print(f"[+] Sanitização de termos:    {'ATIVA' if os.getenv('CASSANDRA_SANITIZE','1') in ('1','true','yes','on') else 'inativa'}")
    if ALLOW_SHELL:
        print("[!] AVISO: MODO SHELL AUTOMÁTICO ATIVADO NA WEB!")

    # --- Encerramento limpo (Ctrl+C) ---
    # Dois problemas faziam o Ctrl+C "não funcionar":
    #   1. o uvicorn espera a requisição em andamento terminar — e um
    #      stream do modelo pode levar minutos;
    #   2. comandos de shell rodam em sessão própria (para podermos matar
    #      o grupo), então NÃO recebem o SIGINT e ficam pendurados.
    # O helper cuida de (2); o timeout abaixo cuida de (1).
    install_shutdown_handlers()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        # Sem isto, o Ctrl+C fica pendurado até a requisição em curso
        # terminar. 3s é suficiente para o stream fechar com elegância.
        timeout_graceful_shutdown=3,
    )
