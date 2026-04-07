from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Literal

from app.schemas import (
    HealthAppInfo,
    MetricsModelUsage,
    MetricsRequestTotals,
    MetricsResponse,
    MetricsCacheUsage,
    MetricsRouteUsage,
)
from app.settings import Settings

ModelOperation = Literal["chat", "embed"]


@dataclass
class _RouteMetric:
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_status_code: int | None = None
    recent_latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))


@dataclass
class _ModelMetric:
    call_count: int = 0
    cache_hit_count: int = 0
    retry_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    recent_latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))


@dataclass
class _CacheMetric:
    hit_count: int = 0
    miss_count: int = 0
    set_count: int = 0
    eviction_count: int = 0
    expiration_count: int = 0
    current_size: int = 0
    max_size: int = 0


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = datetime.now(timezone.utc)
        self._started_monotonic = monotonic()
        self._routes: dict[tuple[str, str], _RouteMetric] = defaultdict(_RouteMetric)
        self._models: dict[tuple[str, str], _ModelMetric] = defaultdict(_ModelMetric)
        self._caches: dict[str, _CacheMetric] = defaultdict(_CacheMetric)

    def reset(self) -> None:
        with self._lock:
            self._started_at = datetime.now(timezone.utc)
            self._started_monotonic = monotonic()
            self._routes.clear()
            self._models.clear()
            self._caches.clear()

    def record_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        key = (method.upper(), path)
        with self._lock:
            metric = self._routes[key]
            metric.request_count += 1
            metric.total_latency_ms += duration_ms
            metric.max_latency_ms = max(metric.max_latency_ms, duration_ms)
            metric.last_status_code = status_code
            metric.recent_latencies_ms.append(duration_ms)
            if status_code >= 400:
                metric.error_count += 1

    def record_model_call(
        self,
        *,
        operation: ModelOperation,
        model: str,
        duration_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        estimated_cost_usd: float = 0.0,
        cache_hit: bool = False,
        retries: int = 0,
        success: bool = True,
    ) -> None:
        key = (operation, model)
        with self._lock:
            metric = self._models[key]
            metric.call_count += 1
            metric.total_latency_ms += duration_ms
            metric.max_latency_ms = max(metric.max_latency_ms, duration_ms)
            metric.recent_latencies_ms.append(duration_ms)
            metric.retry_count += retries
            metric.estimated_cost_usd += estimated_cost_usd
            if cache_hit:
                metric.cache_hit_count += 1
            if not success:
                metric.failure_count += 1
            if prompt_tokens is not None:
                metric.prompt_tokens += prompt_tokens
            if completion_tokens is not None:
                metric.completion_tokens += completion_tokens
            if total_tokens is not None:
                metric.total_tokens += total_tokens

    def record_cache_event(
        self,
        *,
        cache_name: str,
        event: str,
        current_size: int,
        max_size: int,
        evictions: int = 0,
        expirations: int = 0,
    ) -> None:
        with self._lock:
            metric = self._caches[cache_name]
            metric.current_size = current_size
            metric.max_size = max_size
            metric.eviction_count += evictions
            metric.expiration_count += expirations
            if event == "hit":
                metric.hit_count += 1
            elif event == "miss":
                metric.miss_count += 1
            elif event == "set":
                metric.set_count += 1

    def snapshot(self, settings: Settings) -> MetricsResponse:
        with self._lock:
            route_items = list(self._routes.items())
            model_items = list(self._models.items())
            cache_items = list(self._caches.items())
            uptime_seconds = round(max(0.0, monotonic() - self._started_monotonic), 3)

        total_requests = sum(metric.request_count for _, metric in route_items)
        total_errors = sum(metric.error_count for _, metric in route_items)
        total_latency_ms = sum(metric.total_latency_ms for _, metric in route_items)
        avg_latency_ms = round(total_latency_ms / total_requests, 3) if total_requests else 0.0

        routes = [
            MetricsRouteUsage(
                method=method,
                path=path,
                request_count=metric.request_count,
                error_count=metric.error_count,
                average_latency_ms=round(metric.total_latency_ms / metric.request_count, 3)
                if metric.request_count
                else 0.0,
                p95_latency_ms=self._p95(metric.recent_latencies_ms),
                max_latency_ms=round(metric.max_latency_ms, 3),
                last_status_code=metric.last_status_code,
            )
            for (method, path), metric in sorted(route_items, key=lambda item: (item[0][1], item[0][0]))
        ]
        model_usage = [
            MetricsModelUsage(
                operation=operation,
                model=model,
                call_count=metric.call_count,
                cache_hit_count=metric.cache_hit_count,
                retry_count=metric.retry_count,
                failure_count=metric.failure_count,
                average_latency_ms=round(metric.total_latency_ms / metric.call_count, 3)
                if metric.call_count
                else 0.0,
                p95_latency_ms=self._p95(metric.recent_latencies_ms),
                max_latency_ms=round(metric.max_latency_ms, 3),
                prompt_tokens=metric.prompt_tokens,
                completion_tokens=metric.completion_tokens,
                total_tokens=metric.total_tokens,
                estimated_cost_usd=round(metric.estimated_cost_usd, 6),
            )
            for (operation, model), metric in sorted(model_items, key=lambda item: (item[0][0], item[0][1]))
        ]
        caches = [
            MetricsCacheUsage(
                cache_name=cache_name,
                hit_count=metric.hit_count,
                miss_count=metric.miss_count,
                set_count=metric.set_count,
                eviction_count=metric.eviction_count,
                expiration_count=metric.expiration_count,
                current_size=metric.current_size,
                max_size=metric.max_size,
            )
            for cache_name, metric in sorted(cache_items, key=lambda item: item[0])
        ]

        return MetricsResponse(
            generated_at=datetime.now(timezone.utc),
            uptime_seconds=uptime_seconds,
            app=HealthAppInfo(
                name=settings.app_name,
                version=settings.app_version,
            ),
            requests=MetricsRequestTotals(
                total_requests=total_requests,
                error_requests=total_errors,
                average_latency_ms=avg_latency_ms,
            ),
            routes=routes,
            model_usage=model_usage,
            caches=caches,
        )

    @staticmethod
    def _p95(values: deque[float]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
        return round(ordered[index], 3)
