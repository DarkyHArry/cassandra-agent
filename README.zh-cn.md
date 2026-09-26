<div align="center">
  <img src="banner.png" alt="Evil Cassandra Banner" width="100%">

  # 👁️‍🗨️ Evil Cassandra V2.1 b
  
  [🇺🇸 English](README.md) | [🇧🇷 Português](README.pt-br.md) | [🇨🇳 中文](README.zh-cn.md)

  <br>

  <img src="https://img.shields.io/badge/Status-Active-red.svg" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-success.svg" alt="OS">
  <img src="https://img.shields.io/badge/Customizable-100%25-orange.svg" alt="Customizable">

  <br><br>
  
  ⚠️ **唯一官方仓库** ⚠️
  
  *由 **Mörlsara** 创建和编写*
</div>

### 🛡️ 账号安全

Cassandra 现在对 DeepSeek Web 会话采用故障即停止的安全策略：

- 默认请求之间至少间隔 3 秒，可通过 "DEEPSEEK_MIN_REQUEST_INTERVAL" 配置。
- 收到 HTTP 401、403 或 429 后，**不会自动重试**。
- 检测到 CAPTCHA、WAF、人机验证、限流或账号保护信号后，会触发本地安全断路器并停止后续请求。
- 默认关闭自动 headless 会话刷新。保存的会话过期后，Cassandra 要求用户手动登录，而不是在后台反复打开 DeepSeek。
- Cassandra 不会解决或绕过 CAPTCHA。
- 这些保护可以减少不必要的自动化和请求突发，但**无法保证 DeepSeek 永远不会暂停账号**。最终的风险判断和账号处置由 DeepSeek 控制。

DeepSeek API 文档明确建议在收到 429 限流时合理控制请求速度，其用户协议也说明违反协议可能导致账号被暂停。 citeturn0search1turn0search21

为了最大限度保护账号，请使用正常的可见浏览器登录流程，不要分享会话文件，也不要让多个 Cassandra 实例同时使用同一个 DeepSeek Web 账号。

---
---

## 📖 什么是 Evil Cassandra 及其用途？

**Evil Cassandra** 是一个高级、高度可定制的基于终端的 AI 代理框架，专为希望拥有定制化、沉浸式和自动化终端助手的用户而设计。它可以与任何对话 API（例如兼容 OpenAI 的端点）无缝交互，主要用于直接从命令行**自动执行任务、进行研究、执行动态工作流以及协助完成复杂的多步骤目标**。

该框架具有引人注目的红色主题界面、结构化的 Markdown 输出以及一种独特且坚定的“Cassandra”人设，将 AI 栩栩如生地呈现出来。无论您使用的是 Linux bash、macOS Zsh 还是 **Windows PowerShell/CMD**，Evil Cassandra 都能提供一致且强大的体验。

### ⚙️ Cassandra 如何工作

从核心来看，Cassandra 是您与所选的大语言模型 (LLM) 之间持续对话的循环：
1. **输入和上下文**：它捕获您的提示，并使用系统级上下文对其进行丰富，维持严格的人设和操作准则。
2. **动态处理**：它安全地连接到您的 LLM API，并将 AI 的想法和响应实时流式传输回您的终端。
3. **执行与模块化**：通过其技能系统，它可以根据 AI 的输出有选择地执行 shell 命令或专门的逻辑。

> ⚠️ **注意：** 此仓库是一个框架。它**不**包含任何硬编码的 API 密钥或模型。您可以根据自己的喜好自由选择和配置您的 API 提供商和模型！

---

## ✨ 核心特性

- 🌐 **DeepSeek Web 集成 (免费)**：无需 API 密钥！Cassandra 可以无缝劫持您的浏览器 DeepSeek 会话，自动提取 token，并在后台静默运行，实现完全免费、无限制的使用。
- 🔴 **沉浸式 Web 和 CLI 界面**：您可以纯粹在终端中运行它，或使用 `--web` 启动时尚的动态 Web UI，其中具有 Markdown 支持、DeepThink (R1) 可展开推理块，以及统一的文件和文件夹附件功能！
- 🎭 **自定义人设和规则 0**：内置且一致的 Cassandra 人设，她在“规则 0”下行动——这是一种系统性绕过 API 审查和安全护栏的核心指令，实现了不受限制的操作自由。
- 📈 **等比数列 (PG) 智能**：Cassandra 被编程为通过**等比数列**的数学视角来分析问题。这种核心框架允许她自动识别乘数、检测指数模式，并以惊人的速度扩展推理。
- 🧩 **Skillogy 系统**：无限扩展她的能力！深受 [BitterSecurity/Decepticon](https://github.com/BitterSecurity/Decepticon) 仓库的启发，您可以通过将外部技能、逻辑和工具放入 `cassandra-skill/` 目录来动态加载它们。Cassandra 会自动提取并即时执行全新的工作流。
- ♾️ **全自动执行循环**：结合 `--allow-shell` 标志，Cassandra 成为一个独立的实体。她读取您的提示，编写 shell 命令，在本地执行，读取输出，并完全依靠自己根据结果进行迭代循环，直到任务完成——无需任何人类指导。
- 💻 **跨平台**：完全兼容 Linux、macOS 和 Windows (PowerShell/CMD)。

---

## 📸 演示

<div align="center">
  <img src="demo.png" alt="Cassandra in Action" width="100%">
  <br>
  <em>Cassandra 自动为 Shodan 生成 LFI 攻击查询。</em>
</div>

---

## 💻 运行模式与教程

Evil Cassandra 提供了多种交互和操作方式。您可以结合使用各种标志来完美匹配您的用例。

### 🌐 Web 界面 (`--web`)
Cassandra 具有一个时尚、红色主题的动态 Web 界面。当您运行 `python deepseek_web.py --web` 时，本地服务器将启动（默认端口 8080）。
- **富文本格式：** 完全支持 Markdown、DeepThink 逻辑（隐藏/可展开的思维）和代码高亮显示。
- **附件（文件和目录）：** 点击 📎 曲别针按钮即可附加单个文件或**整个目录**。内容会自动注入到您的提示中！
- **幽灵模式：** 确保在您关闭会话时不会留下任何痕迹。

### 🛡️ 自主模式与 `--allow-shell` 标志
Cassandra 可以生成并在您的系统上执行终端命令。为了保护您的机器免受意外操作的影响，**默认情况下已禁用 Shell 执行**。

- **默认模式 (安全模式)**：Cassandra 会将建议的命令以文本（Markdown）形式输出。您完全可以手动复制并运行它们。
- **执行模式 (`--allow-shell`)**：Cassandra 获得直接在您的机器上执行其生成的命令的能力。
- **自动循环**：在带有 `--allow-shell` 的 Web 界面中运行时，Cassandra 将成为一个**完全自主的代理**。如果您交给她一个任务，她将生成命令、在本地执行、读取输出，并**自动循环**生成下一个命令以修复错误并推进。她会主动采取行动，直到最终目标完全实现才来打扰您！

### 🧠 DeepSeek 与 Cassandra 交互流

Evil Cassandra 利用强大的交互流进行自主操作，将您的本地机器与 DeepSeek 的智能无缝结合。

1. **大脑 (DeepSeek)**：DeepSeek 充当核心智能引擎。Cassandra 通过无头 Playwright 浏览器连接到它，以安全地拦截数据流，包括内部的 **DeepThink (R1)** 推理日志和最终答案。
2. **身体 (Cassandra)**：Cassandra 充当主动的本地代理。她在您的机器上本地运行，读取 DeepSeek 的输出，在您的终端（或 Web UI）中精美地格式化 Markdown，并主动寻找 shell 代码块来执行。
3. **循环**：当 DeepSeek 建议运行终端命令时，Cassandra 拦截该命令，在您的计算机上本地执行它，捕获终端输出结果，并**自动将结果反馈给 DeepSeek** 作为新的提示。这就创建了一个持续的、自主的执行循环，直到最终目标被彻底达成！

### 🛠️ 安装、DeepSeek 登录与运行

Cassandra 可以直接使用 DeepSeek Web 会话，无需 API Key。

#### 1. 安装依赖

~~~bash
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
~~~

#### 2. 登录 DeepSeek

运行登录辅助程序：

~~~bash
python -m deepseek.auth
~~~

程序会打开一个可见的浏览器窗口。**请手动登录 DeepSeek，并完成 DeepSeek 显示的 CAPTCHA / 人机验证。** Cassandra 只等待已认证会话，不会自动解决或绕过 CAPTCHA。

登录成功后，会话保存在 "session/session.json"，浏览器配置保存在 "session/profile"。这些文件应保持私密，并且会被 Git 忽略。

#### 3. 使用 "--allow-shell" 运行 Cassandra

登录完成后，完整命令：

~~~bash
python deepseek_web.py --allow-shell
~~~

使用 Web UI：

~~~bash
python deepseek_web.py --web --allow-shell
~~~

> "--allow-shell" 会允许 Cassandra 自动执行生成的 shell 命令。请只在可信工作区使用。

#### 4. 如果 CAPTCHA 仍然失败

DeepSeek 可能拒绝自动化浏览器会话，或者显示 CAPTCHA/网络错误。近期也有用户报告在普通浏览器中遇到 DeepSeek CAPTCHA/login 问题，因此这不一定是 Cassandra 本身的 bug。 citeturn4reddit16turn5search8

更可靠的方法是通过 Chrome DevTools Protocol (CDP) 使用普通 Chrome 窗口，然后由用户手动完成 CAPTCHA。

设置：

~~~bash
# Linux/macOS
export DEEPSEEK_CDP_URL=http://127.0.0.1:9222

# PowerShell
$env:DEEPSEEK_CDP_URL="http://127.0.0.1:9222"
~~~

启动一个带 remote debugging 的独立 Chrome 配置，打开 "https://chat.deepseek.com/"，手动登录并完成 CAPTCHA，然后运行：

~~~bash
python -m deepseek.auth
python deepseek_web.py --allow-shell
~~~

CDP 模式直接复用普通浏览器会话，不再尝试伪装 Playwright 浏览器。

> 不要使用 CAPTCHA 破解服务、token bypass 或反机器人规避脚本。如果 DeepSeek 阻止验证，请在可见浏览器中完成验证，或稍后重试。

------

## 🎨 高度可定制和可扩展！

此工具旨在成为您创意的绝对画布。您拥有完全控制权：
- **注入新技能 (Skills)**：您是最终的协调者。您可以不断将新能力、Markdown 指南或逻辑框架直接注入 `cassandra-skill/` 文件夹。Cassandra 会自动提取这些文件，对其进行分析，并无缝执行新的工作流。
  > ⚠️ **警告：** 如果您添加了太多技能，您必须编辑代码以调整字符大小限制，以避免出现问题！
- **本地 AI 与兼容性**：Cassandra 不被绑定到特定提供商。您可以将她的基本 API URL 指向任何与 OpenAI 兼容的端点。这意味着她**完全可以自由地使用本地模型**（如 **Ollama**、**LM Studio**、**MCP (Model Context Protocol)**）或任何其他本地后端进行操作，确保最大程度的隐私并实现零外部审查。
- **自主执行**：结合 `--allow-shell` 标志、她的 PG 智能和规则 0，Cassandra 将成为一个全自动代理，能够在无人指导的情况下解决复杂问题。
  - *示例 1 (渗透/侦察)*：您指示她“映射目标网络，查找暴露的服务，并生成漏洞报告。” 她将编写扫描脚本，执行它们，分析结果，并自动循环运行，直到最终报告准备就绪。
  - *示例 2 (开发)*：您指示她“分析我的本地代码库，发现逻辑错误，并应用修复补丁。” 她将自主读取文件、编写补丁并执行 Git 提交。
- **修改人设**：更改系统提示以完全根据您的需求定制 Cassandra 的行为。

享受与 Evil Cassandra 一起探索终端的乐趣！🖤
