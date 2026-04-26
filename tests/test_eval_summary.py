import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

import app.evaluation as evaluation
from app.evaluation import (
    load_eval_cases,
    load_investigation_eval_cases,
    load_rag_eval_cases,
    load_workflow_eval_cases,
)
from app.main import app


def test_eval_fixture_dirs_resolve_from_packaged_resource_root(tmp_path, monkeypatch) -> None:
    resource_root = tmp_path / "packaged"
    monkeypatch.setattr(evaluation, "resource_root", lambda: resource_root)

    assert evaluation.eval_cases_dir() == resource_root / "data" / "eval_cases"
    assert evaluation.investigation_eval_cases_dir() == resource_root / "data" / "tool_eval_cases"
    assert evaluation.rag_eval_cases_dir() == resource_root / "data" / "rag_eval_cases"


def test_pyproject_bundles_eval_fixture_data() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    wheel_includes = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    sdist_includes = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

    for source_path in ("data/eval_cases", "data/tool_eval_cases", "data/rag_eval_cases"):
        assert source_path in wheel_includes
        assert f"/{source_path}" in sdist_includes


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
