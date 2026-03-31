import json

import requests

from app.schemas import AnalyzeModelResponse, AnalyzeResponse

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"


def normalize_log_line(line: str) -> str:
    parts = line.strip().split(" ", 3)
    if len(parts) == 4 and parts[2].upper() in {"INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"}:
        return parts[3].strip()
    return line.strip()


def extract_top_error_lines(log_text: str, limit: int = 3) -> list[str]:
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if not lines:
        return ["No log lines provided"]

    priority_lines = [
        line
        for line in lines
        if any(level in line.upper() for level in ("CRITICAL", "ERROR", "WARN", "WARNING", "FATAL"))
    ]

    selected = priority_lines[:limit] or lines[:limit]
    return selected


def ground_suspected_root_cause(root_cause: str, top_error_lines: list[str]) -> str:
    cleaned_root_cause = root_cause.strip().rstrip(".")
    evidence = "; ".join(normalize_log_line(line) for line in top_error_lines[:3] if line.strip())

    if not evidence:
        return cleaned_root_cause

    evidence_clause = f"Evidence from log: {evidence}"
    if evidence_clause.lower() in cleaned_root_cause.lower():
        return cleaned_root_cause

    return f"{cleaned_root_cause}. {evidence_clause}"


def analyze_log_with_ollama(log_text: str) -> AnalyzeResponse:
    schema = AnalyzeModelResponse.model_json_schema()

    prompt = f"""
Return JSON only.
Return exactly these six fields and no others:
incident_type
severity
summary
suspected_root_cause
recommended_action
confidence

Choose incident_type from:
api
authentication
configuration
database
deployment
disk
memory
network
performance
queue
security
service

Incident type guidance:
- api = HTTP 429, upstream API contract issues, or endpoint-specific API failures
- authentication = failed logins, account lockouts, or credential misuse
- configuration = missing environment variables, missing config values, or secret/config mistakes
- database = deadlocks, pool exhaustion, or database connection failures
- deployment = rollout problems, readiness probe failures, or release-stage failures
- disk = no space left, disk full, or storage exhaustion
- memory = out-of-memory, swap pressure, or memory exhaustion
- network = DNS failures, packet loss, connection resets, or transport connectivity issues
- performance = high CPU, latency spikes, or throughput degradation without a hard outage
- queue = queue backlog, consumer lag, or message processing delays
- security = certificates, malware, ransomware, or active security incidents
- service = crashes, restarts, 5xx upstream failures, or circuit-breaker events

Classification rules:
- If the log explicitly shows a missing environment variable or missing config value, choose configuration even if it happened during a deployment.
- DNS failures, packet loss, and connection reset errors are network, not api.
- Queue backlog plus consumer lag or breached SLA should usually be high severity.
- Segmentation faults, crashes, and repeated restarts are service unless the log explicitly mentions memory, OOM, heap, swap, or exit code 137.
- Do not invent memory issues when the log does not mention them.

Choose severity from:
critical
high
medium
low

Severity rubric:
- critical = active security compromise, confirmed data loss, or complete outage
- high = repeated errors, failed deployments, service crashes, disk full, or broken dependencies
- medium = degraded performance, queue lag, packet loss, or rate limiting with partial impact
- low = limited warning with minor user impact

Use concrete words from the log when you describe the suspected_root_cause.

Set confidence to a numeric value between 0.0 and 1.0.

Use this log text:

{log_text}
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": schema,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    parsed = json.loads(data["response"])
    model_response = AnalyzeModelResponse(**parsed)
    top_error_lines = extract_top_error_lines(log_text)
    response_payload = model_response.model_dump()
    response_payload["suspected_root_cause"] = ground_suspected_root_cause(
        model_response.suspected_root_cause,
        top_error_lines,
    )
    return AnalyzeResponse(
        **response_payload,
        top_error_lines=top_error_lines,
    )
