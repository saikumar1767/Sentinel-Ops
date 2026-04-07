from __future__ import annotations

from fastapi import FastAPI

from app.settings import Settings


def validate_settings(settings: Settings) -> None:
    if not settings.app_name.strip():
        raise RuntimeError("app_name must not be blank.")
    if not settings.app_version.strip():
        raise RuntimeError("app_version must not be blank.")
    if not settings.analyze_model.strip():
        raise RuntimeError("analyze_model must not be blank.")
    if not settings.investigate_model.strip():
        raise RuntimeError("investigate_model must not be blank.")
    if not settings.embedding_model.strip():
        raise RuntimeError("embedding_model must not be blank.")
    if not settings.allowed_log_roots:
        raise RuntimeError("allowed_log_roots must contain at least one readable root.")
    for root in settings.allowed_log_roots:
        root.parent.mkdir(parents=True, exist_ok=True)
    settings.incident_history_dir.mkdir(parents=True, exist_ok=True)
    settings.workflow_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    settings.audit_db_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.knowledge_store_backend == "simple":
        settings.knowledge_index_path.parent.mkdir(parents=True, exist_ok=True)
    elif settings.knowledge_store_backend == "chroma" and settings.chroma_client_mode == "persistent":
        settings.chroma_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.telemetry_exporter == "otlp" and not (settings.telemetry_otlp_endpoint or "").strip():
        raise RuntimeError(
            "telemetry_otlp_endpoint must be set when telemetry_exporter=otlp."
        )


def run_startup_validation(app: FastAPI, settings: Settings) -> None:
    if not settings.startup_validate_config:
        app.state.startup_validation = "skipped"
        return

    validate_settings(settings)
    app.state.startup_validation = "passed"
