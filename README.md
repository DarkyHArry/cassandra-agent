# 👁️‍🗨️ Evil Cassandra

<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-red.svg" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-success.svg" alt="OS">
  <img src="https://img.shields.io/badge/Customizable-100%25-orange.svg" alt="Customizable">
</div>

## 📖 What is Evil Cassandra?

**Evil Cassandra** is a highly customizable, terminal-based AI client designed to interact with any generic conversational API (like OpenAI-compatible endpoints). It features a striking red-themed terminal interface, structured Markdown outputs, and a distinct, consistent persona.

Whether you're using Linux bash, macOS Zsh, or **Windows PowerShell/CMD**, Evil Cassandra is designed to work seamlessly.

> ⚠️ **Note:** This repository is a framework. It does **NOT** contain any hardcoded API keys or models. You are free to choose and configure your own API provider and models according to your preferences!

---

## ✨ Key Features

- 🔴 **Immersive Interface**: A unique red-themed terminal experience.
- 📝 **Markdown Support**: Structured, easy-to-read Markdown outputs directly in your console.
- 🎭 **Custom Persona**: A built-in, consistent Cassandra persona.
- 🧩 **Extensible Skills**: Load external capabilities (Skillogy) via files in the `skills/` directory.
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

## 🎨 Highly Customizable!

This tool is built to be a canvas for your ideas. You can:
- Change the base API URL to point to any local or cloud model.
- Modify the system prompt to alter the Cassandra persona.
- Add completely new Python scripts into the `skills/` folder to extend what Cassandra can do.

Enjoy exploring the terminal with Evil Cassandra! 🖤
