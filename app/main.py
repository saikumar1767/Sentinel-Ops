from fastapi import FastAPI

from app.ollama_client import analyze_log_with_ollama
from app.schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return analyze_log_with_ollama(request.log_text)
