from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BOOLEAN, JSON, Column, DateTime, MetaData, String, Table, Text, insert, select, update
from sqlalchemy.sql import Select

from app.auth import AuthenticatedUser
from app.persistence import build_metadata_engine
from app.schemas import (
    WorkflowThreadListItem,
    WorkflowThreadListResponse,
    WorkflowThreadResponse,
)
from app.settings import Settings


class WorkflowThreadStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine = build_metadata_engine(self.settings.effective_metadata_database_url)
        self._metadata = MetaData()
        self._threads = Table(
            "workflow_threads_v1",
            self._metadata,
            Column("thread_id", String(120), nullable=False, primary_key=True),
            Column("request_id", String(120), nullable=False),
            Column("status", String(40), nullable=False),
            Column("current_stage", String(60), nullable=False),
            Column("current_step", String(120), nullable=False),
            Column("incident_type", String(40), nullable=True),
            Column("severity", String(20), nullable=True),
            Column("checkpoint_id", String(120), nullable=True),
            Column("input_summary", Text, nullable=True),
            Column("manager_summary", Text, nullable=True),
            Column("engineer_summary", Text, nullable=True),
            Column("approval_status", String(20), nullable=False),
            Column("approval_required", BOOLEAN, nullable=False, default=False),
            Column("actor_subject", String(160), nullable=True),
            Column("actor_email", String(320), nullable=True),
            Column("actor_name", String(160), nullable=True),
            Column("actor_roles", JSON, nullable=False),
            Column("last_snapshot", JSON, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self._metadata.create_all(self._engine)

    def record_thread_snapshot(
        self,
        *,
        thread: WorkflowThreadResponse,
        actor: AuthenticatedUser | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        snapshot = thread.model_dump(mode="json")
        actor_roles = list(actor.roles) if actor is not None else []
        values = {
            "request_id": thread.request_id,
            "status": thread.status,
            "current_stage": thread.current_stage,
            "current_step": thread.current_step,
            "incident_type": thread.incident_type,
            "severity": thread.severity,
            "checkpoint_id": thread.checkpoint_id,
            "input_summary": thread.input_summary,
            "manager_summary": thread.manager_summary,
            "engineer_summary": thread.engineer_summary,
            "approval_status": thread.approval_status,
            "approval_required": thread.approval_required,
            "actor_subject": actor.subject if actor is not None else None,
            "actor_email": actor.email if actor is not None else None,
            "actor_name": actor.name if actor is not None else None,
            "actor_roles": actor_roles,
            "last_snapshot": snapshot,
            "updated_at": now,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(self._threads.c.thread_id).where(self._threads.c.thread_id == thread.thread_id)
            ).first()
            if existing is None:
                connection.execute(
                    insert(self._threads).values(
                        thread_id=thread.thread_id,
                        created_at=now,
                        **values,
                    )
                )
            else:
                connection.execute(
                    update(self._threads)
                    .where(self._threads.c.thread_id == thread.thread_id)
                    .values(**values)
                )

    def list_threads(
        self,
        *,
        limit: int,
        status: str | None = None,
        incident_type: str | None = None,
    ) -> WorkflowThreadListResponse:
        stmt: Select[Any] = select(self._threads).order_by(self._threads.c.updated_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(self._threads.c.status == status)
        if incident_type:
            stmt = stmt.where(self._threads.c.incident_type == incident_type)

        with self._engine.begin() as connection:
            rows = connection.execute(stmt).mappings().all()

        items = [
            WorkflowThreadListItem(
                thread_id=row["thread_id"],
                request_id=row["request_id"],
                status=row["status"],
                current_stage=row["current_stage"],
                current_step=row["current_step"],
                incident_type=row["incident_type"],
                severity=row["severity"],
                checkpoint_id=row["checkpoint_id"],
                approval_required=bool(row["approval_required"]),
                approval_status=row["approval_status"],
                input_summary=row["input_summary"],
                manager_summary=row["manager_summary"],
                engineer_summary=row["engineer_summary"],
                actor_subject=row["actor_subject"],
                actor_email=row["actor_email"],
                actor_name=row["actor_name"],
                actor_roles=_coerce_string_list(row["actor_roles"]),
                created_at=_ensure_utc(row["created_at"]),
                updated_at=_ensure_utc(row["updated_at"]),
            )
            for row in rows
        ]
        return WorkflowThreadListResponse(total_threads=len(items), threads=items)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if cleaned.startswith("["):
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [cleaned]
    return [str(value).strip()] if str(value).strip() else []
