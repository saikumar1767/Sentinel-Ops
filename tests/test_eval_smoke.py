import pytest
from fastapi.testclient import TestClient

from app.evaluation import REQUIRED_RESPONSE_KEYS, load_eval_cases, score_analysis_response
from app.main import app

client = TestClient(app)
CASES = load_eval_cases()


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_analyze_eval_cases(case) -> None:
    response = client.post("/analyze", json={"log_text": case.input_log})

    assert response.status_code == 200

    payload = response.json()
    for key in REQUIRED_RESPONSE_KEYS:
        assert key in payload

    failures = score_analysis_response(case, payload)
    assert not failures, f"{case.id} failed: {', '.join(failures)}"
