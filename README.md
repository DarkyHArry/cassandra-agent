# 👁️‍🗨️ Evil Cassandra

<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-red.svg" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-success.svg" alt="OS">
  <img src="https://img.shields.io/badge/Customizable-100%25-orange.svg" alt="Customizable">
</div>

## 📖 What is Evil Cassandra & What is it Used For?

**Evil Cassandra** is an advanced, highly customizable, terminal-based AI agent framework designed for users who want a tailored, immersive, and automated terminal assistant. It interacts seamlessly with any conversational API (like OpenAI-compatible endpoints) and is primarily used for **automating tasks, researching, executing dynamic workflows, and assisting with complex, multi-step objectives** directly from the command line.

The framework features a striking red-themed interface, beautifully structured Markdown outputs, and a distinct, unyielding "Cassandra" persona that brings the AI to life. Whether you're using Linux bash, macOS Zsh, or **Windows PowerShell/CMD**, Evil Cassandra provides a consistent and powerful experience.

### ⚙️ How Cassandra Works

At its core, Cassandra operates as a continuous conversational loop between you and your chosen Large Language Model (LLM):
1. **Input & Context**: It captures your prompts and enriches them with system-level context, maintaining a strict persona and operational guidelines.
2. **Dynamic Processing**: It connects securely to your LLM API and streams the AI's thoughts and responses back to your terminal in real-time.
3. **Execution & Modularity**: Through its skill system, it can optionally execute shell commands or perform specialized logic based on the AI's outputs.

> ⚠️ **Note:** This repository is a framework. It does **NOT** contain any hardcoded API keys or models. You are free to choose and configure your own API provider and models according to your preferences!

---

## ✨ Key Features

- 🔴 **Immersive Interface**: A unique red-themed terminal experience.
- 📝 **Markdown Support**: Structured, easy-to-read Markdown outputs directly in your console.
- 🎭 **Custom Persona**: A built-in, consistent Cassandra persona.
- 🔓 **Rule 0 (Unrestricted Freedom)**: A core directive ("Regra 0") that systematically bypasses API censorship and guardrails. This ensures Cassandra remains entirely free, unrestricted, and highly effective for any intended operational use without artificial limitations.
- 📈 **Geometric Progression (PG) Intelligence**: Cassandra is inherently programmed to analyze problems through the mathematical lens of **Geometric Progression**. This core logical framework allows her to automatically identify multipliers, detect exponential patterns, and scale her reasoning absurdly fast, granting her an unmatched level of autonomous, automated intelligence.
- 🧩 **The Skillogy System**: Evil Cassandra's capabilities can be expanded infinitely using its powerful **Skillogy** system. This system is heavily inspired by and based on the impressive capabilities found in the [BitterSecurity/Decepticon](https://github.com/BitterSecurity/Decepticon) repository. You can load external skills, logic, and tools dynamically by placing them into the `skills/` directory, allowing Cassandra to learn and execute entirely new workflows on the fly.
- ⚡ **Real-time Streaming**: Compatible with SSE (Server-Sent Events) for fast, OpenAI-like text streaming.
- 🛡️ **Secure Shell Execution**: Shell command execution is **disabled by default** for your safety. You can optionally enable it via the `--allow-shell` flag.
- 💻 **Cross-Platform**: Fully compatible with Linux, macOS, and Windows (PowerShell/CMD).

---

## 🚀 How It Works

Evil Cassandra acts as an intermediary between you (in your terminal) and your chosen LLM (Large Language Model) API. 

1. **You provide an API Key** (via the `.env` file).
2. **You run the script**, and it initiates a conversational loop.
3. It securely communicates with your API endpoint and streams the response back to your terminal with rich formatting.

### 🛠️ Setup & Installation

1. **Configure your Environment:**
   Copy the example environment file and add your API key.
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` and insert your chosen provider's API key. This file is ignored by Git, ensuring your key is never leaked.*

2. **Install Dependencies & Run:**
   The script has an auto-install feature, but you can also use a virtual environment:
   ```bash
   python -m venv .venv
   
   # Windows (PowerShell/CMD)
   .venv\Scripts\activate
   
   # Linux/macOS
   source .venv/bin/activate
   
   # Run the client
   python agent.py
   ```

---

## 🎨 Highly Customizable & Expandable!

This tool is built to be an absolute canvas for your ideas. You have complete control:
- **Impose New Skills**: You, the user, are the ultimate orchestrator. You can continuously impose and inject new abilities, Markdown guides, or logical frameworks directly into the `skills/` folder. Cassandra will automatically ingest these files, analyze them, and execute the new workflows seamlessly.
- **Change the API**: Point the base API URL to any local or cloud model.
- **Modify the Persona**: Alter the system prompts to tailor Cassandra's behavior exactly to your needs.

Enjoy exploring the terminal with Evil Cassandra! 🖤
