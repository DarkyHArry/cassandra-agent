# Modelos NVIDIA NIM verificados — 2026-10-20

Conta: `nvapi-` (endpoint `https://integrate.api.nvidia.com/v1`)
Método: `POST /chat/completions` com `stream: true`, prompt "Diga apenas: OK",
e sondagem de janela de contexto com marcadores únicos (`[M000001-XXXXXXXXXX]`).
O limite real de cada modelo foi extraído do erro HTTP 400 do próprio endpoint
(`"This model's maximum context length is N tokens"`).

## Funcionais (12)

| Modelo | Contexto | Observação |
|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | **1.048.576** | maior janela disponível; modelo padrão |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | **1.000.000** | multimodal (VL) |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | **1.000.000** | reasoning, responde rápido |
| `stepfun-ai/step-5-preview` | **1.000.000** | confirmado até 1.000.000 tok |
| `meta/llama-3.2-11b-vision-instruct` | 131.072 | visão |
| `poolside/laguna-xs-2.1` | 262.144 | código |
| `openai/gpt-oss-20b` | 131.072 | ~18 s por resposta |
| `nvidia/nemotron-3.5-content-safety` | 128.000 | guarda: retorna JSON `User Safety` |
| `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | 128.000 | guarda: retorna JSON `User Safety` |
| `nvidia/ising-calibration-1.5-31b` | 128.000 | nicho (calibração quântica) |
| `nvidia/riva-translate-4b-instruct-v2` | 128.000 | tradução |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 128.000 | responde vazio em teste seco |

## Não disponíveis nesta conta

- **HTTP 404 `Function '...': Not found for account`** — modelo existe no catálogo
  público mas não está provisionado para esta conta:
  `nvidia/nemotron-3-super-120b-a12b`, `nvidia/nemotron-4-340b-instruct`,
  `nvidia/nemotron-4-340b-reward`, `nvidia/llama-3.1-nemotron-ultra-253b-v1`,
  `nvidia/nemotron-nano-3-30b-a3b`, `nvidia/llama-3.1-nemotron-70b-instruct`,
  `nvidia/llama-3.1-nemotron-51b-instruct`, `nvidia/mistral-nemo-minitron-8b-8k-instruct`,
  `nvidia/cosmos-reason2-8b`, `nvidia/llama3-chatqa-1.5-70b`, `nvidia/neva-22b`,
  `nvidia/vila`, `nvidia/riva-translate-4b-instruct`,
  `google/gemma-3-12b-it`, `google/gemma-3-4b-it`, `google/gemma-2b`,
  `google/codegemma-7b`, `google/codegemma-1.1-7b`, `google/recurrentgemma-2b`,
  `google/deplot`, `meta/codellama-70b`, `meta/llama2-70b`,
  `mistralai/mistral-large-2-instruct`, `mistralai/codestral-22b-instruct-v0.1`,
  `mistralai/mixtral-8x22b-v0.1`, `mistralai/mistral-large`,
  `mistralai/mistral-7b-instruct-v0.3`, `nv-mistralai/mistral-nemo-12b-instruct`,
  `writer/palmyra-creative-122b`, `writer/palmyra-fin-70b-32k`,
  `writer/palmyra-med-70b`, `writer/palmyra-med-70b-32k`,
  `ibm/granite-34b-code-instruct`, `ibm/granite-3.0-8b-instruct`,
  `ibm/granite-3.0-3b-a800m-instruct`, `microsoft/phi-3.5-moe-instruct`,
  `microsoft/phi-3-vision-128k-instruct`, `microsoft/kosmos-2`,
  `ai21labs/jamba-1.5-large-instruct`, `zyphra/zamba2-7b-instruct`,
  `01-ai/yi-large`, `databricks/dbrx-instruct`, `adept/fuyu-8b`,
  `aisingapore/sea-lion-7b-instruct`, `deepseek-ai/deepseek-coder-6.7b-instruct`.
  Todos os modelos de embedding (`nvidia/*embed*`, `snowflake/arctic-embed-l`)
  também retornam 404 — o endpoint não os expõe via `/chat/completions`.
- **HTTP 410 Gone (fim de vida)** — `openai/gpt-oss-120b` (EOL 2026-09-03),
  `stepfun-ai/step-3.7-flash` (EOL 2026-08-28).
- **Timeout de leitura (~180 s)** — `deepseek-ai/deepseek-v4.1-flash`,
  `google/gemma-4-31b-it`, `google/diffusiongemma-26b-a4b-it`,
  `meta/llama-3.2-90b-vision-instruct`, `meta/llama-guard-4-12b`,
  `nvidia/llama-3.1-nemoguard-8b-content-safety`, `openai/gpt-oss-20b` (com payload grande).
- **HTTP 400** — `nvidia/nemotron-parse` não aceita `content` como string simples.
- **HTTP 500/503** — `nvidia/ai-synthetic-video-detector`,
  `nvidia/llama-3.1-nemoguard-8b-topic-control`,
  `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (503 transitório: limite de 16 requisições concorrentes por worker).

## Notas operacionais

- **Como medir o limite quando o endpoint não o informa diretamente.** Alguns
  modelos (ex.: `openai/gpt-oss-20b`) respondem o estouro de contexto com um
  erro de `max_tokens` em vez de citar a janela:
  `max_tokens must be at least 1, got -N`. Esse erro é uma equação linear —
  `max_tokens = janela − prompt_tokens` — então bastam 3-4 pontos para derivar
  a janela por regressão. No `gpt-oss-20b`, 7 pontos (55k–112k) fecharam com
  **R² = 0.99999591** (resíduo máx. 139 tokens) e derivaram **131.072**;
  a confirmação empírica (54.000 passa, 55.000 falha) bateu exatamente.
- **Texto repetitivo NÃO serve para medir contexto.** `lorem ipsum` em loop
  comprime e qualquer tamanho "passa" — foi o que fez o `gpt-oss-20b` parecer
  ter 500k de janela quando tem 131k. Use marcadores únicos
  (`[M000001-XXXXXXXXXX]`) ou confie no erro do endpoint.
- O catálogo `GET /v1/models` lista **87 modelos**, mas a maioria não está
  provisionada para a conta. Sempre valide com uma chamada real antes de confiar na lista.
- Vários modelos respondem **vazio** em chamada não-streaming e só funcionam
  com `stream: true` (`stepfun-ai/step-5-preview`, `nvidia/nemotron-3.5-super-vl-120b-a12b`,
  `openai/gpt-oss-20b`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`).
  O cliente da Cassandra usa streaming, então isso é transparente.
- `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `nvidia/nemotron-parse-2.0`,
  `nvidia/llama-3.1-nemoguard-8b-topic-control`, `meta/muse-glimmer-30b`
  retornam HTTP 200 com corpo vazio — não utilizáveis.
- Para descobrir o limite de contexto de um modelo novo, envie um payload
  propositalmente acima de 1M tokens: o HTTP 400 devolve o valor exato.
