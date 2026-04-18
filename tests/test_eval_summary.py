from fastapi.testclient import TestClient

from app.evaluation import (
    load_eval_cases,
    load_investigation_eval_cases,
    load_rag_eval_cases,
    load_workflow_eval_cases,
)
from app.main import app


def test_eval_summary_endpoint_returns_deterministic_report() -> None:
    client = TestClient(app)

    response = client.get("/eval/summary")

    assert response.status_code == 200
    payload = response.json()

    analyze_count = len(load_eval_cases())
    investigate_count = len(load_investigation_eval_cases())
    rag_count = len(load_rag_eval_cases())
    workflow_count = len(load_workflow_eval_cases())

    assert payload["mode"] == "deterministic_local"
    assert payload["totals"]["total_cases"] == analyze_count + investigate_count + rag_count + workflow_count
    assert payload["analyze"]["total_cases"] == analyze_count
    assert payload["investigate"]["total_cases"] == investigate_count
    assert payload["rag"]["total_cases"] == rag_count
    assert payload["workflow"]["total_cases"] == workflow_count
    assert 0.0 <= payload["totals"]["overall_pass_rate"] <= 1.0
    assert 0.0 <= payload["analyze"]["average_confidence"] <= 1.0
    assert 0.0 <= payload["investigate"]["average_confidence"] <= 1.0
    assert 0.0 <= payload["rag"]["retrieval_hit_rate"] <= 1.0
    assert 0.0 <= payload["workflow"]["pass_rate"] <= 1.0
    assert 0.0 <= payload["workflow"]["waiting_for_approval_rate"] <= 1.0
    assert 0.0 <= payload["workflow"]["completed_rate"] <= 1.0
    assert payload["rag"]["corpus_document_count"] >= 30
    assert payload["rag"]["corpus_chunk_count"] >= payload["rag"]["corpus_document_count"]
