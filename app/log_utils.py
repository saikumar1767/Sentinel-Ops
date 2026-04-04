from __future__ import annotations

from typing import Iterable

from app.schemas import IncidentType

ERROR_KEYWORDS = (
    "CRITICAL",
    "ERROR",
    "WARN",
    "WARNING",
    "FATAL",
    "EXCEPTION",
    "FAILED",
    "FAILURE",
    "TIMEOUT",
    "REFUSED",
)

SUCCESS_KEYWORDS = (
    "SUCCESS",
    "HEALTHY",
    "READY",
    "COMPLETED",
    "STARTED",
    "CONNECTED",
    "RECOVERED",
    "OK",
)

LOG_LEVEL_TOKENS = {"INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"}


def split_nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalize_log_line(line: str) -> str:
    parts = line.strip().split(" ", 3)
    if len(parts) == 4 and parts[2].upper() in LOG_LEVEL_TOKENS:
        return parts[3].strip()
    return line.strip()


def looks_like_error(line: str) -> bool:
    upper_line = line.upper()
    return any(keyword in upper_line for keyword in ERROR_KEYWORDS)


def looks_like_success(line: str) -> bool:
    upper_line = line.upper()
    return any(keyword in upper_line for keyword in SUCCESS_KEYWORDS)


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)

    return deduped


def extract_priority_lines(log_text: str, limit: int = 3) -> list[str]:
    lines = split_nonempty_lines(log_text)
    if not lines:
        return ["No log lines provided"]

    priority_lines = [line for line in lines if looks_like_error(line)]
    selected = priority_lines[:limit] or lines[:limit]
    return selected


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3].rstrip()}..."


def strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()

    return stripped


def guess_incident_type(text: str) -> IncidentType | None:
    lowered = text.lower()

    if any(token in lowered for token in ("missing env", "missing config", "payment_api_key", "redis_url")):
        return "configuration"
    if any(token in lowered for token in ("failed login", "credential", "account lock", "lock threshold")):
        return "authentication"
    if any(token in lowered for token in ("outofmemory", "heap space", "swap activity", "memory available")):
        return "memory"
    if any(token in lowered for token in ("ransomware", "certificate", "tls handshake", "malware")):
        return "security"
    if any(token in lowered for token in ("queue backlog", "consumer lag", "processing delay breached sla")):
        return "queue"
    if any(token in lowered for token in ("disk usage", "no space left", "storage exhaustion")):
        return "disk"
    if any(token in lowered for token in ("readiness probe", "rollout paused", "failed deployment")):
        return "deployment"
    if any(token in lowered for token in ("failed to resolve", "dns lookup", "packet loss", "connection reset")):
        return "network"
    if any(token in lowered for token in ("rate limit", "http 429", "throttle")):
        return "api"
    if any(token in lowered for token in ("database", "pool exhausted", "deadlock", "lock wait timeout")):
        return "database"
    if any(token in lowered for token in ("cpu usage", "latency p95", "autoscaling recommendation")):
        return "performance"
    if any(token in lowered for token in ("502", "segmentation fault", "restarting", "circuit breaker")):
        return "service"
    return None
