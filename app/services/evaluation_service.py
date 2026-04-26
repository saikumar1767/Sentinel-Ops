from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.evaluation import (
    eval_data_root,
    load_eval_cases,
    load_investigation_eval_cases,
    load_rag_eval_cases,
    load_workflow_eval_cases,
    score_analysis_response,
    score_investigation_response,
    score_rag_search_results,
    score_workflow_thread_response,
)
from app.bootstrap import resource_root
from app.ollama_client import ChatTurn, ToolCallSpec
from app.rag.chunker import MarkdownChunker
from app.rag.loader import KnowledgeDocumentLoader
from app.rag.service import KnowledgeBaseService
from app.rag.simple_store import SimpleKnowledgeStore
from app.schemas import (
    AnalyzeRequest,
    EvalScenarioSummary,
    EvalSummaryResponse,
    EvalTotals,
    InvestigateRequest,
    RagEvalSummary,
    RetrievalHit,
    WorkflowApproveRequest,
    WorkflowEvalSummary,
    WorkflowInvestigateRequest,
    WorkflowRejectRequest,
)
from app.services.analyze_service import AnalyzeService
from app.services.investigation_service import InvestigationService
from app.services.workflow_service import WorkflowService
from app.settings import Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools
from app.tools.tool_registry import ToolRegistry

VOCABULARY = [
    "429",
    "account lock",
    "authentication",
    "backlog",
    "certificate",
    "connection pool",
    "connection timeout",
    "consumer lag",
    "cpu",
    "credential",
    "database",
    "deadlock",
    "deployment",
    "disk",
    "dns",
    "expired",
    "failed login",
    "latency",
    "memory",
    "missing environment",
    "network",
    "no space left",
    "packet loss",
    "postgres",
    "queue",
    "rate limit",
    "readiness",
    "resolve",
    "restart",
    "segmentation fault",
    "service",
    "sla",
    "swap",
    "throttle",
    "timeout",
    "tls",
]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _incident_type_from_text(text: str) -> str:
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
    if any(token in lowered for token in ("cpu usage", "latency", "autoscaling recommendation")):
        return "performance"
    return "service"


def _severity_from_text(text: str, incident_type: str) -> str:
    lowered = text.lower()
    if "ransomware" in lowered:
        return "critical"
    if incident_type == "performance":
        return "medium"
    if incident_type == "memory" and "swap activity" in lowered and "outofmemory" not in lowered:
        return "medium"
    return "high"


def _stub_retrieval_hit(incident_type: str) -> RetrievalHit:
    snippets = {
        "api": "Partner billing integration can return HTTP 429 when the rate limit budget is exhausted.",
        "authentication": "Repeated failed login attempts plus account lock growth usually indicate credential abuse or stale secrets.",
        "configuration": "Missing environment variables should be classified as configuration even when the service is failing during deployment.",
        "database": "Database timeout incidents often include connection pool exhaustion or long-running transactions on postgres.",
        "deployment": "Rollouts should pause when readiness probes fail for new pods.",
        "disk": "No space left on device means the host is storage constrained and backup writes are likely to fail.",
        "memory": "Sustained swap activity with low available memory indicates memory pressure before an explicit OOM crash.",
        "network": "DNS lookup failures and connection reset events point to a network or resolver problem.",
        "performance": "High CPU plus rising latency usually indicates service saturation rather than a hard outage.",
        "queue": "Queue backlog and consumer lag should be handled as a throughput incident with SLA risk.",
        "security": "Expired certificates and TLS handshake failures are security incidents that block trusted connections.",
        "service": "HTTP 502 plus an open circuit breaker usually indicates an unhealthy upstream service.",
    }
    return RetrievalHit(
        chunk_id=f"stub-{incident_type}",
        document_type="runbook",
        source_path=f"data/knowledge/{incident_type}.md",
        citation=f"data/knowledge/{incident_type}.md#Overview",
        snippet=snippets[incident_type],
        title=f"{incident_type.title()} reference",
        incident_type=incident_type,  # type: ignore[arg-type]
        similarity_score=0.95,
    )


class StubRetriever:
    def search(self, *, query: str, top_k: int, document_types=None, incident_type_hint=None):
        incident_type = incident_type_hint or _incident_type_from_text(query)
        return [_stub_retrieval_hit(incident_type)]


class HeuristicAnalyzeGateway:
    def chat(self, *, model, messages, tools=None, format=None):
        prompt = messages[-1]["content"]
        log_text = prompt.split("Use this log text:", 1)[1].split(
            "Retrieved supporting evidence:",
            1,
        )[0].strip()
        incident_type = _incident_type_from_text(log_text)
        severity = _severity_from_text(log_text, incident_type)
        lines = [line.strip() for line in log_text.splitlines() if line.strip()]
        suspected_root_cause = " ".join(lines[:2]) or "Insufficient log evidence."
        payload = {
            "incident_type": incident_type,
            "severity": severity,
            "summary": f"{incident_type.title()} incident detected from supplied log evidence.",
            "suspected_root_cause": suspected_root_cause,
            "recommended_action": "Use the cited runbook and validate the affected dependency before retrying.",
            "retrieved_evidence": [],
            "source_citations": [],
            "confidence": 0.84,
        }
        body = json.dumps(payload)
        return ChatTurn(
            content=body,
            message={"role": "assistant", "content": body},
            tool_calls=[],
        )


class ScriptedInvestigationGateway:
    def __init__(self, case):
        self.pending_rounds = [
            [ToolCallSpec(name=plan.name, arguments=plan.arguments) for plan in tool_round]
            for tool_round in case.tool_rounds
        ]
        self.final_payload = json.dumps(case.final_response.model_dump())

    def chat(self, *, model, messages, tools=None, format=None):
        if tools is not None:
            if self.pending_rounds:
                tool_calls = self.pending_rounds.pop(0)
                tool_call_payload = [
                    {
                        "function": {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        }
                    }
                    for tool_call in tool_calls
                ]
                return ChatTurn(
                    content="",
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_call_payload,
                    },
                    tool_calls=tool_calls,
                )

            return ChatTurn(
                content="enough evidence",
                message={"role": "assistant", "content": "enough evidence"},
                tool_calls=[],
            )

        return ChatTurn(
            content=self.final_payload,
            message={"role": "assistant", "content": self.final_payload},
            tool_calls=[],
        )


class KeywordEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        normalized = self._normalize(text)
        vector: list[float] = []
        for keyword in VOCABULARY:
            vector.append(float(normalized.count(keyword)))
        vector.append(float(len(normalized.split())))
        return vector

    @staticmethod
    def _normalize(text: str) -> str:
        collapsed = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        return f" {collapsed} "

class EvaluationSummaryService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_summary(self) -> EvalSummaryResponse:
        analyze_summary = self._run_analyze_eval()
        investigate_summary = self._run_investigation_eval()
        rag_summary = self._run_rag_eval()
        workflow_summary = self._run_workflow_eval()

        total_cases = (
            analyze_summary.total_cases
            + investigate_summary.total_cases
            + rag_summary.total_cases
            + workflow_summary.total_cases
        )
        passed_cases = (
            analyze_summary.passed_cases
            + investigate_summary.passed_cases
            + rag_summary.passed_cases
            + workflow_summary.passed_cases
        )
        failed_cases = total_cases - passed_cases

        return EvalSummaryResponse(
            mode="deterministic_local",
            summary=(
                "Deterministic local evaluation summary for SentinelOps service logic, retrieval quality, and workflow durability."
            ),
            generated_at=datetime.now(UTC),
            totals=EvalTotals(
                total_cases=total_cases,
                passed_cases=passed_cases,
                failed_cases=failed_cases,
                overall_pass_rate=_rate(passed_cases, total_cases),
            ),
            analyze=analyze_summary,
            investigate=investigate_summary,
            rag=rag_summary,
            workflow=workflow_summary,
        )

    def _run_analyze_eval(self) -> EvalScenarioSummary:
        service = AnalyzeService(
            settings=Settings(),
            gateway=HeuristicAnalyzeGateway(),
            retriever=StubRetriever(),
        )
        cases = load_eval_cases()
        passed = 0
        failed = 0
        failure_reasons: Counter[str] = Counter()
        confidence_values: list[float] = []
        confidence_by_incident_type: dict[str, list[float]] = defaultdict(list)
        retrieval_used_cases = 0

        for case in cases:
            response = service.analyze(AnalyzeRequest(log_text=case.input_log))
            payload = response.model_dump()
            failures = score_analysis_response(case, payload)
            if failures:
                failed += 1
                failure_reasons.update(failures)
            else:
                passed += 1

            if response.retrieval_status == "used":
                retrieval_used_cases += 1
            confidence_values.append(response.confidence)
            confidence_by_incident_type[response.incident_type].append(response.confidence)

        return EvalScenarioSummary(
            total_cases=len(cases),
            passed_cases=passed,
            failed_cases=failed,
            pass_rate=_rate(passed, len(cases)),
            average_confidence=_average(confidence_values),
            retrieval_used_rate=_rate(retrieval_used_cases, len(cases)),
            average_confidence_by_incident_type={
                incident_type: round(sum(values) / len(values), 3)
                for incident_type, values in sorted(confidence_by_incident_type.items())
            },
            common_failure_reasons=dict(failure_reasons),
        )

    def _run_investigation_eval(self) -> EvalScenarioSummary:
        cases = load_investigation_eval_cases()
        passed = 0
        failed = 0
        failure_reasons: Counter[str] = Counter()
        confidence_values: list[float] = []
        confidence_by_incident_type: dict[str, list[float]] = defaultdict(list)
        retrieval_used_cases = 0

        with TemporaryDirectory(prefix="sentinelops-eval-investigate-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            for case in cases:
                service = self._build_investigation_service(case, temp_dir / case.id)
                response = service.investigate(
                    InvestigateRequest(
                        prompt=case.prompt,
                        candidate_log_paths=case.candidate_log_paths,
                        incident_type_hint=case.incident_type_hint,
                    )
                )
                payload = response.model_dump()
                failures = score_investigation_response(case, payload)
                if failures:
                    failed += 1
                    failure_reasons.update(failures)
                else:
                    passed += 1

                if response.retrieval_status == "used":
                    retrieval_used_cases += 1
                confidence_values.append(response.confidence)
                confidence_by_incident_type[response.incident_type].append(response.confidence)

        return EvalScenarioSummary(
            total_cases=len(cases),
            passed_cases=passed,
            failed_cases=failed,
            pass_rate=_rate(passed, len(cases)),
            average_confidence=_average(confidence_values),
            retrieval_used_rate=_rate(retrieval_used_cases, len(cases)),
            average_confidence_by_incident_type={
                incident_type: round(sum(values) / len(values), 3)
                for incident_type, values in sorted(confidence_by_incident_type.items())
            },
            common_failure_reasons=dict(failure_reasons),
        )

    def _run_rag_eval(self) -> RagEvalSummary:
        cases = load_rag_eval_cases()
        passed = 0
        failed = 0
        failure_reasons: Counter[str] = Counter()
        hit_cases = 0
        hits_returned: list[int] = []

        with TemporaryDirectory(prefix="sentinelops-eval-rag-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            data_root = eval_data_root()
            settings = Settings(
                knowledge_base_dir=data_root / "knowledge",
                incident_templates_dir=data_root / "incident_templates",
                incident_history_dir=data_root / "reference_incidents",
                knowledge_index_path=temp_dir / "knowledge-index.json",
                knowledge_auto_ingest=False,
                knowledge_store_backend="simple",
            )
            service = KnowledgeBaseService(
                settings=settings,
                embedding_provider=KeywordEmbeddingProvider(),
                loader=KnowledgeDocumentLoader(settings),
                chunker=MarkdownChunker(settings),
                store=SimpleKnowledgeStore(settings),
            )
            ingest_result = service.rebuild_index(reset=True)

            for case in cases:
                hits = service.search(
                    query=case.query,
                    top_k=case.top_k,
                    document_types=case.document_types or None,
                    incident_type_hint=case.incident_type_hint,
                )
                failures = score_rag_search_results(case, hits)
                if failures:
                    failed += 1
                    failure_reasons.update(failures)
                else:
                    passed += 1

                if hits:
                    hit_cases += 1
                hits_returned.append(len(hits))

        return RagEvalSummary(
            total_cases=len(cases),
            passed_cases=passed,
            failed_cases=failed,
            pass_rate=_rate(passed, len(cases)),
            retrieval_hit_rate=_rate(hit_cases, len(cases)),
            average_hits_returned=round(sum(hits_returned) / len(hits_returned), 3) if hits_returned else 0.0,
            corpus_document_count=ingest_result.document_count,
            corpus_chunk_count=ingest_result.chunk_count,
            common_failure_reasons=dict(failure_reasons),
        )

    def _run_workflow_eval(self) -> WorkflowEvalSummary:
        cases = load_workflow_eval_cases()
        passed = 0
        failed = 0
        failure_reasons: Counter[str] = Counter()
        confidence_values: list[float] = []
        confidence_by_incident_type: dict[str, list[float]] = defaultdict(list)
        waiting_cases = 0
        completed_cases = 0
        approval_required_cases = 0
        approved_completion_count = 0
        rejected_completion_count = 0

        with TemporaryDirectory(prefix="sentinelops-eval-workflow-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            for case in cases:
                service = self._build_workflow_service(case, temp_dir / case.id)
                try:
                    response = service.start_investigation(
                        WorkflowInvestigateRequest(
                            thread_id=case.id,
                            prompt=case.prompt,
                            candidate_log_paths=case.candidate_log_paths,
                            incident_type_hint=case.incident_type_hint,
                            require_approval_for_remediation=case.require_approval_for_remediation,
                        )
                    )
                    if case.post_start_action == "approve":
                        response = service.approve(
                            case.id,
                            WorkflowApproveRequest(
                                review_notes=case.review_notes,
                            ),
                        )
                    elif case.post_start_action == "reject":
                        response = service.reject(
                            case.id,
                            WorkflowRejectRequest(
                                reason=case.review_notes or "Workflow eval rejection.",
                                edited_remediation_plan=case.edited_remediation_plan,
                            ),
                        )

                    payload = response.model_dump(mode="json")
                    failures = score_workflow_thread_response(case, payload)
                    if failures:
                        failed += 1
                        failure_reasons.update(failures)
                    else:
                        passed += 1

                    if response.status == "waiting_for_approval":
                        waiting_cases += 1
                    if response.status == "completed":
                        completed_cases += 1
                    if response.approval_required:
                        approval_required_cases += 1
                    if response.approval_status == "approved":
                        approved_completion_count += 1
                    if response.approval_status == "rejected":
                        rejected_completion_count += 1
                    if response.confidence is not None:
                        confidence_values.append(response.confidence)
                    if response.incident_type is not None and response.confidence is not None:
                        confidence_by_incident_type[response.incident_type].append(response.confidence)
                finally:
                    service.close()

        return WorkflowEvalSummary(
            total_cases=len(cases),
            passed_cases=passed,
            failed_cases=failed,
            pass_rate=_rate(passed, len(cases)),
            waiting_for_approval_rate=_rate(waiting_cases, len(cases)),
            completed_rate=_rate(completed_cases, len(cases)),
            approval_required_rate=_rate(approval_required_cases, len(cases)),
            approved_completion_count=approved_completion_count,
            rejected_completion_count=rejected_completion_count,
            average_confidence=_average(confidence_values),
            average_confidence_by_incident_type={
                incident_type: round(sum(values) / len(values), 3)
                for incident_type, values in sorted(confidence_by_incident_type.items())
            },
            common_failure_reasons=dict(failure_reasons),
        )

    def _build_investigation_service(self, case, workdir: Path) -> InvestigationService:
        history_dir = workdir / "reference_incidents"
        data_root = eval_data_root()
        shutil.copytree(data_root / "reference_incidents", history_dir)

        settings = Settings(
            allowed_log_roots=[resource_root() / "samples", data_root / "logs"],
            incident_templates_dir=data_root / "incident_templates",
            incident_history_dir=history_dir,
        )
        registry = ToolRegistry(
            file_tools=FileTools(settings),
            incident_tools=IncidentTools(settings),
            settings=settings,
        )
        return InvestigationService(
            settings=settings,
            gateway=ScriptedInvestigationGateway(case),
            tool_registry=registry,
            retriever=StubRetriever(),
        )

    def _build_workflow_service(self, case, workdir: Path) -> WorkflowService:
        history_dir = workdir / "reference_incidents"
        data_root = eval_data_root()
        shutil.copytree(data_root / "reference_incidents", history_dir)

        settings = Settings(
            allowed_log_roots=[resource_root() / "samples", data_root / "logs"],
            incident_templates_dir=data_root / "incident_templates",
            incident_history_dir=history_dir,
            workflow_checkpoint_path=workdir / "workflow" / "checkpoints.sqlite",
        )
        registry = ToolRegistry(
            file_tools=FileTools(settings),
            incident_tools=IncidentTools(settings),
            settings=settings,
        )
        return WorkflowService(
            settings=settings,
            gateway=ScriptedInvestigationGateway(case),
            tool_registry=registry,
            retriever=StubRetriever(),
        )
