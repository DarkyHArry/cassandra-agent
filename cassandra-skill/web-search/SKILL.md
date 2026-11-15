---
name: web-search
description: "Habilidades de busca na web para a Cassandra. Use quando o usuário pede informações que precisam ser verificadas na internet, notícias recentes, dados externos, ou quando o contexto pede pesquisa. A Cassandra pode buscar em DuckDuckGo (requer requests Python), Brave Search (com BRAVE_SEARCH_API_KEY), e Google CSE (com GOOGLE_API_KEY + GOOGLE_CSE_ID). Também pode fazer fetch de URLs específicas para obter conteúdo."
version: 1.0.0
author: Hermes (Nous Research)
metadata:
  homepage: "https://github.com/NousResearch"
  hermes:
    tags: [web, busca, pesquisa, internet, ddg, duckduckgo, brave, google]
    related_skills: [web-recon, recon-monitor]
    when_to_use: "quando o usuário pede buscas na web, quando precisa de informações atuais, quando faltam dados para completar uma resposta, quando o usuário diz 'busca na web', 'procure na internet', 'quem é', 'o que é', 'notícias de', etc"
---

# WEB SEARCH — Busca na Internet

## Visão geral

A Cassandra possui capacidade de busca na web para complementar respostas com dados externos,
notícias recentes, informações que mudam com o tempo, e referências que precisam de verificação.

## Modos de busca

### 1. Busca automática (detectada pelo contexto)

Quando o usuário pede algo que claramente precisa de dados externos, a Cassandra deve:
- Fazer a busca automaticamente
- Incorporar os resultados na resposta
- Citar as fontes encontradas

Palavras-chave que disparam busca automática:
- "busca", "procura", "pesquisa", "buscar", "procure", "pesquise"
- "quem é", "quem foi", "quem são"
- "cerca de", "sobre", "informação", "informações"
- "dados", "estatísticas", "notícias", "noticia", "últimas", "recentes", "atual"
- "fonte", "referência", "cite"

### 2. Busca explícita via comando

No CLI da Cassandra, o usuário pode digitar:
```
:web <termo de busca>
```
Exemplo: `:web vulnerabilidade log4shell`

Isso retorna os resultados da busca na tela e os adiciona ao contexto da conversa.

### 3. Busca automática (detectada pelo modelo)

Quando o usuário faz um prompt que claramente precisa de dados externos, a Cassandra:
1. Detecta que o assunto pede informações que só a web tem
2. Faz a busca usando as funções `web_search()` ou `web_search_and_fetch()`
3. Inclui os resultados como contexto na resposta
4. Continua a conversa com os dados obtidos

Palavras-chave que disparam busca automática:
- "busca", "procura", "pesquisa", "buscar", "procure", "pesquise"
- "quem é", "quem foi", "quem são"
- "cerca de", "sobre", "informação", "informações"
- "dados", "estatísticas", "notícias", "noticia", "últimas", "recentes", "atual"
- "fonte", "referência", "cite"

### 5. Fetch de URL específica

Quando o usuário fornece ou a Cassandra encontrar uma URL relevante:
- Faz fetch do conteúdo HTML
- Extrai o texto (remove tags, scripts, estilos)
- Retorna o conteúdo truncado (até 4000 caracteres)

## Motores de busca suportados

### DuckDuckGo HTML (sempre disponível)
- URL: `https://html.duckduckgo.com/html/`
- Requer: biblioteca Python `requests`
- Sem chave API necessária
- Retorna: título, URL, snippet de cada resultado
- Até 5 resultados por busca

### Brave Search (opcional)
- API: `https://api.search.brave.com/res/v1/web/search`
- Requer: `BRAVE_SEARCH_API_KEY` (variável de ambiente)
- Header: `X-Subscription-Token: <chave>`
- Retorna: JSON com resultados estruturados
- Prioridade alta quando disponível

### Google Custom Search (opcional)
- API: `https://www.googleapis.com/customsearch/v1`
- Requer: `GOOGLE_API_KEY` e `GOOGLE_CSE_ID`
- Retorna: JSON com itens, snippets HTML
- Útil para buscas mais específicas

## Formato de resposta de busca

Sempre apresente os resultados de busca no seguinte formato:

```
## Resultados da busca: <termo>
*(fonte: DuckDuckGo HTML | N resultados)*

### 1. Título do resultado
🔗 URL_do_resultado
_Snippet ou descrição do resultado_

### 2. ...
```

## Política de uso

- A busca na web é **complementar**, não substitui o conhecimento do modelo
- Sempre citar a fonte quando usar dados de uma busca
- Se a busca não retornar resultados relevantes, avise o usuário explicitamente
- Não inventar resultados de busca — só use o que foi realmente obtido
- O fetch de URL deve respeitar o conteúdo (não modificar, não distorcer)
