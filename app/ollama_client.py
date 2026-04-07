from __future__ import annotations

import copy
import json
import time
from collections.abc import Mapping, Sequence
from hashlib import sha256
from time import perf_counter
from typing import Any, Protocol

from ollama import Client, RequestError, ResponseError
from pydantic import BaseModel, Field

from app.cache import ExpiringCache
from app.runtime_metrics import RuntimeMetrics
from app.settings import Settings
from app.telemetry import set_span_attributes, start_span


class ToolCallSpec(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class OllamaUsage(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    total_duration_ms: float | None = Field(default=None, ge=0.0)
    load_duration_ms: float | None = Field(default=None, ge=0.0)
    prompt_eval_duration_ms: float | None = Field(default=None, ge=0.0)
    eval_duration_ms: float | None = Field(default=None, ge=0.0)


class ChatTurn(BaseModel):
    content: str = ""
    message: dict[str, Any]
    tool_calls: list[ToolCallSpec] = Field(default_factory=list)
    usage: OllamaUsage | None = None
    model: str | None = None
    cached: bool = False


class LLMGateway(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Any] | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> ChatTurn: ...


class EmbeddingGateway(Protocol):
    def embed(
        self,
        *,
        model: str,
        texts: Sequence[str],
    ) -> list[list[float]]: ...


class OllamaGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        metrics: RuntimeMetrics | None = None,
        client: Client | None = None,
    ):
        self.settings = settings
        self.metrics = metrics
        self._client = client or Client(
            host=settings.ollama_host,
            timeout=settings.ollama_timeout_seconds,
        )
        self._chat_cache = ExpiringCache(
            name="ollama_chat",
            max_entries=settings.ollama_cache_max_entries,
            metrics=metrics,
        )
        self._embed_cache = ExpiringCache(
            name="ollama_embed",
            max_entries=settings.ollama_cache_max_entries,
            metrics=metrics,
        )

    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Any] | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> ChatTurn:
        cache_key = self._cache_key(
            "chat",
            {
                "model": model,
                "messages": list(messages),
                "tools": self._serialize_tools(tools),
                "format": format,
            },
        )
        with start_span(
            "ollama.chat",
            {
                "llm.operation": "chat",
                "llm.model": model,
                "llm.message_count": len(messages),
                "llm.tools_supplied": bool(tools),
            },
        ) as span:
            if self.settings.ollama_cache_enabled:
                cached_turn = self._chat_cache.get(cache_key)
                if cached_turn is not None:
                    cached_turn.cached = True
                    self._record_model_metric(
                        operation="chat",
                        model=model,
                        duration_ms=0.0,
                        usage=None,
                        cache_hit=True,
                        retries=0,
                        success=True,
                    )
                    set_span_attributes(span, {"llm.cache_hit": True})
                    return cached_turn

            retries = 0
            started = perf_counter()
            while True:
                try:
                    response = self._client.chat(
                        model=model,
                        messages=list(messages),
                        tools=list(tools) if tools else None,
                        stream=False,
                        format=format,
                        options={"temperature": 0},
                    )
                    elapsed_ms = (perf_counter() - started) * 1000
                    payload = response.model_dump(exclude_none=True)
                    message = dict(payload.get("message") or response.message.model_dump(exclude_none=True))
                    tool_calls = [
                        ToolCallSpec(
                            name=tool_call.function.name,
                            arguments=dict(tool_call.function.arguments or {}),
                        )
                        for tool_call in (response.message.tool_calls or [])
                    ]
                    usage = self._usage_from_payload(payload)
                    turn = ChatTurn(
                        content=response.message.content or "",
                        message=message,
                        tool_calls=tool_calls,
                        usage=usage,
                        model=model,
                        cached=False,
                    )
                    if self.settings.ollama_cache_enabled:
                        self._chat_cache.set(cache_key, turn, self.settings.ollama_cache_ttl_seconds)
                    self._record_model_metric(
                        operation="chat",
                        model=model,
                        duration_ms=elapsed_ms,
                        usage=usage,
                        cache_hit=False,
                        retries=retries,
                        success=True,
                    )
                    set_span_attributes(
                        span,
                        {
                            "llm.cache_hit": False,
                            "llm.retries": retries,
                            "llm.duration_ms": round(elapsed_ms, 3),
                            "llm.total_tokens": usage.total_tokens if usage is not None else None,
                        },
                    )
                    return turn
                except (RequestError, ResponseError) as exc:
                    if self._should_retry(exc, retries):
                        retries += 1
                        set_span_attributes(span, {"llm.retries": retries})
                        time.sleep(self._retry_delay_seconds(retries))
                        continue

                    self._record_model_metric(
                        operation="chat",
                        model=model,
                        duration_ms=(perf_counter() - started) * 1000,
                        usage=None,
                        cache_hit=False,
                        retries=retries,
                        success=False,
                    )
                    raise
                except ConnectionError as exc:
                    wrapped = RequestError(str(exc))
                    if self._should_retry(wrapped, retries):
                        retries += 1
                        set_span_attributes(span, {"llm.retries": retries})
                        time.sleep(self._retry_delay_seconds(retries))
                        continue

                    self._record_model_metric(
                        operation="chat",
                        model=model,
                        duration_ms=(perf_counter() - started) * 1000,
                        usage=None,
                        cache_hit=False,
                        retries=retries,
                        success=False,
                    )
                    raise wrapped from exc

    def embed(
        self,
        *,
        model: str,
        texts: Sequence[str],
    ) -> list[list[float]]:
        cache_key = self._cache_key(
            "embed",
            {
                "model": model,
                "texts": list(texts),
            },
        )
        with start_span(
            "ollama.embed",
            {
                "llm.operation": "embed",
                "llm.model": model,
                "llm.batch_size": len(texts),
            },
        ) as span:
            if self.settings.ollama_cache_enabled:
                cached_vectors = self._embed_cache.get(cache_key)
                if cached_vectors is not None:
                    self._record_model_metric(
                        operation="embed",
                        model=model,
                        duration_ms=0.0,
                        usage=None,
                        cache_hit=True,
                        retries=0,
                        success=True,
                    )
                    set_span_attributes(span, {"llm.cache_hit": True})
                    return [list(vector) for vector in cached_vectors]

            retries = 0
            started = perf_counter()
            while True:
                try:
                    response = self._client.embed(
                        model=model,
                        input=list(texts),
                        truncate=True,
                    )
                    elapsed_ms = (perf_counter() - started) * 1000
                    payload = response.model_dump(exclude_none=True)
                    vectors = [list(vector) for vector in response.embeddings]
                    if self.settings.ollama_cache_enabled:
                        self._embed_cache.set(cache_key, vectors, self.settings.ollama_cache_ttl_seconds)
                    usage = self._usage_from_payload(payload)
                    self._record_model_metric(
                        operation="embed",
                        model=model,
                        duration_ms=elapsed_ms,
                        usage=usage,
                        cache_hit=False,
                        retries=retries,
                        success=True,
                    )
                    set_span_attributes(
                        span,
                        {
                            "llm.cache_hit": False,
                            "llm.retries": retries,
                            "llm.duration_ms": round(elapsed_ms, 3),
                            "llm.total_tokens": usage.total_tokens if usage is not None else None,
                        },
                    )
                    return vectors
                except (RequestError, ResponseError) as exc:
                    if self._should_retry(exc, retries):
                        retries += 1
                        set_span_attributes(span, {"llm.retries": retries})
                        time.sleep(self._retry_delay_seconds(retries))
                        continue

                    self._record_model_metric(
                        operation="embed",
                        model=model,
                        duration_ms=(perf_counter() - started) * 1000,
                        usage=None,
                        cache_hit=False,
                        retries=retries,
                        success=False,
                    )
                    raise
                except ConnectionError as exc:
                    wrapped = RequestError(str(exc))
                    if self._should_retry(wrapped, retries):
                        retries += 1
                        set_span_attributes(span, {"llm.retries": retries})
                        time.sleep(self._retry_delay_seconds(retries))
                        continue

                    self._record_model_metric(
                        operation="embed",
                        model=model,
                        duration_ms=(perf_counter() - started) * 1000,
                        usage=None,
                        cache_hit=False,
                        retries=retries,
                        success=False,
                    )
                    raise wrapped from exc

    def _record_model_metric(
        self,
        *,
        operation: str,
        model: str,
        duration_ms: float,
        usage: OllamaUsage | None,
        cache_hit: bool,
        retries: int,
        success: bool,
    ) -> None:
        if self.metrics is None:
            return

        total_tokens = usage.total_tokens if usage is not None else None
        estimated_cost_usd = self._estimated_cost_usd(model=model, total_tokens=total_tokens, operation=operation)
        self.metrics.record_model_call(
            operation=operation,
            model=model,
            duration_ms=duration_ms,
            prompt_tokens=usage.prompt_tokens if usage is not None else None,
            completion_tokens=usage.completion_tokens if usage is not None else None,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            cache_hit=cache_hit,
            retries=retries,
            success=success,
        )

    def _estimated_cost_usd(self, *, model: str, total_tokens: int | None, operation: str) -> float:
        if total_tokens is None:
            return 0.0

        if operation == "embed":
            rate = self.settings.embedding_model_cost_per_1k_tokens
        elif model == self.settings.analyze_model:
            rate = self.settings.analyze_model_cost_per_1k_tokens
        elif model == self.settings.investigate_model:
            rate = self.settings.investigate_model_cost_per_1k_tokens
        else:
            rate = 0.0
        return (total_tokens / 1000) * rate

    def _should_retry(self, exc: Exception, retries_used: int) -> bool:
        if retries_used >= self.settings.ollama_max_retries:
            return False
        if isinstance(exc, RequestError):
            return True
        if isinstance(exc, ResponseError):
            status_code = getattr(exc, "status_code", None)
            if status_code is None:
                return True
            return int(status_code) >= 500 or int(status_code) == 429
        return False

    def _retry_delay_seconds(self, retry_number: int) -> float:
        return self.settings.ollama_retry_backoff_seconds * (2 ** max(0, retry_number - 1))

    def _cache_key(self, namespace: str, payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=self._json_default,
        )
        return f"{namespace}:{sha256(serialized.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if callable(value):
            return getattr(value, "__name__", repr(value))
        return repr(value)

    @staticmethod
    def _serialize_tools(tools: Sequence[Any] | None) -> list[Any] | None:
        if tools is None:
            return None
        serialized: list[Any] = []
        for tool in tools:
            if callable(tool):
                serialized.append(getattr(tool, "__name__", repr(tool)))
            else:
                serialized.append(tool)
        return serialized

    @staticmethod
    def _usage_from_payload(payload: dict[str, Any]) -> OllamaUsage | None:
        prompt_tokens = OllamaGateway._optional_int(payload.get("prompt_eval_count"))
        completion_tokens = OllamaGateway._optional_int(payload.get("eval_count"))
        total_tokens = prompt_tokens + completion_tokens if prompt_tokens is not None and completion_tokens is not None else None
        usage = OllamaUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            total_duration_ms=OllamaGateway._duration_ms(payload.get("total_duration")),
            load_duration_ms=OllamaGateway._duration_ms(payload.get("load_duration")),
            prompt_eval_duration_ms=OllamaGateway._duration_ms(payload.get("prompt_eval_duration")),
            eval_duration_ms=OllamaGateway._duration_ms(payload.get("eval_duration")),
        )
        if all(value is None for value in usage.model_dump().values()):
            return None
        return usage

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None

    @staticmethod
    def _duration_ms(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return round(value / 1_000_000, 3)
        if isinstance(value, float):
            return round(value, 3)
        return None
