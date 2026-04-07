from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import WorkflowAuditEvent, WorkflowAuditResponse
from app.settings import Settings


class WorkflowAuditTrail:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.audit_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

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
        )
        with sqlite3.connect(self.settings.audit_db_path) as connection:
            connection.execute(
                """
                INSERT INTO workflow_approval_audit_v2 (
                    event_id,
                    thread_id,
                    recorded_at,
                    action,
                    decision,
                    review_notes,
                    edited_remediation_plan,
                    status_after,
                    request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.thread_id,
                    event.recorded_at.isoformat(),
                    event.action,
                    event.decision,
                    event.review_notes,
                    json.dumps(event.edited_remediation_plan),
                    event.status_after,
                    event.request_id,
                ),
            )
            connection.commit()
        return event

    def thread_audit(self, thread_id: str) -> WorkflowAuditResponse:
        events = self.list_events(thread_id)
        return WorkflowAuditResponse(
            thread_id=thread_id,
            total_events=len(events),
            events=events,
        )

    def list_events(self, thread_id: str) -> list[WorkflowAuditEvent]:
        with sqlite3.connect(self.settings.audit_db_path) as connection:
            rows = self._list_v2_events(connection, thread_id)
            rows.extend(self._list_legacy_events(connection, thread_id))

        events = [self._row_to_event(row) for row in rows]
        events.sort(key=lambda event: (event.recorded_at, event.event_id))
        return events

    def _initialize_schema(self) -> None:
        with sqlite3.connect(self.settings.audit_db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_approval_audit_v2 (
                    event_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    review_notes TEXT,
                    edited_remediation_plan TEXT NOT NULL,
                    status_after TEXT NOT NULL,
                    request_id TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_approval_audit_v2_thread_id
                ON workflow_approval_audit_v2(thread_id, recorded_at)
                """
            )
            connection.commit()

    @staticmethod
    def _list_v2_events(connection: sqlite3.Connection, thread_id: str) -> list[tuple]:
        return connection.execute(
            """
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
            FROM workflow_approval_audit_v2
            WHERE thread_id = ?
            ORDER BY recorded_at ASC, event_id ASC
            """,
            (thread_id,),
        ).fetchall()

    @staticmethod
    def _list_legacy_events(connection: sqlite3.Connection, thread_id: str) -> list[tuple]:
        legacy_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'workflow_approval_audit'
            """
        ).fetchone()
        if legacy_table is None:
            return []

        rows = connection.execute(
            """
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
            FROM workflow_approval_audit
            WHERE thread_id = ?
            ORDER BY recorded_at ASC, event_id ASC
            """,
            (thread_id,),
        ).fetchall()
        return rows

    @staticmethod
    def _row_to_event(row: tuple) -> WorkflowAuditEvent:
        remediation_plan = json.loads(row[6] or "[]")
        return WorkflowAuditEvent(
            event_id=row[0],
            thread_id=row[1],
            recorded_at=datetime.fromisoformat(row[2]),
            action=row[3],  # type: ignore[arg-type]
            decision=row[4],  # type: ignore[arg-type]
            review_notes=row[5],
            edited_remediation_plan=remediation_plan,
            status_after=row[7],  # type: ignore[arg-type]
            request_id=row[8],
        )
