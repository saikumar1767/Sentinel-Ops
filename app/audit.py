from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, insert, select

from app.auth import AuthenticatedUser
from app.persistence import build_metadata_engine, sqlite_database_path
from app.schemas import WorkflowAuditEvent, WorkflowAuditResponse
from app.settings import Settings


class WorkflowAuditTrail:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine = build_metadata_engine(self.settings.effective_metadata_database_url)
        self._metadata = MetaData()
        self._events = Table(
            "workflow_approval_audit_v3",
            self._metadata,
            Column("event_id", String(120), nullable=False, primary_key=True),
            Column("thread_id", String(120), nullable=False, index=True),
            Column("recorded_at", DateTime(timezone=True), nullable=False, index=True),
            Column("action", String(40), nullable=False),
            Column("decision", String(40), nullable=False),
            Column("review_notes", Text, nullable=True),
            Column("edited_remediation_plan", JSON, nullable=False),
            Column("status_after", String(40), nullable=False),
            Column("request_id", String(120), nullable=True),
            Column("actor_subject", String(160), nullable=True),
            Column("actor_email", String(320), nullable=True),
            Column("actor_name", String(160), nullable=True),
            Column("actor_roles", JSON, nullable=False),
        )
        self._metadata.create_all(self._engine)

    def record_event(
        self,
        *,
        thread_id: str,
        action: str,
        decision: str,
        review_notes: str | None,
        edited_remediation_plan: list[str],
        status_after: str,
        request_id: str | None = None,
        actor: AuthenticatedUser | None = None,
    ) -> WorkflowAuditEvent:
        event = WorkflowAuditEvent(
            event_id=f"audit-{uuid4().hex}",
            thread_id=thread_id,
            recorded_at=datetime.now(timezone.utc),
            action=action,  # type: ignore[arg-type]
            decision=decision,  # type: ignore[arg-type]
            review_notes=review_notes,
            edited_remediation_plan=edited_remediation_plan,
            status_after=status_after,  # type: ignore[arg-type]
            request_id=request_id,
            actor_subject=actor.subject if actor is not None else None,
            actor_email=actor.email if actor is not None else None,
            actor_name=actor.name if actor is not None else None,
            actor_roles=list(actor.roles) if actor is not None else [],
        )
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._events).values(
                    event_id=event.event_id,
                    thread_id=event.thread_id,
                    recorded_at=event.recorded_at,
                    action=event.action,
                    decision=event.decision,
                    review_notes=event.review_notes,
                    edited_remediation_plan=event.edited_remediation_plan,
                    status_after=event.status_after,
                    request_id=event.request_id,
                    actor_subject=event.actor_subject,
                    actor_email=event.actor_email,
                    actor_name=event.actor_name,
                    actor_roles=event.actor_roles,
                )
            )
        return event

    def thread_audit(self, thread_id: str) -> WorkflowAuditResponse:
        events = self.list_events(thread_id)
        return WorkflowAuditResponse(thread_id=thread_id, total_events=len(events), events=events)

    def list_events(self, thread_id: str) -> list[WorkflowAuditEvent]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                select(self._events)
                .where(self._events.c.thread_id == thread_id)
                .order_by(self._events.c.recorded_at.asc(), self._events.c.event_id.asc())
            ).mappings().all()

        events = [self._mapping_to_event(row) for row in rows]
        events.extend(self._list_legacy_events(thread_id))
        events.sort(key=lambda event: (event.recorded_at, event.event_id))
        return events

    def _list_legacy_events(self, thread_id: str) -> list[WorkflowAuditEvent]:
        sqlite_path = sqlite_database_path(self.settings.effective_metadata_database_url)
        if sqlite_path is None or not sqlite_path.exists():
            return []

        with sqlite3.connect(sqlite_path) as connection:
            rows = self._fetch_legacy_rows(connection, thread_id, "workflow_approval_audit_v2")
            rows.extend(self._fetch_legacy_rows(connection, thread_id, "workflow_approval_audit"))
        return [self._legacy_row_to_event(row) for row in rows]

    @staticmethod
    def _fetch_legacy_rows(
        connection: sqlite3.Connection,
        thread_id: str,
        table_name: str,
    ) -> list[tuple]:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if table is None:
            return []

        return connection.execute(
            f"""
            SELECT
                event_id,
                thread_id,
                recorded_at,
                action,
                decision,
                review_notes,
                edited_remediation_plan,
                status_after,
                request_id
            FROM {table_name}
            WHERE thread_id = ?
            ORDER BY recorded_at ASC, event_id ASC
            """,
            (thread_id,),
        ).fetchall()

    @staticmethod
    def _mapping_to_event(row: dict) -> WorkflowAuditEvent:
        return WorkflowAuditEvent(
            event_id=str(row["event_id"]),
            thread_id=str(row["thread_id"]),
            recorded_at=_coerce_datetime(row["recorded_at"]),
            action=str(row["action"]),  # type: ignore[arg-type]
            decision=str(row["decision"]),  # type: ignore[arg-type]
            review_notes=row["review_notes"],
            edited_remediation_plan=_coerce_string_list(row["edited_remediation_plan"]),
            status_after=str(row["status_after"]),  # type: ignore[arg-type]
            request_id=row["request_id"],
            actor_subject=row.get("actor_subject"),
            actor_email=row.get("actor_email"),
            actor_name=row.get("actor_name"),
            actor_roles=_coerce_string_list(row.get("actor_roles")),
        )

    @staticmethod
    def _legacy_row_to_event(row: tuple) -> WorkflowAuditEvent:
        remediation_plan = json.loads(row[6] or "[]")
        return WorkflowAuditEvent(
            event_id=row[0],
            thread_id=row[1],
            recorded_at=_coerce_datetime(row[2]),
            action=row[3],  # type: ignore[arg-type]
            decision=row[4],  # type: ignore[arg-type]
            review_notes=row[5],
            edited_remediation_plan=remediation_plan,
            status_after=row[7],  # type: ignore[arg-type]
            request_id=row[8],
            actor_roles=[],
        )


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
