from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from app.log_utils import dedupe_preserve_order, guess_incident_type, normalize_log_line
from app.schemas import (
    IncidentType,
    InvestigateRequest,
    RetrievalHit,
    RootCauseDiagnostics,
    RootCauseHypothesis,
    RootCauseSignal,
    Severity,
)
from app.tools.tool_registry import ToolExecutionRecord


SeverityRank = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class EvidenceSignal:
    name: str
    incident_type: IncidentType
    severity: SeverityRank
    weight: float
    line: str
    normalized_line: str
    source_citation: str


@dataclass(frozen=True)
class StructuredLogEvent:
    timestamp: str | None
    level: str | None
    message: str
    source_citation: str
    line_number: int | None = None

    def timeline_text(self) -> str:
        prefix = f"{self.timestamp} " if self.timestamp else ""
        level = f"{self.level} " if self.level else ""
        return f"{prefix}{level}{self.message}".strip()


@dataclass(frozen=True)
class CausalHypothesis:
    title: str
    incident_type: IncidentType
    root_cause: str
    score: float
    supporting_signals: list[str] = field(default_factory=list)
    remediation_focus: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RootCauseReport:
    incident_type: IncidentType
    severity: Severity
    primary_hypothesis: CausalHypothesis | None
    signals: list[EvidenceSignal]
    events: list[StructuredLogEvent]
    regression_detected: bool
    timeline: list[str]
    missing_evidence: list[str]

    @property
    def root_cause(self) -> str:
        if self.primary_hypothesis is None:
            return ""
        return self.primary_hypothesis.root_cause

    @property
    def next_steps(self) -> list[str]:
        if self.primary_hypothesis is None:
            return []
        return self.primary_hypothesis.remediation_focus

    @property
    def source_citations(self) -> list[str]:
        return dedupe_preserve_order(signal.source_citation for signal in self.signals if signal.source_citation)

    @property
    def evidence_strength(self) -> float:
        if not self.signals:
            return 0.2
        weighted = min(sum(signal.weight for signal in self.signals), 18.0)
        regression_bonus = 1.5 if self.regression_detected else 0.0
        timeline_bonus = min(len(self.timeline), 4) * 0.4
        return round(min((weighted + regression_bonus + timeline_bonus) / 20.0, 0.98), 2)

    def to_diagnostics(self) -> RootCauseDiagnostics:
        hypotheses = []
        if self.primary_hypothesis is not None:
            hypotheses.append(
                RootCauseHypothesis(
                    title=self.primary_hypothesis.title,
                    incident_type=self.primary_hypothesis.incident_type,
                    root_cause=self.primary_hypothesis.root_cause,
                    score=self.primary_hypothesis.score,
                    supporting_signals=self.primary_hypothesis.supporting_signals,
                    remediation_focus=self.primary_hypothesis.remediation_focus,
                )
            )
        return RootCauseDiagnostics(
            incident_type=self.incident_type,
            severity=self.severity,
            evidence_strength=self.evidence_strength,
            regression_detected=self.regression_detected,
            primary_root_cause=self.root_cause or None,
            hypotheses=hypotheses,
            signals=[
                RootCauseSignal(
                    name=signal.name,
                    incident_type=signal.incident_type,
                    severity=signal.severity,
                    weight=signal.weight,
                    evidence=signal.normalized_line,
                    source_citation=signal.source_citation,
                )
                for signal in self.signals[:12]
            ],
            timeline=self.timeline,
            missing_evidence=self.missing_evidence,
        )

    def prompt_summary(self) -> str:
        if not self.signals:
            return "No deterministic root-cause signals were extracted."

        signal_lines = [
            f"- {signal.name} ({signal.severity}) from {signal.source_citation}: {signal.normalized_line}"
            for signal in self.signals[:6]
        ]
        hypothesis = self.root_cause or "No dominant deterministic hypothesis."
        return "\n".join(
            [
                f"Dominant hypothesis: {hypothesis}",
                f"Incident type: {self.incident_type}",
                f"Severity estimate: {self.severity}",
                f"Regression signal: {'yes' if self.regression_detected else 'no'}",
                f"Evidence strength: {self.evidence_strength}",
                "Timeline:",
                *[f"- {item}" for item in self.timeline[:4]],
                "Signals:",
                *signal_lines,
                "Missing evidence:",
                *[f"- {item}" for item in self.missing_evidence],
            ]
        )


@dataclass(frozen=True)
class _SignalPattern:
    name: str
    incident_type: IncidentType
    severity: SeverityRank
    weight: float
    pattern: re.Pattern[str]


_SIGNAL_PATTERNS = (
    _SignalPattern("connection_pool_exhaustion", "database", "high", 5.0, re.compile(r"pool exhausted|connection pool", re.I)),
    _SignalPattern("database_timeout", "database", "high", 4.0, re.compile(r"database.*timeout|timeout.*database|postgres.*timeout", re.I)),
    _SignalPattern("stalled_database_checkout", "database", "high", 3.5, re.compile(r"stalled.*database connection|waiting for (?:a )?free database connection", re.I)),
    _SignalPattern("database_deadlock", "database", "high", 4.5, re.compile(r"deadlock|lock wait timeout", re.I)),
    _SignalPattern("missing_configuration", "configuration", "high", 4.5, re.compile(r"missing (?:env|environment|config|configuration|secret)|required .* not set", re.I)),
    _SignalPattern("dns_resolution_failure", "network", "high", 4.0, re.compile(r"dns|resolve|resolution|lookup.*timed out", re.I)),
    _SignalPattern("packet_loss", "network", "medium", 3.5, re.compile(r"packet loss|connection reset|network unreachable", re.I)),
    _SignalPattern("disk_full", "disk", "high", 4.5, re.compile(r"no space left|disk full|disk usage .*100|storage exhausted", re.I)),
    _SignalPattern("memory_exhaustion", "memory", "high", 4.5, re.compile(r"out of memory|oom|exit code 137|swap", re.I)),
    _SignalPattern("cpu_saturation", "performance", "medium", 3.0, re.compile(r"cpu.*(?:high|saturat|usage)|latency|p95|p99", re.I)),
    _SignalPattern("queue_backlog", "queue", "high", 4.0, re.compile(r"queue backlog|consumer lag|sla.*breach", re.I)),
    _SignalPattern("authentication_abuse", "authentication", "high", 4.0, re.compile(r"failed login|credential|account lock|bruteforce|brute force", re.I)),
    _SignalPattern("certificate_failure", "security", "high", 4.0, re.compile(r"certificate|tls handshake|expired cert", re.I)),
    _SignalPattern("security_compromise", "security", "critical", 5.5, re.compile(r"ransomware|malware|exfiltrat|compromise", re.I)),
    _SignalPattern("rate_limit", "api", "medium", 3.5, re.compile(r"\b429\b|rate limit|too many requests", re.I)),
    _SignalPattern("service_crash", "service", "high", 4.0, re.compile(r"segmentation fault|crash|crashloop|restarts?|502|5xx", re.I)),
)

_SEVERITY_ORDER: dict[SeverityRank, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class RootCauseEngine:
    def analyze(
        self,
        *,
        request: InvestigateRequest,
        records: list[ToolExecutionRecord],
        retrieval_hits: list[RetrievalHit],
    ) -> RootCauseReport:
        events = self._extract_events(records)
        signals = self._extract_signals(records)
        incident_type = self._infer_incident_type(request, signals, retrieval_hits)
        relevant_signals = [signal for signal in signals if signal.incident_type == incident_type] or signals
        regression_detected = self._has_regression_signal(records)
        hypothesis = self._build_hypothesis(
            incident_type=incident_type,
            signals=relevant_signals,
            regression_detected=regression_detected,
        )
        return RootCauseReport(
            incident_type=incident_type,
            severity=self._estimate_severity(relevant_signals, fallback="medium" if relevant_signals else "low"),
            primary_hypothesis=hypothesis,
            signals=relevant_signals,
            events=events,
            regression_detected=regression_detected,
            timeline=self._extract_timeline(events, relevant_signals),
            missing_evidence=self._missing_evidence(
                request=request,
                records=records,
                signals=relevant_signals,
                retrieval_hits=retrieval_hits,
                regression_detected=regression_detected,
            ),
        )

    def _extract_events(self, records: list[ToolExecutionRecord]) -> list[StructuredLogEvent]:
        events: list[StructuredLogEvent] = []
        seen: set[tuple[str, str]] = set()
        for record in records:
            if not record.ok:
                continue
            source_citation = self._record_citation(record)
            for line in self._record_lines(record):
                event = self._parse_log_event(line, source_citation=source_citation)
                key = (event.source_citation, event.timeline_text())
                if key in seen:
                    continue
                seen.add(key)
                events.append(event)
        return sorted(events, key=lambda event: (event.timestamp or "", event.line_number or 0, event.message))

    def _extract_signals(self, records: list[ToolExecutionRecord]) -> list[EvidenceSignal]:
        signals: list[EvidenceSignal] = []
        seen: set[tuple[str, str]] = set()

        for record in records:
            if not record.ok:
                continue
            source_citation = self._record_citation(record)
            for line in self._record_lines(record):
                normalized = self._normalize_line(line)
                for pattern in _SIGNAL_PATTERNS:
                    if not pattern.pattern.search(normalized):
                        continue
                    key = (pattern.name, normalized)
                    if key in seen:
                        continue
                    seen.add(key)
                    signals.append(
                        EvidenceSignal(
                            name=pattern.name,
                            incident_type=pattern.incident_type,
                            severity=pattern.severity,
                            weight=pattern.weight,
                            line=line,
                            normalized_line=normalized,
                            source_citation=source_citation,
                        )
                    )

        return sorted(signals, key=lambda signal: (-signal.weight, signal.source_citation, signal.line))

    def _parse_log_event(self, line: str, *, source_citation: str) -> StructuredLogEvent:
        cleaned = self._normalize_line(line)
        line_number = None
        line_number_match = re.match(r"^\s*(\d+):", line)
        if line_number_match:
            line_number = int(line_number_match.group(1))

        timestamp = None
        timestamp_match = re.search(r"\b(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\b", line)
        if timestamp_match:
            timestamp = timestamp_match.group(1).replace("T", " ")

        level = None
        level_match = re.search(r"\b(CRITICAL|FATAL|ERROR|WARN|WARNING|INFO|DEBUG)\b", line, re.I)
        if level_match:
            level = level_match.group(1).upper()
            if level == "WARNING":
                level = "WARN"

        message = cleaned
        if timestamp:
            message = message.replace(timestamp, "", 1).strip()
        if level:
            message = re.sub(rf"\b{re.escape(level)}\b", "", message, count=1, flags=re.I).strip()
        return StructuredLogEvent(
            timestamp=timestamp,
            level=level,
            message=message or cleaned,
            source_citation=source_citation,
            line_number=line_number,
        )

    @staticmethod
    def _record_lines(record: ToolExecutionRecord) -> list[str]:
        payload = record.payload
        lines: list[str] = []
        for key in ("selected_lines", "matched_lines", "new_error_lines", "missing_success_lines", "differences"):
            value = payload.get(key)
            if isinstance(value, list):
                lines.extend(str(item) for item in value if str(item).strip())
        return lines

    @staticmethod
    def _record_citation(record: ToolExecutionRecord) -> str:
        payload = record.payload
        if record.name == "read_log_file" and payload.get("path"):
            return f"{record.name}:{payload['path']}"
        if record.name == "grep_error_pattern" and payload.get("path"):
            return f"{record.name}:{payload['path']}"
        if record.name == "compare_two_logs" and payload.get("path_a") and payload.get("path_b"):
            return f"{record.name}:{payload['path_a']}->{payload['path_b']}"
        if record.name == "load_incident_template" and payload.get("incident_type"):
            return f"{record.name}:{payload['incident_type']}"
        return record.name

    @staticmethod
    def _normalize_line(line: str) -> str:
        without_prefix = re.sub(r"^(?:New error in [^:]+:|Missing success from [^:]+:)\s*", "", line.strip())
        without_line_number = re.sub(r"^\d+:\s*", "", without_prefix)
        return normalize_log_line(without_line_number).strip().rstrip(".")

    @staticmethod
    def _infer_incident_type(
        request: InvestigateRequest,
        signals: list[EvidenceSignal],
        retrieval_hits: list[RetrievalHit],
    ) -> IncidentType:
        if request.incident_type_hint is not None:
            return request.incident_type_hint
        if signals:
            weighted = Counter()
            for signal in signals:
                weighted[signal.incident_type] += signal.weight
            return weighted.most_common(1)[0][0]
        for hit in retrieval_hits:
            if hit.incident_type is not None:
                return hit.incident_type
        return guess_incident_type(request.prompt) or "service"

    @staticmethod
    def _has_regression_signal(records: list[ToolExecutionRecord]) -> bool:
        return any(
            record.ok
            and record.name == "compare_two_logs"
            and (record.payload.get("new_error_lines") or record.payload.get("missing_success_lines"))
            for record in records
        )

    def _build_hypothesis(
        self,
        *,
        incident_type: IncidentType,
        signals: list[EvidenceSignal],
        regression_detected: bool,
    ) -> CausalHypothesis | None:
        if not signals:
            return None

        signal_names = {signal.name for signal in signals}
        root_cause = self._root_cause_text(incident_type, signal_names, signals)
        title = root_cause.split(" is ", 1)[0].split(" appears ", 1)[0]
        score = round(sum(signal.weight for signal in signals) + (1.0 if regression_detected else 0.0), 2)
        return CausalHypothesis(
            title=title,
            incident_type=incident_type,
            root_cause=root_cause,
            score=score,
            supporting_signals=dedupe_preserve_order(signal.name for signal in signals),
            remediation_focus=self._remediation_steps(incident_type, signal_names),
        )

    def _root_cause_text(
        self,
        incident_type: IncidentType,
        signal_names: set[str],
        signals: list[EvidenceSignal],
    ) -> str:
        if incident_type == "database":
            primary_postgres = any("primary-postgres" in signal.normalized_line.lower() for signal in signals)
            if "connection_pool_exhaustion" in signal_names:
                subject = "Connection pool exhaustion on primary-postgres" if primary_postgres else "Database connection pool exhaustion"
                effects: list[str] = []
                if "database_timeout" in signal_names:
                    effects.append("repeated database timeouts")
                if "stalled_database_checkout" in signal_names:
                    effects.append("stalled checkout requests")
                return f"{subject} is causing {self._join_phrases(effects)}" if effects else subject
            if "database_deadlock" in signal_names:
                return "Database deadlocks or lock waits are blocking normal transaction progress"
            if "database_timeout" in signal_names:
                return "Repeated database connection timeouts are preventing the service from completing database work"

        if incident_type == "configuration":
            variable = self._first_config_key(signals)
            if variable:
                return f"Missing configuration value {variable} is blocking service startup or readiness"
            return "Missing required configuration is blocking service startup or readiness"

        if incident_type == "network":
            if "dns_resolution_failure" in signal_names:
                return "DNS resolution failures are preventing the service from reaching a required dependency"
            return "Network transport instability is interrupting dependency communication"

        if incident_type == "queue":
            return "Queue backlog and consumer lag indicate processing throughput is below incoming demand"
        if incident_type == "disk":
            return "Disk exhaustion is preventing write-heavy service operations from completing"
        if incident_type == "memory":
            return "Memory exhaustion is forcing the service or host into an unhealthy state"
        if incident_type == "performance":
            return "Resource saturation is driving elevated latency and degraded service performance"
        if incident_type == "authentication":
            return "Repeated authentication failures indicate credential abuse, stale secrets, or lockout pressure"
        if incident_type == "security":
            if "security_compromise" in signal_names:
                return "Security compromise indicators require immediate containment and incident escalation"
            return "Certificate or TLS failures are breaking secure service communication"
        if incident_type == "api":
            return "API rate limiting is rejecting requests because caller volume exceeds the allowed quota"

        return "Service crash or upstream failure signals indicate the application runtime is unhealthy"

    @staticmethod
    def _first_config_key(signals: list[EvidenceSignal]) -> str:
        for signal in signals:
            match = re.search(r"\b[A-Z][A-Z0-9_]{2,}\b", signal.normalized_line)
            if match:
                return match.group(0)
        return ""

    @staticmethod
    def _remediation_steps(incident_type: IncidentType, signal_names: set[str]) -> list[str]:
        if incident_type == "database":
            steps = [
                "Confirm database reachability, connection pool health, and active saturation symptoms.",
                "Compare the first failing timestamp against deploys, traffic changes, and database capacity events.",
            ]
            if "connection_pool_exhaustion" in signal_names:
                steps.append("Reduce caller concurrency or shed noncritical traffic until connection checkout recovers.")
            steps.append("Mitigate by reducing pressure, restarting stuck workers only if safe, and validating recovery.")
            return steps
        if incident_type == "configuration":
            return [
                "Identify the missing config or secret in the failing environment.",
                "Restore the reviewed value through the normal secret/config deployment path.",
                "Restart or redeploy only after readiness checks confirm the value is present.",
            ]
        if incident_type == "network":
            return [
                "Confirm resolver, route, and dependency reachability from the affected service network.",
                "Compare the failure window with DNS, ingress, firewall, or subnet changes.",
                "Fail over or route around the broken path only after impact and rollback are clear.",
            ]
        if incident_type == "queue":
            return [
                "Measure backlog growth, consumer lag, and producer rate for the affected queue.",
                "Scale or unblock consumers after confirming downstream dependencies can absorb the load.",
                "Throttle producers or prioritize critical work until lag returns to the SLA window.",
            ]
        if incident_type == "security":
            return [
                "Escalate to the security owner and preserve evidence before making destructive changes.",
                "Contain affected credentials, hosts, or traffic paths according to the incident runbook.",
                "Validate recovery with security and service owners before returning normal traffic.",
            ]
        return [
            "Confirm the failure pattern from cited logs and current runtime health.",
            "Correlate the first failing timestamp with recent deploys, config changes, and dependency alerts.",
            "Apply the lowest-risk mitigation first and validate recovery before broad rollout.",
        ]

    def _estimate_severity(self, signals: list[EvidenceSignal], *, fallback: Severity) -> Severity:
        if not signals:
            return fallback
        highest = max(signals, key=lambda signal: _SEVERITY_ORDER[signal.severity]).severity
        return highest

    @staticmethod
    def _extract_timeline(events: list[StructuredLogEvent], signals: list[EvidenceSignal]) -> list[str]:
        event_timeline = [
            event.timeline_text()
            for event in events
            if event.level in {"ERROR", "CRITICAL", "FATAL", "WARN"} or not event.level
        ]
        signal_timeline = [signal.normalized_line for signal in signals if signal.normalized_line]
        return dedupe_preserve_order([*event_timeline, *signal_timeline])[:8]

    @staticmethod
    def _missing_evidence(
        *,
        request: InvestigateRequest,
        records: list[ToolExecutionRecord],
        signals: list[EvidenceSignal],
        retrieval_hits: list[RetrievalHit],
        regression_detected: bool,
    ) -> list[str]:
        missing: list[str] = []
        if request.candidate_log_paths and not any(record.ok and record.name == "read_log_file" for record in records):
            missing.append("No candidate log file was read successfully.")
        if len(request.candidate_log_paths) >= 2 and not regression_detected:
            missing.append("No before/after regression delta was confirmed from the supplied log pair.")
        if not retrieval_hits:
            missing.append("No retrieval-backed runbook or prior-incident evidence was attached.")
        if not signals:
            missing.append("No deterministic failure signal matched the current evidence.")
        return missing

    @staticmethod
    def _join_phrases(phrases: list[str]) -> str:
        if not phrases:
            return "the observed failure symptoms"
        if len(phrases) == 1:
            return phrases[0]
        if len(phrases) == 2:
            return f"{phrases[0]} and {phrases[1]}"
        return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"
