from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_evaluation_summary_service
from app.schemas import EvalSummaryResponse
from app.services.evaluation_service import EvaluationSummaryService

router = APIRouter(tags=["evaluation"])


@router.get(
    "/eval/summary",
    response_model=EvalSummaryResponse,
    summary="Deterministic evaluation summary",
    description=(
        "Runs the local deterministic evaluation harness and returns a summary you can use in demos, judging, "
        "or regression tracking."
    ),
)
def eval_summary(
    service: EvaluationSummaryService = Depends(get_evaluation_summary_service),
) -> EvalSummaryResponse:
    return service.build_summary()
