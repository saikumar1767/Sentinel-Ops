from collections import Counter
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from app.evaluation import load_eval_cases, score_analysis_response

EVAL_URL = "http://127.0.0.1:8000/analyze"


def main() -> int:
    cases = load_eval_cases()
    failure_reasons: Counter[str] = Counter()
    passed_cases = 0
    failed_cases = 0

    for case in cases:
        try:
            response = requests.post(
                EVAL_URL,
                json={"log_text": case.input_log},
                timeout=120,
            )
        except requests.RequestException as exc:
            failed_cases += 1
            failure_reasons["request_error"] += 1
            print(f"[{case.id}] request failed: {exc}")
            continue

        print(f"[{case.id}] status={response.status_code}")
        print(response.text)

        if response.status_code != 200:
            failed_cases += 1
            failure_reasons[f"http_{response.status_code}"] += 1
            continue

        try:
            payload = response.json()
        except ValueError:
            failed_cases += 1
            failure_reasons["invalid_json"] += 1
            continue

        failures = score_analysis_response(case, payload)
        if failures:
            failed_cases += 1
            failure_reasons.update(failures)
            print(f"[{case.id}] failures: {', '.join(failures)}")
        else:
            passed_cases += 1
            print(f"[{case.id}] passed")

    print()
    print("Evaluation summary")
    print(f"total cases: {len(cases)}")
    print(f"passed cases: {passed_cases}")
    print(f"failed cases: {failed_cases}")

    if failure_reasons:
        print("common failure reasons:")
        for reason, count in failure_reasons.most_common():
            print(f"- {reason}: {count}")
    else:
        print("common failure reasons: none")

    return 0 if failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
