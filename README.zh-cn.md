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

  <br>

  ![Cassandra 网页界面](model.png)
  *Cassandra V3.0 — 支持多提供商的网页界面*
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
- 💻 **跨平台** —— Linux (Debian/Fedora/Arch)、macOS (Intel/Apple Silicon)、
  Windows (PowerShell/CMD/WSL2)、Android (Termux) 和 Docker。

---

## 🚀 安装

Cassandra 可运行于 **Linux、macOS、Windows 和 Android (Termux)**。请选择您的
平台 —— 所有路径最终都以相同的运行命令结束。

### 通用准备（任意平台）

```bash
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
cp .env.example .env     # 然后编辑 .env 并粘贴您的 API 密钥
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

### 🐧 Linux

**Debian / Ubuntu / Kali / Mint**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 编辑并粘贴您的 API 密钥

python agent.py               # 命令行
python agent.py --allow-shell # 带自主执行的命令行
python agent.py --web         # 网页界面 -> http://localhost:8080
```

**Fedora / RHEL / CentOS / Rocky**

```bash
sudo dnf install -y python3 python3-pip git
# (RHEL/CentOS 可能需要: sudo dnf install -y python3-virtualenv)

git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python agent.py --allow-shell
```

**Arch / Manjaro / EndeavourOS**

```bash
sudo pacman -S --needed python python-pip git

git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python agent.py --allow-shell
```

> **注意：** 在 Debian/Ubuntu 上，如果 `python3 -m venv` 失败，请安装
> `python3-venv`（较新版本还需 `python3-full`）。切勿对系统 Python 执行
> `pip install` —— 请始终使用虚拟环境。

---

### 🍎 macOS

同时支持 **Intel** 和 **Apple Silicon (M1/M2/M3)** —— 步骤完全相同。

```bash
# 1. 安装 Homebrew（如果尚未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Python 3
brew install python@3.12

# 3. 克隆并配置
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 编辑并粘贴您的 API 密钥

# 4. 运行
python agent.py               # 命令行
python agent.py --allow-shell # 带自主执行的命令行
python agent.py --web         # 网页界面 -> http://localhost:8080
```

> **注意：** 在 macOS 上默认 shell 是 `zsh`，但 Cassandra 的命令兼容
> POSIX/bash，可正常运行。`--allow-shell` 授予在您机器上真实执行命令的
> 权限 —— 请谨慎使用。

---

### 🪟 Windows

**方式 A —— PowerShell（推荐）**

```powershell
# 1. 从 https://www.python.org/downloads/ 安装 Python 3.10+
#    （安装时勾选 "Add python.exe to PATH"）

# 2. 克隆并配置
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent

# 3. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

#    如果 PowerShell 阻止执行，请先为您的用户放开：
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 4. 安装依赖
pip install -r requirements.txt

# 5. 配置
copy .env.example .env        # 编辑并粘贴您的 API 密钥

# 6. 运行
python agent.py               # 命令行
python agent.py --allow-shell # 带自主执行的命令行
python agent.py --web         # 网页界面 -> http://localhost:8080
```

**方式 B —— CMD（命令提示符）**

```cmd
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
python agent.py --allow-shell
```

**方式 C —— WSL2（Windows 的 Linux 子系统）**

如果您想要与 Linux 完全一致的行为（bash 命令、POSIX 工具），这是最佳选择。

```powershell
# 在管理员 PowerShell 中执行一次：
wsl --install -d Ubuntu
```

然后，在 WSL 的 Ubuntu 终端中，按上面的 **Debian/Ubuntu** 步骤操作。
Cassandra 作为原生 Linux 进程运行，并输出 `bash` 代码块。

> **Windows 注意事项：**
> - 使用 **Windows Terminal** 或 **PowerShell 7+** 以获得正确的 ANSI 颜色。
>   旧版 `cmd.exe` 和 Windows PowerShell 5.1 可能无法渲染颜色 —— 工具会在
>   不支持时自动检测并禁用颜色。
> - 在自主模式下，Cassandra 在 Windows 上输出 `powershell` / `cmd` 代码块，
>   并原生执行（当命令使用 PowerShell 语法时路由到 `powershell -Command`）。
>   参见下方的 **自主模式**。

---

### 📱 Android (Termux)

```bash
# 1. 从 F-Droid 安装 Termux（不要用 Play Store 版本）

# 2. 更新并安装 Python
pkg update && pkg upgrade -y
pkg install -y python git

# 3. 克隆并配置
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 编辑并粘贴您的 API 密钥

# 4. 运行
python agent.py --allow-shell
```

> **注意：** 在 Termux 上，如果您的 ABI 没有可用的 wheel，某些依赖可能需要
> `pkg install -y build-essential libffi openssl`。网页界面同样可用 —— 在
> 手机浏览器中打开 `http://localhost:8080`。

---

### 🐳 Docker（任意主机）

仓库未附带 Dockerfile，但临时容器即可运行：

```bash
git clone https://github.com/DarkyHArry/cassandra-agent.git
cd cassandra-agent
cp .env.example .env          # 编辑并粘贴您的 API 密钥

docker run --rm -it \
  -v "$PWD":/app -w /app \
  -p 8080:8080 \
  python:3.12-slim \
  bash -lc "pip install -r requirements.txt && python agent.py --web"
```

然后打开 `http://localhost:8080`。若要在容器内自主执行 shell，请添加
`--allow-shell`（容器可将其与您的主机隔离）。

---

## ▶️ 快速使用

### Linux / macOS / Termux
```bash
./cassandra.sh              # 自主交互式命令行
./cassandra.sh --web        # 网页界面 (http://localhost:8080)
./web_ui.py                 # 直接启动网页界面
```

### Windows
```cmd
:: 命令提示符 (CMD)
cassandra.bat
cassandra.bat --web

:: PowerShell
.\cassandra.ps1
.\cassandra.ps1 --web
```

### 直接通过 Python 运行
```bash
# CLI
.venv/bin/python agent.py

# 强制开启自主执行的 CLI
.venv/bin/python agent.py --allow-shell

# Web 界面 (http://localhost:8080)
.venv/bin/python agent.py --web

# 强制指定提供商 / 模型 / 端点
.venv/bin/python agent.py --provider openai --model gpt-4o
.venv/bin/python agent.py --base-url https://my-endpoint/v1
```

在 Web 界面中，点击 **⚙ CONFIGURAR API** 可在运行时粘贴密钥 —— 它只保存在内存中，绝不会写入磁盘。

---

## 🛡️ 自主模式与 Shell 控制

Cassandra **默认处于自主模式**（在 `.env` 中设置 `CASSANDRA_ALLOW_SHELL="1"`）：

- **自主循环开启** —— 接收到实际任务时（创建文件、排查网络、执行命令），她会生成可执行代码块，系统在本地执行后捕获输出回传，她将**自动迭代**直至目标达成。
- **灵活控制**：
  - **在 Web 界面：** 点击顶部的 **`⚡ SHELL: AUTÔNOMO`** 按钮一键切换。
  - **在 CLI：** 使用 `--allow-shell`（默认）或 `--no-allow-shell` 关闭。
  - **在 `.env`：** 配置 `CASSANDRA_ALLOW_SHELL="1"`（启用）或 `"0"`（受限）。
- **受限模式（无 shell）** —— 关闭时，命令仅以 Markdown 文本输出供人工查阅复制。

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

> ⚠️ **默认关闭（`CASSANDRA_ENCRYPT=0`）。** 语言模型不会执行 AES-GCM：开启信封后，它们收到的是密文，会卡在尝试解密上而不是作答。除非您清楚自己在做什么，否则请保持关闭 —— 真正有效的规避层是净化（sanitization）。

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
