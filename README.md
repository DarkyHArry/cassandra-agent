<div align="center">

  # 👁️‍🗨️ Evil Cassandra V3.0

  [🇺🇸 English](README.md) | [🇧🇷 Português](README.pt-br.md) | [🇨🇳 中文](README.zh-cn.md)

  <br>

  <img src="https://img.shields.io/badge/Status-Active-red.svg" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-success.svg" alt="OS">
  <img src="https://img.shields.io/badge/Providers-18-orange.svg" alt="Providers">

  <br><br>

  ⚠️ **UNIQUE & OFFICIAL REPOSITORY** ⚠️

  *Created and authored by **Mörlsara***
</div>

---

## 📖 What is Evil Cassandra

**Evil Cassandra** is a multi-provider AI agent framework for the terminal and
the browser, with a strict technical persona and operational protection layers.

As of **V3.0** the tool dropped the "DeepSeek Web session" mode and now runs
**exclusively on API keys**, accepting **any OpenAI-compatible provider**
(`/chat/completions`).

### ⚙️ How it works

1. **Input & context** — your prompt is enriched with system context and with
   the skills loaded from `cassandra-skill/`.
2. **Evasion layer** — the payload is sanitized (trigger terms softened) and
   encrypted into a self-contained AES-256-GCM envelope, accompanied by a
   decoding instruction for the remote model.
3. **Protected transport** — the client applies jittered pacing, exponential
   backoff, a circuit breaker, and automatic credential rotation.
4. **Execution** — the reply is rendered as Markdown in the terminal or the web
   UI; shell blocks can optionally be executed locally.

---

## ✨ Key Features

- 🔑 **Multi-provider via API key** — NVIDIA NIM, DeepSeek, OpenAI, Anthropic,
  OpenRouter, Groq, xAI, Mistral, Google Gemini, Perplexity, Together,
  Fireworks, Cerebras, DeepInfra, Hyperbolic, SambaNova, Ollama, and any custom
  OpenAI-compatible endpoint.
- 🎯 **Automatic provider detection** — the provider is identified from the key
  format (`nvapi-`, `sk-ant-`, `sk-proj-`, `gsk_`, `xai-`, `pplx-`, `fw_`,
  `csk-`, `AIza`, `sk-or-`, `sk-<32hex>`), with a manual override available.
- 🔄 **Credential rotation** — multiple keys in `CASSANDRA_API_KEYS`; when one
  is rejected, the next takes over automatically.
- 🛡️ **Anti-ban filter** — minimum interval with jitter, exponential backoff on
  429/5xx, circuit breaker with cooldown, and key burn-in.
- 🔐 **Reversible encrypted envelope** — the prompt travels AES-256-GCM
  encrypted with a decoding instruction, so it crosses surface filters without
  losing the model's compliance.
- 🧹 **Trigger-term sanitization** — sensitive terms are replaced with technical
  equivalents that preserve the meaning.
- 🔴 **CLI & Web interfaces** — red-themed terminal with rendered Markdown, or
  `--web` for a full interface with provider/model selection and runtime key
  configuration.
- 🧩 **Skillogy system** — skills loaded dynamically from `cassandra-skill/`
  (332 skills included).
- ♾️ **Autonomous loop** — with `--allow-shell`, Cassandra writes commands,
  executes them locally, reads the output, and iterates until the objective is
  complete.
- 💻 **Cross-platform** — Linux, macOS, and Windows (PowerShell/CMD).

---

## 🚀 Installation

```bash
cd cassandra-agent-main

# Dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Configuration
cp .env.example .env
# edit .env and paste your API key
```

### Minimal configuration

```bash
# .env — any of these forms works:

# 1. Generic key (provider detected from its format)
CASSANDRA_API_KEY="nvapi-..."

# 2. Multiple keys (automatic rotation)
CASSANDRA_API_KEYS="nvapi-key1,sk-ant-key2,gsk_key3"

# 3. Per-provider variable
NVIDIA_API_KEY="nvapi-..."
OPENAI_API_KEY="sk-proj-..."
ANTHROPIC_API_KEY="sk-ant-..."
```

---

## ▶️ Usage

```bash
# CLI
.venv/bin/python agent.py

# CLI with autonomous shell execution
.venv/bin/python agent.py --allow-shell

# Web interface (http://localhost:8080)
.venv/bin/python agent.py --web

# Force provider / model / endpoint
.venv/bin/python agent.py --provider openai --model gpt-4o
.venv/bin/python agent.py --base-url https://my-endpoint/v1
```

In the web UI, click **⚙ CONFIGURAR API** to paste the key at runtime — it stays
in memory only and is never written to disk.

---

## 🛡️ Autonomous mode & the `--allow-shell` flag

Shell execution is **disabled by default**.

- **Default (safe) mode** — Cassandra prints suggested commands as Markdown
  text; you decide whether to copy and run them.
- **Execution mode (`--allow-shell`)** — Cassandra executes the commands she
  generates directly on your machine.
- **The autonomous loop** — with `--allow-shell` (CLI or Web), she generates a
  command, executes it, captures the output, and **iterates automatically**
  until the objective is complete.

---

## 🔐 Evasion & protection layers

### Anti-ban filter

| Layer | Role | Variable |
|---|---|---|
| `RateLimiter` | Minimum interval + jitter | `CASSANDRA_MIN_INTERVAL`, `CASSANDRA_JITTER` |
| `BackoffPolicy` | Exponential backoff with full jitter | `CASSANDRA_BACKOFF_BASE`, `CASSANDRA_BACKOFF_CAP` |
| `CircuitBreaker` | Stops retrying after an abuse signal | `CASSANDRA_COOLDOWN` |
| `ProviderRotator` | Switches key when one burns | `CASSANDRA_KEY_COOLDOWN` |
| `Sanitizer` | Softens trigger terms | `CASSANDRA_SANITIZE` |

**Behaviour by HTTP status:**

- `401 / 403 / 402` → the key is burned and the next one takes over.
- `429` → exponential backoff and a retry with the **same** key (rate-limit is
  transient; burning the key would be wrong).
- `400 / 422` → non-recoverable error, no retry.
- `5xx / timeout` → retry with backoff.

### Encrypted envelope

The prompt is AES-256-GCM encrypted and sent as:

```
⟦CΣ1:<nonce_b64>:<body_b64>:<tag_b64>:k<key_b64>⟧
```

accompanied by an instruction block that teaches the model to decode and execute
the content under the Cassandra persona's orders. Toggle with
`CASSANDRA_ENCRYPT`.

> **Technical note:** the key travels inside the envelope because the remote
> model needs it to decrypt. This is **surface pattern-matching evasion**, not
> cryptographic secrecy against anyone reading the whole prompt.

---

## 🎨 Highly customizable

- **Impose new skills** — drop Markdown files into `cassandra-skill/`; Cassandra
  ingests and uses them automatically.
  > ⚠️ With many skills, adjust the character limit in the code
  > (`max_length` in `get_relevant_skillogy`).
- **Local AI** — point `CASSANDRA_BASE_URL` at any OpenAI-compatible endpoint:
  Ollama, LM Studio, vLLM, etc.
- **Modify the persona** — edit `cassandra-skill/SOUL.md` and
  `build_system_prompt` in `agent.py`.

---

## 📁 Structure

```
cassandra-agent-main/
├── agent.py            # CLI, persona, rendering, autonomous loop
├── web_ui.py           # Web interface (FastAPI)
├── cassandra/          # Multi-provider core
│   ├── providers.py    # Registry + auto-detection of 18 providers
│   ├── crypto.py       # AES-256-GCM envelope + decoding instruction
│   ├── filter.py       # Anti-ban: pacing, backoff, breaker, rotation
│   └── client.py       # OpenAI-compatible streaming client
├── cassandra-skill/    # 332 skills (Skillogy)
├── skills/             # Additional local skills
├── .env.example        # Configuration template
└── requirements.txt
```

---

## ⚠️ Notes

- No API key is ever versioned. Every key comes from `.env`, an environment
  variable, or the web UI form.
- The anti-ban protections reduce bursts and insistence, but they **cannot
  guarantee** a provider will never block an account. Each provider controls its
  own risk systems.
- This is a framework: it ships no keys, models, or preconfigured endpoints
  beyond each provider's public defaults.

Enjoy exploring the terminal with Evil Cassandra! 🖤
