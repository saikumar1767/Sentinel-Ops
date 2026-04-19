from __future__ import annotations

from fastapi import FastAPI

from app.persistence import is_sqlite_url, sqlite_database_path
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
    if not settings.model_is_allowed_by_policy(settings.analyze_model):
        raise RuntimeError(
            f"analyze_model '{settings.analyze_model}' is not allowed by the configured model_license_policy."
        )
    if not settings.model_is_allowed_by_policy(settings.investigate_model):
        raise RuntimeError(
            f"investigate_model '{settings.investigate_model}' is not allowed by the configured model_license_policy."
        )
    if not settings.model_is_allowed_by_policy(settings.embedding_model):
        raise RuntimeError(
            f"embedding_model '{settings.embedding_model}' is not allowed by the configured model_license_policy."
        )
    if not settings.allowed_log_roots:
        raise RuntimeError("allowed_log_roots must contain at least one readable root.")
    for root in settings.allowed_log_roots:
        root.parent.mkdir(parents=True, exist_ok=True)
    settings.incident_history_dir.mkdir(parents=True, exist_ok=True)
    settings.workflow_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_sqlite_path = sqlite_database_path(settings.effective_workflow_checkpoint_database_url)
    if workflow_sqlite_path is not None:
        workflow_sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.audit_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.incident_library_dir.mkdir(parents=True, exist_ok=True)
    settings.reference_incidents_dir.mkdir(parents=True, exist_ok=True)
    metadata_sqlite_path = sqlite_database_path(settings.effective_metadata_database_url)
    if metadata_sqlite_path is not None:
        metadata_sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.knowledge_store_backend == "simple":
        settings.knowledge_index_path.parent.mkdir(parents=True, exist_ok=True)
    elif settings.knowledge_store_backend == "chroma" and settings.chroma_client_mode == "persistent":
        settings.chroma_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.telemetry_exporter == "otlp" and not (settings.telemetry_otlp_endpoint or "").strip():
        raise RuntimeError(
            "telemetry_otlp_endpoint must be set when telemetry_exporter=otlp."
        )
    if settings.auth_mode == "api_key":
        if not settings.auth_api_key and not settings.auth_bearer_tokens:
            raise RuntimeError(
                "auth_api_key or auth_bearer_tokens must be configured when auth_mode=api_key."
            )
    if settings.auth_mode == "oidc":
        if not settings.auth_oidc_issuer_url:
            raise RuntimeError("auth_oidc_issuer_url must be set when auth_mode=oidc.")
        if not settings.effective_auth_oidc_jwks_url:
            raise RuntimeError("auth_oidc_jwks_url must be derivable when auth_mode=oidc.")
    if settings.deployment_mode == "production":
        if settings.auth_mode != "oidc":
            raise RuntimeError("auth_mode must be set to 'oidc' when deployment_mode=production.")
        if is_sqlite_url(settings.effective_metadata_database_url):
            raise RuntimeError("metadata_database_url must point to a shared non-SQLite database in production.")
        if is_sqlite_url(settings.effective_workflow_checkpoint_database_url):
            raise RuntimeError(
                "workflow_checkpoint_database_url must point to a shared non-SQLite database in production."
            )
        if settings.telemetry_exporter == "none":
            raise RuntimeError("telemetry_exporter must not be 'none' when deployment_mode=production.")
        if not settings.public_base_url or not settings.public_base_url.startswith("https://"):
            raise RuntimeError("public_base_url must be configured with https:// when deployment_mode=production.")


def run_startup_validation(app: FastAPI, settings: Settings) -> None:
    if not settings.startup_validate_config:
        app.state.startup_validation = "skipped"
        return

    validate_settings(settings)
    app.state.startup_validation = "passed"
