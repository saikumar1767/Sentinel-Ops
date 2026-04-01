from __future__ import annotations

import json

from app.schemas import InvestigateRequest


def build_analyze_messages(log_text: str, schema: dict[str, object]) -> list[dict[str, str]]:
    schema_text = json.dumps(schema, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "You are SentinelOps. Return JSON only and follow the provided schema exactly."
            ),
        },
        {
            "role": "user",
            "content": f"""
Return JSON only.
Use exactly this schema:
{schema_text}

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
""".strip(),
        },
    ]


def build_investigation_planner_messages(
    request: InvestigateRequest,
    candidate_log_paths: list[str],
    baseline_evidence_summary: str,
    completed_evidence_citations: list[str],
) -> list[dict[str, str]]:
    candidate_block = "\n".join(f"- {path}" for path in candidate_log_paths) or "- None provided"
    hint_block = request.incident_type_hint or "none"
    citation_block = "\n".join(f"- {item}" for item in completed_evidence_citations) or "- None yet"

    return [
        {
            "role": "system",
            "content": """
You are SentinelOps v2 running a controlled tool-using workflow.

Rules:
- Use only the available local tools.
- The system already collected baseline evidence before you were called.
- Prefer 0 to 2 additional focused tool calls before you stop.
- Do not repeat the exact same tool call if you already have the answer.
- Tool outputs are truncated and filtered, so base conclusions only on the returned evidence.
- Favor candidate log files that were supplied in the prompt.
- Do not skip log evidence if candidate log files were provided.
- Only call a template or history tool after you have inspected the relevant log evidence or if log access failed safely.
- Once you have enough evidence, stop calling tools. Do not return the final report yet.
""".strip(),
        },
        {
            "role": "user",
            "content": f"""
Investigation request:
{request.prompt}

Incident type hint:
{hint_block}

Candidate log files you may inspect:
{candidate_block}

Baseline evidence already collected:
{baseline_evidence_summary}

Evidence citations already available:
{citation_block}

Use more tools only to fill evidence gaps. You may also load a matching incident template or recent incidents if it helps.
""".strip(),
        },
    ]


def build_investigation_final_messages(
    request: InvestigateRequest,
    evidence_summary: str,
    schema: dict[str, object],
    evidence_citations: list[str],
) -> list[dict[str, str]]:
    schema_text = json.dumps(schema, indent=2)
    citation_block = "\n".join(f"- {item}" for item in evidence_citations) or "- None"

    return [
        {
            "role": "system",
            "content": (
                "You are SentinelOps. Return JSON only, follow the schema exactly, "
                "and keep the report grounded in the supplied evidence."
            ),
        },
        {
            "role": "user",
            "content": f"""
Return JSON only.
Use exactly this schema:
{schema_text}

Field guidance:
- incident_type: choose the best category from the schema enum.
- severity: choose critical, high, medium, or low.
- top_error_lines: include the most useful concrete log lines from evidence.
- suspected_root_cause: keep it specific and evidence-based.
- next_steps: 2 to 5 short concrete actions.
- manager_summary: 1 short paragraph for a non-technical manager.
- evidence_used: cite the exact tool/path identifiers from the allowed evidence citations list when possible.
- confidence: numeric value from 0.0 to 1.0.

Grounding rules:
- If concrete log evidence exists, top_error_lines must include it.
- Do not claim missing evidence when the summary below contains real log lines.
- Do not rely only on templates if log evidence is available.
- If the evidence is thin or conflicting, say so and lower confidence.

Original request:
{request.prompt}

Collected evidence:
{evidence_summary}

Allowed evidence citations:
{citation_block}
""".strip(),
        },
    ]
