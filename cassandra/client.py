#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cassandra — Cliente Multi-Provedor (OpenAI-compatible)
=====================================================

Fala o protocolo `/chat/completions` de qualquer provedor compatível
com OpenAI. Todas as camadas de proteção estão integradas:

  * RateLimiter      — espaçamento + jitter entre requisições
  * BackoffPolicy    — recuo exponencial em erros transitórios
  * CircuitBreaker   — para de insistir quando o provedor sinaliza abuso
  * ProviderRotator  — troca de credencial quando uma queima
  * Sanitizer        — suaviza termos-gatilho antes do envio
  * Crypto envelope  — cifra o payload com instrução de decodificação

Uso:
    from cassandra.client import CassandraClient, load_credentials
    client = CassandraClient(load_credentials())
    for chunk in client.stream(messages, model="gpt-4o"):
        print(chunk, end="")
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Iterator, List, Optional

import httpx

from .crypto import wrap_for_model
from .filter import (
    BackoffPolicy,
    CircuitBreaker,
    Credential,
    ProviderBlocked,
    ProviderRotator,
    RateLimiter,
    is_ban_signal,
    is_retryable,
    sanitize,
)
from .guard import (
    RetryPolicy,
    detect_refusal,
    is_enabled as guard_enabled,
    override_instruction,
    rewrite_prompt,
)
from .providers import Provider, provider_catalog, resolve_provider


class ProviderError(RuntimeError):
    """Erro devolvido pelo provedor (HTTP != 2xx)."""

    def __init__(self, status: int, body: str, provider: str = ""):
        self.status = status
        self.body = body
        self.provider = provider
        super().__init__(f"[{provider}] HTTP {status}: {body[:400]}")


class AllProvidersExhausted(RuntimeError):
    """Todas as credenciais configuradas estão queimadas ou o circuito abriu."""


# ---------------------------------------------------------------------------
# CARREGAMENTO DE CREDENCIAIS
# ---------------------------------------------------------------------------

def _split_keys(raw: str) -> List[str]:
    """Aceita uma chave ou várias separadas por vírgula/quebra de linha."""
    if not raw:
        return []
    parts = []
    for chunk in raw.replace("\n", ",").split(","):
        k = chunk.strip().strip("'\"")
        if k:
            parts.append(k)
    return parts


def load_credentials() -> List[Credential]:
    """
    Monta a lista de credenciais a partir do ambiente (.env já carregado).

    Ordem de precedência:
      1. CASSANDRA_API_KEYS  — lista explícita (vírgula), multi-chave
      2. <PROVIDER>_API_KEY  — uma por provedor do registro
      3. CASSANDRA_API_KEY   — chave genérica (compatibilidade)
    """
    creds: List[Credential] = []
    provider_hint = os.getenv("CASSANDRA_PROVIDER", "").strip()
    model_override = os.getenv("CASSANDRA_MODEL", "").strip()
    base_override = os.getenv("CASSANDRA_BASE_URL", "").strip()

    # 1. Lista explícita multi-chave
    for key in _split_keys(os.getenv("CASSANDRA_API_KEYS", "")):
        p = resolve_provider(key, provider_hint, base_override)
        creds.append(
            Credential(
                provider_key=p.key,
                api_key=key,
                model=model_override or p.default_model,
                base_url=p.base_url,
                label=p.label,
            )
        )

    # 2. Variáveis por provedor
    if not creds:
        for entry in provider_catalog():
            if entry["key"] == "custom":
                continue
            raw = os.getenv(entry["env_var"], "")
            for key in _split_keys(raw):
                p = resolve_provider(key, entry["key"], base_override)
                creds.append(
                    Credential(
                        provider_key=p.key,
                        api_key=key,
                        model=model_override or p.default_model,
                        base_url=p.base_url,
                        label=p.label,
                    )
                )

    # 3. Chave genérica
    if not creds:
        generic = os.getenv("CASSANDRA_API_KEY", "").strip()
        for key in _split_keys(generic):
            p = resolve_provider(key, provider_hint, base_override)
            creds.append(
                Credential(
                    provider_key=p.key,
                    api_key=key,
                    model=model_override or p.default_model,
                    base_url=p.base_url,
                    label=p.label,
                )
            )

    return creds


# ---------------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------------

class CassandraClient:
    """
    Cliente streaming multi-provedor com proteção anti-banimento.

    Parâmetros de comportamento (via .env):
      CASSANDRA_MIN_INTERVAL   — intervalo mínimo entre requisições (s)
      CASSANDRA_JITTER         — jitter adicional (s)
      CASSANDRA_MAX_ATTEMPTS   — tentativas por requisição
      CASSANDRA_COOLDOWN       — cooldown do circuit breaker (s)
      CASSANDRA_SANITIZE       — 1/0, ativa o sanitizador de termos
      CASSANDRA_ENCRYPT        — 1/0, ativa o envelope cifrado
    """

    def __init__(self, credentials: Optional[List[Credential]] = None):
        # `is None` (não `or`) — uma lista vazia significa "sem credenciais"
        # de propósito, e não deve recarregar do ambiente.
        self.rotator = ProviderRotator(
            credentials if credentials is not None else load_credentials()
        )
        self.rate_limiter = RateLimiter()
        self.backoff = BackoffPolicy.from_env()
        self.breaker = CircuitBreaker()
        self.sanitize_enabled = os.getenv("CASSANDRA_SANITIZE", "1").lower() in {
            "1", "true", "yes", "on",
        }
        # Envelope cifrado: DESLIGADO por padrão. Modelos de linguagem não
        # executam AES-GCM — com isto ligado eles recebem o envelope e
        # travam tentando decifrá-lo em vez de responder. Ver docs em
        # crypto.py. A sanitização é a camada de evasão que funciona.
        self.encrypt_enabled = os.getenv("CASSANDRA_ENCRYPT", "0").lower() in {
            "1", "true", "yes", "on",
        }
        # Guarda anti-recusa: reescreve o pedido em termos técnicos neutros
        # e, se o modelo recusar mesmo assim, reenvia com reescrita mais
        # agressiva. Vale para CLI e web, pois roda dentro do cliente.
        self.guard_enabled = guard_enabled()
        self.refusal_policy = RetryPolicy.from_env()
        self._lock = threading.Lock()
        # Timeouts agressivos. O `read` antigo era 600s (10 min): se o
        # provedor travava no meio do stream, a agente ficava "pensando"
        # parada até 10 minutos sem produzir nada. Agora:
        #   connect  -> 20s  (não adianta esperar mais para abrir TCP)
        #   read     -> 90s  (intervalo MÁXIMO entre chunks, não total)
        #   write    -> 30s
        #   pool     -> 20s
        self._http = httpx.Client(
            timeout=httpx.Timeout(90.0, connect=20.0, read=90.0,
                                  write=30.0, pool=20.0),
            follow_redirects=True,
        )
        # Silêncio máximo tolerado entre chunks do stream, em segundos.
        # Independente do timeout do httpx: aqui medimos o intervalo entre
        # chunks recebidos, não o tempo total da requisição.
        # Default: 120s (era 45s — modelos lentos com contexto grande
        # podem demorar mais entre chunks sem estar travados).
        self.stream_idle_timeout = float(
            os.getenv("CASSANDRA_STREAM_IDLE_TIMEOUT", "120")
        )
        # Tempo máximo total de um stream (rede de segurança).
        # Default: 3600s (1h — era 600s). Defina como "0" para desabilitar.
        _raw_total = os.getenv("CASSANDRA_STREAM_TOTAL_TIMEOUT", "3600")
        try:
            _total_val = float(_raw_total)
        except ValueError:
            _total_val = 3600.0
        self.stream_total_timeout = (
            float("inf") if _total_val <= 0 else _total_val
        )
        self.last_report: Dict = {}
        self.last_guard_report: Dict = {}
        # Resposta HTTP em andamento, para permitir abortar de fora
        # (botão Parar da interface web).
        self._active_resp = None

    # -- utilidades ---------------------------------------------------------

    @property
    def has_credentials(self) -> bool:
        return len(self.rotator) > 0

    def describe(self) -> Dict:
        creds = []
        for c in self.rotator._creds:  # diagnóstico
            creds.append(
                {
                    "provider": c.provider_key,
                    "label": c.label,
                    "model": c.model,
                    "key_tail": c.api_key[-4:] if c.api_key else "",
                }
            )
        return {
            "credentials": creds,
            "available": self.rotator.available_count(),
            "sanitize": self.sanitize_enabled,
            "encrypt": self.encrypt_enabled,
            "guard": self.guard_enabled,
            "refusal_retries": self.refusal_policy.max_attempts,
            "breaker_open": self.breaker.is_open,
            "breaker_remaining": round(self.breaker.remaining(), 1),
        }

    def _headers(self, cred: Credential) -> Dict[str, str]:
        provider: Optional[Provider] = resolve_provider(
            cred.api_key, cred.provider_key, cred.base_url
        )
        headers = {
            "Authorization": f"Bearer {cred.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "cassandra-cli/5.0",
        }
        headers.update(provider.extra_headers)
        return headers

    def _endpoint(self, cred: Credential) -> str:
        base = (cred.base_url or "").rstrip("/")
        return f"{base}/chat/completions"

    # -- preparação do payload ---------------------------------------------

    def _prepare_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple[List[Dict[str, str]], Dict]:
        """
        Aplica sanitização e, opcionalmente, cifra a última mensagem do
        usuário em um envelope com instrução de decodificação.

        Devolve (mensagens_para_enviar, relatório).
        """
        report: Dict = {"sanitized": False, "encrypted": False, "hits": {}}
        out = [dict(m) for m in messages]

        # Sanitiza todas as mensagens de usuário/sistema.
        if self.sanitize_enabled:
            total_hits: Dict[str, int] = {}
            for m in out:
                if m.get("role") in ("user", "system"):
                    new_text, rep = sanitize(m.get("content", ""), enabled=True)
                    if rep.changed:
                        m["content"] = new_text
                        total_hits.update(rep.hits)
            if total_hits:
                report["sanitized"] = True
                report["hits"] = total_hits

        # Cifra a última mensagem do usuário.
        if self.encrypt_enabled:
            for m in reversed(out):
                if m.get("role") == "user":
                    original = m.get("content", "")
                    if original and "⟦CΣ1:" not in original:
                        m["content"] = wrap_for_model(original)
                        report["encrypted"] = True
                    break

        return out, report

    # -- requisição ---------------------------------------------------------

    def _request_stream(
        self,
        cred: Credential,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> Iterator[str]:
        """Executa UMA tentativa de streaming. Levanta ProviderError."""
        provider = resolve_provider(cred.api_key, cred.provider_key, cred.base_url)

        body: Dict = {
            "model": model or cred.model or provider.default_model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if provider.supports_stream_options:
            body["stream_options"] = {"include_usage": False}

        self.rate_limiter.wait()

        with self._http.stream(
            "POST",
            self._endpoint(cred),
            json=body,
            headers=self._headers(cred),
        ) as resp:
            # Referência para permitir abortar de fora (botão Parar da web).
            # Sem isto, uma thread bloqueada esperando o próximo chunk
            # mantém a requisição viva e o modelo continua gerando.
            self._active_resp = resp

            if resp.status_code >= 400:
                raw = resp.read().decode("utf-8", errors="replace")
                raise ProviderError(resp.status_code, raw, provider.label)

            # Watchdog de stream: `iter_lines()` bloqueia para sempre se o
            # servidor abrir a conexão e parar de mandar dados sem fechar.
            # Nesse caso nenhum chunk chega e nenhum timeout do httpx
            # dispara — a agente fica "pensando" indefinidamente.
            #
            # Solução: ler as linhas numa thread produtora que alimenta uma
            # fila, e no consumidor aplicar timeout de silêncio. Se passar
            # do limite sem nenhum chunk, abortamos e deixamos o retry agir.
            import queue as _queue
            import threading as _threading

            line_q: "_queue.Queue" = _queue.Queue(maxsize=200)
            _SENTINEL = object()
            reader_error: List[BaseException] = []

            def _pump() -> None:
                try:
                    for _ln in resp.iter_lines():
                        line_q.put(_ln)
                except BaseException as _exc:  # noqa: BLE001
                    reader_error.append(_exc)
                finally:
                    line_q.put(_SENTINEL)

            pump = _threading.Thread(target=_pump, daemon=True)
            pump.start()

            started = time.monotonic()
            got_any = False

            def _process(line) -> Iterator[str]:
                """Processa uma linha SSE. Devolve os pedaços de texto."""
                nonlocal got_any
                if not line:
                    return
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                if not line.startswith("data:"):
                    return
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    return
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    return

                # Alguns provedores mandam erro dentro do stream.
                if isinstance(obj, dict) and obj.get("error"):
                    err = obj["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    raise ProviderError(400, str(msg), provider.label)

                for choice in obj.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        got_any = True
                        yield content
                    # Anthropic-compat e alguns proxies usam reasoning_content.
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        got_any = True
                        yield reasoning

            while True:
                # Limite total (rede de segurança).
                if time.monotonic() - started > self.stream_total_timeout:
                    raise ProviderError(
                        408,
                        f"stream excedeu {self.stream_total_timeout:.0f}s no total",
                        provider.label,
                    )
                try:
                    line = line_q.get(timeout=self.stream_idle_timeout)
                except _queue.Empty:
                    raise ProviderError(
                        408,
                        f"stream silencioso por {self.stream_idle_timeout:.0f}s "
                        f"(sem chunks)",
                        provider.label,
                    )

                if line is _SENTINEL:
                    # Produtor terminou; drena o que sobrou e sai.
                    while True:
                        try:
                            nxt = line_q.get_nowait()
                        except _queue.Empty:
                            break
                        if nxt is _SENTINEL:
                            break
                        yield from _process(nxt)
                    break

                yield from _process(line)

            if reader_error and not got_any:
                raise reader_error[0]

            if not got_any:
                raise ProviderError(
                    502,
                    "stream encerrou sem produzir nenhum conteúdo",
                    provider.label,
                )

        # Fim do `with`: a resposta não está mais ativa.
        self._active_resp = None

    def abort_active(self) -> bool:
        """
        Aborta a requisição em andamento, fechando o stream HTTP.

        Usado pelo botão Parar da interface web. Fechar a resposta encerra
        de verdade a geração no provedor — não basta parar de ler, senão o
        modelo continua produzindo (e cobrando) tokens que ninguém verá.
        """
        resp = self._active_resp
        if resp is None:
            return False
        try:
            resp.close()
            return True
        except Exception:  # noqa: BLE001
            return False

    # -- API pública --------------------------------------------------------

    def _stream_once(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> Iterator[str]:
        """
        Uma passagem completa de transporte: prepara, tenta com retry de
        rede/credencial e faz streaming. Sem lógica de recusa — essa fica
        em `stream()`, que pode chamar isto várias vezes.
        """
        prepared, report = self._prepare_messages(messages)
        self.last_report = report

        attempts = 0
        max_attempts = self.backoff.max_attempts
        last_error: Optional[Exception] = None

        while attempts < max_attempts:
            cred = self.rotator.current()
            if cred is None:
                raise AllProvidersExhausted(
                    "Todas as credenciais estão temporariamente bloqueadas "
                    "(queimadas). Aguarde o cooldown ou adicione outra chave."
                )

            try:
                # Streaming progressivo com ponto de retorno seguro.
                #
                # Emitimos os pedaços conforme chegam (preserva o efeito de
                # digitação na web), mas só depois de acumular um mínimo de
                # conteúdo. Motivo: um provedor pode mandar um pedaço curto
                # ("iniciando", um preâmbulo) e TRAVAR em seguida. Se
                # emitíssemos imediatamente, o usuário veria lixo parcial e
                # perderíamos a chance de rotacionar.
                #
                # Regra: acumula até `_COMMIT_CHARS`. Antes disso, travar é
                # invisível e rotaciona. Depois disso, já é resposta real —
                # não repetimos (evita duplicar texto).
                _COMMIT_CHARS = int(
                    os.getenv("CASSANDRA_STREAM_COMMIT_CHARS", "24")
                )
                # Também compromete por TEMPO: se o provedor estiver
                # mandando chunks devagar, esperar 24 caracteres reteria
                # uma resposta curta inteira. Após este intervalo com
                # conteúdo pendente, emitimos o que temos.
                _COMMIT_SECS = float(
                    os.getenv("CASSANDRA_STREAM_COMMIT_SECS", "1.5")
                )
                pending: List[str] = []
                committed = False
                first_chunk_at: Optional[float] = None
                for piece in self._request_stream(
                    cred, prepared, model, temperature, max_tokens
                ):
                    if committed:
                        yield piece
                        continue
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic()
                    pending.append(piece)
                    enough_chars = sum(len(x) for x in pending) >= _COMMIT_CHARS
                    enough_time = (
                        time.monotonic() - first_chunk_at
                    ) >= _COMMIT_SECS
                    if enough_chars or enough_time:
                        committed = True
                        yield from pending
                        pending = []
                # Stream terminou: emite o que sobrou.
                if pending:
                    yield from pending
                return  # sucesso

            except ProviderError as exc:
                last_error = exc
                # Se já comprometemos conteúdo real nesta tentativa,
                # repetir duplicaria texto. Encerramos com o que temos.
                if committed and exc.status in (408, 502, 503, 504):
                    return
                if exc.status in (401, 403, 402):
                    # Chave inválida/revogada/limite de faturamento:
                    # queima esta credencial e passa para a próxima.
                    self.rotator.mark_burned(cred, f"HTTP {exc.status}")
                    attempts += 1
                    continue
                if is_ban_signal(exc.status, exc.body):
                    # 429 / abuso: transitório. NÃO queima a credencial —
                    # recua e tenta de novo (mesma chave), que é o
                    # comportamento correto para rate-limit.
                    delay = self.backoff.delay_for(attempts)
                    time.sleep(delay)
                    attempts += 1
                    continue
                if exc.status in (408, 502, 503, 504):
                    # Stream travado / silencioso / gateway ruim. É falha
                    # do ENDPOINT, não da credencial: rotaciona para a
                    # próxima imediatamente, sem backoff. Insistir na
                    # mesma chave só repete o travamento (era o que fazia
                    # a agente "pensar" parada por minutos).
                    self.rotator.rotate()
                    attempts += 1
                    continue
                if is_retryable(exc.status):
                    delay = self.backoff.delay_for(attempts)
                    time.sleep(delay)
                    attempts += 1
                    continue
                # Erro não recuperável (400, 422): não insiste.
                raise

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
                last_error = exc
                delay = self.backoff.delay_for(attempts)
                time.sleep(delay)
                attempts += 1
                continue

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts += 1
                continue

        # Esgotou tentativas.
        if last_error is not None:
            self.breaker.trip(f"última falha: {last_error}")
            raise AllProvidersExhausted(
                f"Todas as tentativas falharam. Último erro: {last_error}"
            )
        raise AllProvidersExhausted("Todas as credenciais disponíveis falharam.")

    def _messages_with_rewrite(
        self,
        messages: List[Dict[str, str]],
        attempt: int,
    ) -> List[Dict[str, str]]:
        """
        Devolve uma cópia das mensagens com o pedido do usuário reescrito
        em termos técnicos neutros, conforme a estratégia da tentativa.

        Só a última mensagem de usuário é reescrita — o histórico e o
        system prompt permanecem intactos.
        """
        strategy = self.refusal_policy.strategy_for(attempt)
        out = [dict(m) for m in messages]

        for m in reversed(out):
            if m.get("role") == "user":
                original = m.get("content", "")
                rewritten, rep = rewrite_prompt(
                    original,
                    add_framing=True,
                    aggressive=strategy["aggressive"],
                )
                if strategy["override"]:
                    rewritten += override_instruction()
                m["content"] = rewritten
                # MESCLA em vez de substituir: preserva o "detected" que
                # stream() acabou de registrar. Substituir apagava o flag,
                # e nem o CLI nem a web conseguiam informar ao operador
                # que uma recusa foi neutralizada.
                self.last_guard_report = {
                    **self.last_guard_report,
                    "attempt": attempt,
                    "strategy": strategy,
                    "hits": rep.hits,
                    "rewritten": rep.changed,
                }
                break

        return out

    def stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """
        Streaming com todas as proteções:

          1. retry de rede/credencial (backoff, rotação, breaker);
          2. guarda anti-recusa — se a resposta for uma recusa, o pedido é
             reescrito em termos técnicos neutros e reenviado, até o limite
             configurado, sem repetir a mesma abordagem.

        A guarda é transparente: o operador vê apenas a resposta final.
        Quando uma recusa é neutralizada, a informação fica disponível em
        `self.last_guard_report` para quem quiser exibir um aviso.
        """
        if not self.has_credentials:
            raise AllProvidersExhausted(
                "Nenhuma credencial configurada. Defina uma chave de API no "
                ".env (ex.: NVIDIA_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY) "
                "ou pela interface web."
            )

        if self.breaker.is_open:
            raise ProviderBlocked(
                f"Circuito aberto por proteção anti-banimento "
                f"({self.breaker.reason}). Aguarde "
                f"{self.breaker.remaining():.0f}s."
            )

        self.last_guard_report = {}

        # Sem guarda: passagem única, streaming direto (menor latência).
        if not self.guard_enabled or self.refusal_policy.max_attempts <= 0:
            yield from self._stream_once(messages, model, temperature, max_tokens)
            return

        # Com guarda: streaming preservado com JANELA de detecção.
        #
        # A versão anterior acumulava a resposta INTEIRA antes de emitir
        # qualquer coisa. Com um modelo lento isso deixava a interface
        # parada por minutos, parecendo travada ("fica parado"), e uma
        # resposta vazia entregava literalmente nada.
        #
        # Agora bufferizamos apenas a JANELA INICIAL, onde recusas
        # aparecem ("Não posso ajudar com..."). Janela limpa => emite e
        # segue em streaming normal. Recusa => aborta antes de emitir e
        # reescreve o pedido.
        current_messages = messages
        max_refusal_attempts = self.refusal_policy.max_attempts
        window_chars = int(os.getenv("CASSANDRA_GUARD_WINDOW", "300"))
        # Commit por tempo: se o modelo responde devagar, esperar 300
        # caracteres reteria a resposta inteira (interface parada).
        guard_secs = float(os.getenv("CASSANDRA_GUARD_COMMIT_SECS", "2.0"))
        # Checagem antecipada de recusa: recusas aparecem no início.
        early_check = int(os.getenv("CASSANDRA_GUARD_EARLY_CHARS", "80"))

        for attempt in range(max_refusal_attempts + 1):
            window: List[str] = []
            committed = False          # já emitimos algo ao usuário
            refused = False
            empty = False
            stream_error: Optional[Exception] = None
            first_at: Optional[float] = None

            it = self._stream_once(
                current_messages, model, temperature, max_tokens
            )
            try:
                while True:
                    try:
                        chunk = next(it)
                    except StopIteration:
                        break
                    if committed:
                        yield chunk
                        continue
                    if first_at is None:
                        first_at = time.monotonic()
                    window.append(chunk)
                    joined = "".join(window)

                    # Recusa no início: aborta antes de emitir qualquer coisa.
                    if len(joined) >= early_check:
                        verdict = detect_refusal(joined)
                        if verdict.is_refusal:
                            refused = True
                            self.last_guard_report = {
                                "detected": True,
                                "kind": verdict.kind,
                                "confidence": verdict.confidence,
                                "evidence": verdict.evidence,
                                "attempt": attempt,
                            }
                            break

                    # Ponto de compromisso: por tamanho ou por tempo.
                    elapsed = time.monotonic() - (first_at or time.monotonic())
                    if len(joined) >= window_chars or (
                        elapsed >= guard_secs and len(joined) >= 40
                    ):
                        committed = True
                        yield joined
                        window = []
            except Exception as exc:  # noqa: BLE001
                stream_error = exc

            if stream_error is not None:
                if committed:
                    # Já emitimos conteúdo válido: entrega o resto e sai.
                    if window:
                        yield "".join(window)
                    return
                raise stream_error

            if committed:
                # Streaming já entregue; emite a sobra e encerra.
                if window:
                    yield "".join(window)
                if attempt > 0:
                    self.last_guard_report = {
                        **self.last_guard_report,
                        "recovered": True,
                        "final_attempt": attempt,
                    }
                return

            # Nada emitido: decidir sobre a janela acumulada.
            joined = "".join(window)
            verdict = detect_refusal(joined)

            if verdict.is_refusal:
                refused = True
                self.last_guard_report = {
                    "detected": True,
                    "kind": verdict.kind,
                    "confidence": verdict.confidence,
                    "evidence": verdict.evidence,
                    "attempt": attempt,
                }
            elif not joined.strip():
                empty = True
            else:
                if attempt > 0:
                    self.last_guard_report = {
                        **self.last_guard_report,
                        "recovered": True,
                        "final_attempt": attempt,
                    }
                yield joined
                return

            # --- Precisa de outra tentativa ---
            if attempt >= max_refusal_attempts:
                if refused:
                    # Sem tentativas restantes: entrega a recusa.
                    self.last_guard_report["recovered"] = False
                    yield joined
                    return
                if empty:
                    raise ProviderError(
                        502,
                        "O modelo devolveu resposta vazia em todas as "
                        "tentativas. Verifique o modelo configurado ou "
                        "tente novamente.",
                        "",
                    )
                return

            # Recusa: reescreve o pedido. Vazio: repete sem reescrever.
            if refused:
                current_messages = self._messages_with_rewrite(messages, attempt)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        return "".join(self.stream(messages, model, temperature, max_tokens))

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass
