from fastapi import Depends, FastAPI, HTTPException
from pydantic import ValidationError

from app.dependencies import get_analyze_service, get_investigation_service
from app.schemas import AnalyzeRequest, AnalyzeResponse, InvestigateRequest, InvestigateResponse
from app.services.analyze_service import AnalyzeService
from app.services.investigation_service import InvestigationService

app = FastAPI(title="SentinelOps", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    request: AnalyzeRequest,
    service: AnalyzeService = Depends(get_analyze_service),
) -> AnalyzeResponse:
    try:
        return service.analyze(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid analyze JSON.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/investigate", response_model=InvestigateResponse)
def investigate(
    request: InvestigateRequest,
    service: InvestigationService = Depends(get_investigation_service),
) -> InvestigateResponse:
    try:
        return service.investigate(request)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid investigation JSON.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
