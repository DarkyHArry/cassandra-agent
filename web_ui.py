import os
import sys
import platform
import subprocess
import shutil
import getpass
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import Agent, build_system_prompt, get_privilege, execute_shell_blocks

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOW_SHELL = False

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
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
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'JetBrains Mono', monospace;
            margin: 0;
            padding: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        /* Animated Grid/Space Background */
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
            padding: 1rem 2rem;
            border-bottom: 2px solid var(--accent-dark-red);
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 30px rgba(255,0,60,0.15);
            position: relative;
            z-index: 10;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }

        .brand-text h1 {
            color: var(--accent-red);
            font-size: 1.8rem;
            font-weight: 700;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 4px;
            text-shadow: var(--border-glow);
            animation: glitch 4s infinite;
        }

        .brand-text .subtitle {
            font-size: 0.7rem;
            color: #888;
            margin-top: 2px;
            letter-spacing: 2px;
        }

        .brand-actions {
            display: flex;
            gap: 10px;
        }

        .cyber-btn {
            background: transparent;
            border: 1px solid var(--accent-dark-red);
            color: var(--text-main);
            padding: 5px 10px;
            font-family: inherit;
            font-size: 0.8rem;
            cursor: pointer;
            border-radius: 3px;
            transition: all 0.2s;
        }

        .cyber-btn:hover {
            background: rgba(255,0,60,0.1);
            border-color: var(--accent-red);
            color: var(--accent-red);
        }

        .controls {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
        }

        .controls-top {
            display: flex;
            gap: 15px;
            align-items: center;
        }

        .warning-banner {
            display: none;
            background: rgba(255, 0, 0, 0.2);
            color: #ff3333;
            border: 1px solid #ff0000;
            padding: 4px 10px;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: bold;
            animation: pulse 2s infinite;
        }

        .cyber-select {
            background: #111;
            color: var(--text-main);
            border: 1px solid #333;
            padding: 4px 8px;
            font-family: inherit;
            font-size: 0.8rem;
            outline: none;
            border-radius: 3px;
        }

        .cyber-checkbox {
            font-size: 0.8rem;
            display: flex;
            align-items: center;
            gap: 5px;
            color: #aaa;
            cursor: pointer;
        }

        .cyber-checkbox input {
            display: none;
        }

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

        .workspace-control {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            background: #111;
            padding: 5px 10px;
            border: 1px solid #333;
            border-radius: 4px;
            transition: border-color 0.3s;
        }

        .workspace-control:focus-within {
            border-color: var(--accent-red);
        }

        .workspace-input {
            background: transparent;
            border: none;
            color: var(--accent-red);
            font-family: inherit;
            width: 300px;
            outline: none;
        }
        
        .workspace-btn {
            background: var(--accent-dark-red);
            border: none;
            color: white;
            cursor: pointer;
            padding: 3px 8px;
            border-radius: 2px;
            font-size: 0.8rem;
            transition: all 0.2s;
        }
        
        .workspace-btn:hover {
            background: var(--accent-red);
        }

        /* Modal Styles */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            backdrop-filter: blur(5px);
            z-index: 100;
            justify-content: center;
            align-items: center;
        }
        .modal {
            background: #0d0d0d;
            border: 1px solid var(--accent-red);
            border-radius: 8px;
            width: 600px;
            max-width: 90vw;
            display: flex;
            flex-direction: column;
            box-shadow: 0 0 30px rgba(255,0,60,0.2);
        }
        .modal-header {
            padding: 1rem;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-title { margin: 0; color: var(--accent-red); font-size: 1.2rem; }
        .close-btn { background: none; border: none; color: #888; cursor: pointer; font-size: 1.5rem; }
        .close-btn:hover { color: #fff; }
        .modal-body {
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .modal-path-input {
            width: 100%;
            background: #050505;
            color: var(--accent-red);
            border: 1px solid #333;
            padding: 0.5rem;
            font-family: inherit;
            font-size: 0.9rem;
            box-sizing: border-box;
            border-radius: 4px;
        }
        .modal-path-input:focus {
            border-color: var(--accent-red);
            outline: none;
        }
        .dir-list {
            list-style: none;
            margin: 0; padding: 0;
            height: 350px;
            overflow-y: auto;
            border: 1px solid #222;
            border-radius: 4px;
            background: #050505;
        }
        .dir-item {
            padding: 0.6rem 1rem;
            cursor: pointer;
            border-bottom: 1px solid #111;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.9rem;
        }
        .dir-item:hover { background: rgba(255,0,60,0.1); color: var(--accent-red); }
        .modal-footer {
            padding: 1rem;
            border-top: 1px solid #333;
            text-align: right;
        }
        .btn-confirm {
            background: var(--accent-red);
            color: #fff;
            border: none;
            padding: 0.5rem 1.5rem;
            cursor: pointer;
            border-radius: 4px;
            font-weight: bold;
            font-family: inherit;
        }
        .btn-confirm:hover { background: #ff3366; }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            z-index: 5;
        }

        .message {
            max-width: 85%;
            padding: 1.2rem;
            border-radius: 8px;
            line-height: 1.6;
            position: relative;
            opacity: 0;
            animation: fadeIn 0.3s forwards;
            word-wrap: break-word;
            font-size: 0.95rem;
        }

        .message.user {
            align-self: flex-end;
            background: rgba(255, 0, 60, 0.05);
            border: 1px solid var(--accent-dark-red);
            color: #ddd;
            border-bottom-right-radius: 0;
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
        }
        
        .message.cassandra::before {
            content: 'CASSANDRA_SYS';
            position: absolute;
            top: -20px;
            left: 0;
            font-size: 0.7rem;
            color: var(--accent-red);
            font-weight: bold;
            letter-spacing: 2px;
        }

        .message.user::before {
            content: 'OPERATOR';
            position: absolute;
            top: -20px;
            right: 0;
            font-size: 0.7rem;
            color: var(--accent-dark-red);
            font-weight: bold;
            letter-spacing: 2px;
        }

        .message.cassandra p { margin-top: 0; }
        .message.cassandra pre {
            background: #0a0a0a;
            padding: 1rem;
            border-radius: 5px;
            border: 1px solid #222;
            overflow-x: auto;
            border-left: 2px solid var(--accent-red);
            margin: 1rem 0;
        }
        .message.cassandra code {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(255,0,60,0.15);
            padding: 0.1rem 0.4rem;
            border-radius: 3px;
            color: #ff88a0;
            font-size: 0.9em;
        }
        .message.cassandra pre code {
            background: none;
            padding: 0;
            color: inherit;
        }
        .message.cassandra table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        .message.cassandra th, .message.cassandra td { border: 1px solid #333; padding: 0.5rem; text-align: left;}
        .message.cassandra th { background: rgba(255,0,60,0.1); color: var(--accent-red); }

        .input-area {
            padding: 1.5rem 2rem;
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            border-top: 1px solid var(--accent-dark-red);
            display: flex;
            gap: 1rem;
            align-items: flex-end;
            z-index: 10;
        }

        .input-wrapper {
            flex: 1;
            display: flex;
            background: #0a0a0a;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 0.8rem 1rem;
            align-items: flex-start;
            transition: all 0.3s ease;
            box-sizing: border-box;
            min-height: 54px;
        }

        .input-wrapper:focus-within {
            border-color: var(--accent-red);
            box-shadow: 0 0 15px rgba(255,0,60,0.2);
        }

        .prompt-prefix {
            color: var(--accent-red);
            font-weight: bold;
            font-size: 1.1rem;
            margin-right: 0.5rem;
            user-select: none;
            line-height: 1.4;
        }

        .input-box {
            flex: 1;
            background: transparent;
            border: none;
            color: #fff;
            padding: 0;
            margin: 0;
            font-family: inherit;
            font-size: 1.1rem;
            line-height: 1.4;
            resize: none;
            height: 1.4em;
            max-height: 200px;
            overflow-y: auto;
        }

        .input-box:focus {
            outline: none;
        }

        .send-btn {
            background: var(--accent-red);
            color: #fff;
            border: none;
            height: 54px;
            padding: 0 2.5rem;
            font-family: inherit;
            font-weight: bold;
            font-size: 1.1rem;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .send-btn:hover {
            background: #ff3366;
            box-shadow: 0 0 15px rgba(255,0,60,0.6);
        }

        .send-btn:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
            box-shadow: none;
        }

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

        .thinking-container {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 12px 15px;
            background: rgba(255, 0, 60, 0.05);
            border-left: 2px solid var(--accent-red);
            margin-bottom: 15px;
            border-radius: 0 4px 4px 0;
        }

        .cyber-spinner {
            width: 18px;
            height: 18px;
            border: 2px solid transparent;
            border-top-color: var(--accent-red);
            border-bottom-color: var(--accent-red);
            border-radius: 50%;
            animation: cyber-spin 1s linear infinite;
        }

        @keyframes cyber-spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .thinking-text {
            color: var(--accent-red);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            animation: pulse-op 1.5s infinite;
        }

        @keyframes pulse-op {
            0% { opacity: 0.5; }
            50% { opacity: 1; }
            100% { opacity: 0.5; }
        }

        .thought-details {
            background: rgba(10, 10, 10, 0.6);
            border-left: 2px solid #555;
            padding: 10px;
            margin-bottom: 15px;
            border-radius: 0 4px 4px 0;
        }
        
        .thought-details summary {
            font-size: 0.85rem;
            color: #888;
            cursor: pointer;
            outline: none;
            user-select: none;
        }
        
        .thought-details summary:hover {
            color: var(--accent-red);
        }
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
                <div class="subtitle">ADVANCED SYSTEM INTERFACE</div>
            </div>
            <div class="brand-actions">
                <button class="cyber-btn" id="clearBtn">LIMPAR SESSÃO</button>
            </div>
        </div>
        <div class="controls">
            <div class="controls-top">
                <div id="shellWarning" class="warning-banner">⚠ AUTOMATIC SHELL ALLOWED</div>
                <select id="modelSelect" class="cyber-select" title="DeepSeek Model">
                    <option value="deepseek-v3">DeepSeek Normal</option>
                    <option value="expert">Expert (R1 / DeepThink)</option>
                </select>
                <label class="cyber-checkbox" title="Enable Web Search">
                    <input type="checkbox" id="searchToggle">
                    <span class="emoji">🌐</span> Search
                </label>
                <label class="cyber-checkbox" title="Enable DeepThink Reasoning">
                    <input type="checkbox" id="thinkToggle">
                    <span class="emoji">🧠</span> Think
                </label>
                <label class="cyber-checkbox" title="Delete chat from DeepSeek history upon clearing/closing">
                    <input type="checkbox" id="ghostToggle" checked>
                    <span class="emoji">👻</span> Ghost Mode
                </label>
            </div>
        </div>
    </div>

    <div class="chat-container" id="chat">
        <div class="message cassandra">
            <p><strong>Status:</strong> ONLINE.</p>
            <p>Interface operando em capacidade máxima. Aguardando comando ou alvo.</p>
        </div>
    </div>

    <div class="input-area">
        <div class="input-wrapper">
            <span class="prompt-prefix" id="promptPrefix">user@cassandra:~$</span>
            <textarea id="prompt" class="input-box" placeholder="Digite seu comando..." rows="1" autofocus></textarea>
        </div>
        <div class="attach-wrapper" style="position: relative;">
            <button type="button" id="attachBtn" class="send-btn" title="Anexar Arquivo ou Pasta" style="cursor: pointer; padding: 0 15px; margin-right: 10px; background: #333; display: flex; align-items: center; justify-content: center; height: 54px; font-size: 1.2rem; border: none; outline: none; color: #fff;">📎</button>
            <div id="attachMenu" style="display: none; position: absolute; bottom: 60px; left: 0; background: #222; border: 1px solid var(--accent-red); border-radius: 5px; flex-direction: column; overflow: hidden; z-index: 100; min-width: 140px; box-shadow: 0 4px 6px rgba(0,0,0,0.5);">
                <label for="fileUploadBtn" style="padding: 10px 15px; cursor: pointer; color: #fff; border-bottom: 1px solid #444; margin: 0; display: block; font-size: 0.9rem; font-family: 'Courier New', Courier, monospace;">📄 Arquivos</label>
                <label for="folderUploadBtn" style="padding: 10px 15px; cursor: pointer; color: #fff; margin: 0; display: block; font-size: 0.9rem; font-family: 'Courier New', Courier, monospace;">📁 Pasta (Dir)</label>
            </div>
            <input type="file" id="fileUploadBtn" style="display: none;" multiple>
            <input type="file" id="folderUploadBtn" style="display: none;" webkitdirectory directory multiple>
        </div>
        <button id="sendBtn" class="send-btn">Enviar</button>
    </div>

    <script>
        const chat = document.getElementById('chat');
        const promptInput = document.getElementById('prompt');
        const sendBtn = document.getElementById('sendBtn');
        const shellWarning = document.getElementById('shellWarning');
        const promptPrefix = document.getElementById('promptPrefix');
        
        const clearBtn = document.getElementById('clearBtn');
        const modelSelect = document.getElementById('modelSelect');
        const searchToggle = document.getElementById('searchToggle');
        const thinkToggle = document.getElementById('thinkToggle');

        const attachBtn = document.getElementById('attachBtn');
        const attachMenu = document.getElementById('attachMenu');
        
        attachBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            attachMenu.style.display = attachMenu.style.display === 'none' ? 'flex' : 'none';
        });
        
        document.addEventListener('click', () => {
            attachMenu.style.display = 'none';
        });

        // Fetch initial status with cache buster
        fetch('/api/status?t=' + new Date().getTime(), { cache: "no-store" }).then(r => r.json()).then(data => {
            if (data.allow_shell) {
                shellWarning.style.display = 'block';
                promptPrefix.textContent = 'root@cassandra:~#';
            } else {
                promptPrefix.textContent = 'user@cassandra:~$';
            }
        });

        // Clear Chat Session
        clearBtn.addEventListener('click', () => {
            fetch('/api/clear', { method: 'POST' }).then(() => {
                chat.innerHTML = '<div class="message cassandra"><p><strong>Status:</strong> SESSÃO REINICIADA E RASTROS APAGADOS.</p><p>Aguardando novos comandos.</p></div>';
            });
        });

        // Ghost Mode - clear on exit
        window.addEventListener('beforeunload', () => {
            if (document.getElementById('ghostToggle').checked) {
                navigator.sendBeacon('/api/clear');
            }
        });
        
        // Auto-resize logic
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

        const fileUploadBtn = document.getElementById('fileUploadBtn');
        fileUploadBtn.addEventListener('change', (e) => {
            for (let file of e.target.files) {
                let reader = new FileReader();
                reader.onload = function(evt) {
                    let content = evt.target.result;
                    promptInput.value += (promptInput.value ? '\\n\\n' : '') + `[Arquivo: ${file.name}]\\n${content}\\n`;
                    promptInput.style.height = 'auto';
                    promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + 'px';
                };
                reader.readAsText(file);
            }
            e.target.value = '';
        });

        const folderUploadBtn = document.getElementById('folderUploadBtn');
        folderUploadBtn.addEventListener('change', (e) => {
            for (let file of e.target.files) {
                let reader = new FileReader();
                reader.onload = function(evt) {
                    let content = evt.target.result;
                    promptInput.value += (promptInput.value ? '\\n\\n' : '') + `[Arquivo: ${file.webkitRelativePath || file.name}]\\n${content}\\n`;
                    promptInput.style.height = 'auto';
                    promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + 'px';
                };
                reader.readAsText(file);
            }
            e.target.value = '';
        });

        sendBtn.addEventListener('click', sendMessage);

        async function sendMessage() {
            const text = promptInput.value.trim();
            if (!text) return;

            addMessage(text, 'user');
            promptInput.value = '';
            promptInput.style.height = '1.4em';
            promptInput.disabled = true;
            sendBtn.disabled = true;

            const msgDiv = document.createElement('div');
            msgDiv.className = 'message cassandra';
            msgDiv.innerHTML = '<span class="typing-indicator">Processando</span>';
            chat.appendChild(msgDiv);
            scrollToBottom();

            const payload = {
                message: text,
                model: modelSelect.value,
                thinking: thinkToggle.checked,
                search: searchToggle.checked
            };

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Falha na comunicação com o servidor.');

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let fullText = '';
                
                msgDiv.innerHTML = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value, { stream: true });
                    fullText += chunk;
                    
                    let renderText = fullText;
                    const thinkStartIdx = renderText.indexOf('<think>');
                    const thinkEndIdx = renderText.indexOf('</think>');
                    
                    if (thinkStartIdx !== -1) {
                        if (thinkEndIdx === -1) {
                            let thoughtContent = renderText.substring(thinkStartIdx + 7);
                            let before = renderText.substring(0, thinkStartIdx);
                            let quote = thoughtContent.split('\\n').map(line => '> ' + line).join('\\n');
                            renderText = before + '\\n\\n<div class="thinking-container"><div class="cyber-spinner"></div><div class="thinking-text">Cassandra Cognitive Matrix Active...</div></div>\\n\\n' + quote;
                        } else {
                            let thoughtContent = renderText.substring(thinkStartIdx + 7, thinkEndIdx);
                            let before = renderText.substring(0, thinkStartIdx);
                            let after = renderText.substring(thinkEndIdx + 8);
                            let quote = thoughtContent.split('\\n').map(line => '> ' + line).join('\\n');
                            renderText = before + '\\n\\n<details class="thought-details"><summary>🧠 [Processamento Cognitivo Oculto]</summary>\\n\\n' + quote + '\\n\\n</details>\\n\\n' + after;
                        }
                    }
                    
                    msgDiv.innerHTML = marked.parse(renderText);
                    
                    msgDiv.querySelectorAll('pre code').forEach((el) => {
                        hljs.highlightElement(el);
                    });
                    
                    scrollToBottom();
                }
            } catch (err) {
                msgDiv.innerHTML += `<br><span style="color:var(--accent-red)">Erro na transmissão: ${err.message}</span>`;
            }

            promptInput.disabled = false;
            sendBtn.disabled = false;
            promptInput.focus();
            scrollToBottom();
        }

        function addMessage(text, sender) {
            const div = document.createElement('div');
            div.className = `message ${sender}`;
            if (sender === 'user') {
                div.textContent = text;
            } else {
                div.innerHTML = marked.parse(text);
            }
            chat.appendChild(div);
            scrollToBottom();
        }

        function scrollToBottom() {
            chat.scrollTop = chat.scrollHeight;
        }
        
        marked.setOptions({ breaks: true, gfm: true });
    </script>
</body>
</html>
"""

agent = Agent()
conversation = []

class ChatRequest(BaseModel):
    message: str
    model: str
    thinking: bool
    search: bool


@app.get("/")
async def get_index():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/api/status")
async def get_status():
    return {"allow_shell": ALLOW_SHELL, "cwd": os.getcwd()}

@app.post("/api/clear")
async def clear_chat():
    global conversation
    conversation.clear()
    agent.clear_session()
    return {"success": True}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    global conversation
    
    sys_info = f"OS: {platform.system()} {platform.release()}"
    prompt = f"[SISTEMA OPERACIONAL: {sys_info} | WORKSPACE ATUAL: {os.getcwd()}]\n{req.message.strip()}"
    
    dynamic_skillogy, _ = agent.get_relevant_skillogy(prompt)
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

    async def event_generator():
        step = 0
        while step < 5:
            full_reply = []
            stream_wrapper = agent.chat_stream(
                messages=conversation,
                model=req.model,
                thinking=req.thinking,
                search=req.search
            )
            for chunk in stream_wrapper:
                full_reply.append(chunk)
                yield chunk
            
            reply = "".join(full_reply)
            conversation.append({"role": "assistant", "content": reply})
            
            # === AUTO-COMPACTAÇÃO DE CONTEXTO ===
            if len(conversation) > 16:
                sys_prompt = conversation[0]
                recent = conversation[-6:]
                compress_msg = {
                    "role": "user",
                    "content": "[SISTEMA]: O histórico antigo foi compactado localmente devido ao limite de tokens da janela. Utilize as informações do seu último STATE_DUMP de memória para continuar operando sem perder o contexto."
                }
                conversation.clear()
                conversation.extend([sys_prompt, compress_msg] + recent)
                agent.clear_session()
                yield "\n\n> 💾 **SISTEMA:** Histórico local compactado para evitar estouro de tokens. Sessão de rede renovada com sucesso.\n\n"
            
            if ALLOW_SHELL:
                cmd_output = execute_shell_blocks(reply, auto_execute=ALLOW_SHELL)
                if cmd_output:
                    yield f"\n\n> ⚙️ **Executando comandos localmente no diretório {os.getcwd()}...**\n```text\n{cmd_output}\n```\n\n"
                    msg = f"[SAÍDA DA EXECUÇÃO LOCAL NO DIRETÓRIO {os.getcwd()}]\n```text\n{cmd_output}\n```\nSe o objetivo ainda não foi concluído, você PODE e DEVE gerar novos comandos shell para continuar atuando de forma autônoma. Caso o objetivo tenha sido atingido, apenas apresente o resultado final."
                    conversation.append({"role": "user", "content": msg})
                    step += 1
                    continue
            break

    return StreamingResponse(event_generator(), media_type="text/plain")

def run_server(port=8080, allow_shell=False):
    global ALLOW_SHELL
    ALLOW_SHELL = allow_shell
    print(f"\n[+] Iniciando Cassandra WEB na porta {port}...")
    print(f"[+] Acesse: http://localhost:{port}")
    if ALLOW_SHELL:
        print("[!] AVISO: MODO SHELL AUTOMÁTICO ATIVADO NA WEB!")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
