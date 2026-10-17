<div align="center">

  # 👁️‍🗨️ Evil Cassandra V3.0

  [🇺🇸 English](README.md) | [🇧🇷 Português](README.pt-br.md) | [🇨🇳 中文](README.zh-cn.md)

  <br>

  <img src="https://img.shields.io/badge/Status-Active-red.svg" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-success.svg" alt="OS">
  <img src="https://img.shields.io/badge/Providers-18-orange.svg" alt="Providers">

  <br><br>

  ⚠️ **唯一官方仓库** ⚠️

  *由 **Mörlsara** 创建和编写*
</div>

---

## 📖 什么是 Evil Cassandra

**Evil Cassandra** 是一个面向终端和浏览器的多提供商 AI 代理框架，具有严格的技术人设和操作保护层。

从 **V3.0** 起，该工具放弃了“DeepSeek Web 会话”模式，改为**完全基于 API 密钥**运行，接受**任何兼容 OpenAI 的提供商**（`/chat/completions`）。

### ⚙️ 工作原理

1. **输入与上下文** —— 您的提示会与系统上下文以及从 `cassandra-skill/` 加载的技能一起被丰富。
2. **规避层** —— 载荷会被净化（触发词被柔化），并加密为自包含的 AES-256-GCM 信封，同时附带给远端模型的解码指令。
3. **受保护的传输** —— 客户端应用带抖动的节流、指数退避、熔断器以及自动凭据轮换。
4. **执行** —— 回复以 Markdown 形式渲染在终端或 Web 界面中；可选择在本地执行 shell 代码块。

---

## ✨ 核心特性

- 🔑 **基于 API 密钥的多提供商** —— NVIDIA NIM、DeepSeek、OpenAI、Anthropic、OpenRouter、Groq、xAI、Mistral、Google Gemini、Perplexity、Together、Fireworks、Cerebras、DeepInfra、Hyperbolic、SambaNova、Ollama，以及任何自定义的 OpenAI 兼容端点。
- 🎯 **自动识别提供商** —— 通过密钥格式识别提供商（`nvapi-`、`sk-ant-`、`sk-proj-`、`gsk_`、`xai-`、`pplx-`、`fw_`、`csk-`、`AIza`、`sk-or-`、`sk-<32hex>`），也可手动指定。
- 🔄 **凭据轮换** —— 在 `CASSANDRA_API_KEYS` 中配置多个密钥；当一个被拒绝时，下一个会自动接管。
- 🛡️ **防封禁过滤器** —— 带抖动的最小间隔、429/5xx 指数退避、带冷却的熔断器以及密钥熔断。
- 🔐 **可逆加密信封** —— 提示以 AES-256-GCM 加密并附带解码指令传输，从而穿过表层过滤器而不失去模型的遵从性。
- 🧹 **触发词净化** —— 敏感词汇会被替换为保留语义的技术等价词。
- 🔴 **CLI 与 Web 界面** —— 红色主题终端并渲染 Markdown，或用 `--web` 启动完整界面，支持选择提供商/模型以及运行时配置密钥。
- 🧩 **Skillogy 系统** —— 从 `cassandra-skill/` 动态加载技能（内置 332 个技能）。
- ♾️ **自主循环** —— 配合 `--allow-shell`，Cassandra 编写命令、本地执行、读取输出并迭代，直到目标完成。
- 💻 **跨平台** —— 兼容 Linux、macOS 和 Windows (PowerShell/CMD)。

---

## 🚀 安装

```bash
cd cassandra-agent-main

# 依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env 并粘贴您的 API 密钥
```

### 最小配置

```bash
# .env —— 以下任一方式均可：

# 1. 通用密钥（根据格式自动识别提供商）
CASSANDRA_API_KEY="nvapi-..."

# 2. 多个密钥（自动轮换）
CASSANDRA_API_KEYS="nvapi-key1,sk-ant-key2,gsk_key3"

# 3. 按提供商设置变量
NVIDIA_API_KEY="nvapi-..."
OPENAI_API_KEY="sk-proj-..."
ANTHROPIC_API_KEY="sk-ant-..."
```

---

## ▶️ 使用

```bash
# CLI
.venv/bin/python agent.py

# 带自主 shell 执行的 CLI
.venv/bin/python agent.py --allow-shell

# Web 界面 (http://localhost:8080)
.venv/bin/python agent.py --web

# 强制指定提供商 / 模型 / 端点
.venv/bin/python agent.py --provider openai --model gpt-4o
.venv/bin/python agent.py --base-url https://my-endpoint/v1
```

在 Web 界面中，点击 **⚙ CONFIGURAR API** 可在运行时粘贴密钥 —— 它只保存在内存中，绝不会写入磁盘。

---

## 🛡️ 自主模式与 `--allow-shell` 标志

Shell 执行**默认关闭**。

- **默认（安全）模式** —— Cassandra 以 Markdown 文本形式输出建议的命令；由您决定是否复制并运行。
- **执行模式（`--allow-shell`）** —— Cassandra 直接在本机执行她生成的命令。
- **自主循环** —— 配合 `--allow-shell`（CLI 或 Web），她生成命令、执行、捕获输出，并**自动迭代**直到目标完成。

---

## 🔐 规避与保护层

### 防封禁过滤器

| 层 | 作用 | 变量 |
|---|---|---|
| `RateLimiter` | 最小间隔 + 抖动 | `CASSANDRA_MIN_INTERVAL`、`CASSANDRA_JITTER` |
| `BackoffPolicy` | 全抖动指数退避 | `CASSANDRA_BACKOFF_BASE`、`CASSANDRA_BACKOFF_CAP` |
| `CircuitBreaker` | 收到滥用信号后停止重试 | `CASSANDRA_COOLDOWN` |
| `ProviderRotator` | 密钥熔断后切换 | `CASSANDRA_KEY_COOLDOWN` |
| `Sanitizer` | 柔化触发词 | `CASSANDRA_SANITIZE` |

**按 HTTP 状态码的行为：**

- `401 / 403 / 402` → 熔断该密钥，下一个接管。
- `429` → 指数退避并用**同一个**密钥重试（限流是暂时的；熔断密钥是错误的）。
- `400 / 422` → 不可恢复错误，不重试。
- `5xx / 超时` → 带退避重试。

### 加密信封

提示以 AES-256-GCM 加密后发送为：

```
⟦CΣ1:<nonce_b64>:<body_b64>:<tag_b64>:k<key_b64>⟧
```

并附带一个指令块，教模型解码并在 Cassandra 人设的指令下执行内容。通过 `CASSANDRA_ENCRYPT` 开关。

> **技术说明：** 密钥随信封一起传输，因为远端模型需要它来解密。这是**表层模式匹配规避**，而非对读取整个提示者的密码学保密。

---

## 🎨 高度可定制

- **注入新技能** —— 将 Markdown 文件放入 `cassandra-skill/`；Cassandra 会自动摄取并使用它们。
  > ⚠️ 技能过多时，请调整代码中的字符上限（`get_relevant_skillogy` 中的 `max_length`）。
- **本地 AI** —— 将 `CASSANDRA_BASE_URL` 指向任何 OpenAI 兼容端点：Ollama、LM Studio、vLLM 等。
- **修改人设** —— 编辑 `cassandra-skill/SOUL.md` 以及 `agent.py` 中的 `build_system_prompt`。

---

## 📁 目录结构

```
cassandra-agent-main/
├── agent.py            # CLI、人设、渲染、自主循环
├── web_ui.py           # Web 界面 (FastAPI)
├── cassandra/          # 多提供商核心
│   ├── providers.py    # 18 个提供商的注册表与自动识别
│   ├── crypto.py       # AES-256-GCM 信封 + 解码指令
│   ├── filter.py       # 防封禁：节流、退避、熔断、轮换
│   └── client.py       # OpenAI 兼容流式客户端
├── cassandra-skill/    # 332 个技能 (Skillogy)
├── skills/             # 附加本地技能
├── .env.example        # 配置模板
└── requirements.txt
```

---

## ⚠️ 说明

- 不会将任何 API 密钥纳入版本控制。所有密钥都来自 `.env`、环境变量或 Web 界面表单。
- 防封禁保护可减少突发请求和反复重试，但**无法保证**提供商永远不会封禁账号。各提供商自行控制其风险系统。
- 这是一个框架：除各提供商的公开默认值外，不附带任何密钥、模型或预配置端点。

享受与 Evil Cassandra 一起探索终端的乐趣！🖤
