from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from app.log_utils import truncate_text
from app.schemas import (
    CompareTwoLogsArgs,
    GrepErrorPatternArgs,
    ListRecentIncidentsArgs,
    LoadIncidentTemplateArgs,
    ReadLogFileArgs,
)
from app.settings import Settings
from app.tools.file_tools import FileTools
from app.tools.incident_tools import IncidentTools


class ToolExecutionRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    ok: bool
    cached: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolRegistry:
    def __init__(self, file_tools: FileTools, incident_tools: IncidentTools, settings: Settings):
        self.file_tools = file_tools
        self.incident_tools = incident_tools
        self.settings = settings
        self._tools: dict[str, Callable[..., str]] = {
            "read_log_file": self.read_log_file,
            "grep_error_pattern": self.grep_error_pattern,
            "compare_two_logs": self.compare_two_logs,
            "load_incident_template": self.load_incident_template,
            "list_recent_incidents": self.list_recent_incidents,
        }

    @property
    def tools(self) -> list[Callable[..., str]]:
        return list(self._tools.values())

    def execute_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> tuple[str, ToolExecutionRecord]:
        if tool_name not in self._tools:
            payload = {
                "ok": False,
                "tool": tool_name,
                "error": "Unknown tool requested.",
            }
            return json.dumps(payload), ToolExecutionRecord(
                name=tool_name,
                arguments=arguments,
                ok=False,
                payload=payload,
            )

        normalized_arguments = self._normalize_arguments(tool_name, arguments)
        try:
            raw_result = self._tools[tool_name](**normalized_arguments)
            payload = json.loads(raw_result)
        except TypeError as exc:
            payload = {
                "ok": False,
                "tool": tool_name,
                "error": f"Invalid tool arguments: {exc}",
            }
            raw_result = json.dumps(payload)

        return raw_result, ToolExecutionRecord(
            name=tool_name,
            arguments=normalized_arguments,
            ok=bool(payload.get("ok")),
            payload=payload,
        )

    def read_log_file(self, path: str) -> str:
        """Read one local log file and return only the first relevant lines.

        Args:
          path: Relative log path inside the allowed local log folders.
        """
        return self._run_tool(
            name="read_log_file",
            validator=ReadLogFileArgs,
            handler=self.file_tools.read_log_file,
            arguments={"path": path},
        )

    def grep_error_pattern(self, path: str, pattern: str, max_lines: int) -> str:
        """Search one local log file for a keyword or regex pattern.

        Args:
          path: Relative log path inside the allowed local log folders.
          pattern: A case-insensitive keyword or regex such as ERROR, timeout, refused, exception, or failed.
          max_lines: Maximum number of matching lines to return.
        """
        return self._run_tool(
            name="grep_error_pattern",
            validator=GrepErrorPatternArgs,
            handler=self.file_tools.grep_error_pattern,
            arguments={"path": path, "pattern": pattern, "max_lines": max_lines},
        )

    def compare_two_logs(self, path_a: str, path_b: str) -> str:
        """Compare two local log files and highlight important differences.

        Args:
          path_a: Baseline or previous log path inside the allowed local log folders.
          path_b: Current log path inside the allowed local log folders.
        """
        return self._run_tool(
            name="compare_two_logs",
            validator=CompareTwoLogsArgs,
            handler=self.file_tools.compare_two_logs,
            arguments={"path_a": path_a, "path_b": path_b},
        )

    def load_incident_template(self, incident_type: str) -> str:
        """Load a local incident checklist for a known incident type.

        Args:
          incident_type: One of api, authentication, configuration, database, deployment, disk, memory, network, performance, queue, security, or service.
        """
        return self._run_tool(
            name="load_incident_template",
            validator=LoadIncidentTemplateArgs,
            handler=self.incident_tools.load_incident_template,
            arguments={"incident_type": incident_type},
        )

    def list_recent_incidents(self, limit: int) -> str:
        """List recent saved incident summaries from local storage.

        Args:
          limit: Maximum number of saved incidents to return.
        """
        return self._run_tool(
            name="list_recent_incidents",
            validator=ListRecentIncidentsArgs,
            handler=self.incident_tools.list_recent_incidents,
            arguments={"limit": limit},
        )

    def _run_tool(
        self,
        *,
        name: str,
        validator,
        handler: Callable[[Any], dict[str, object]],
        arguments: dict[str, Any],
    ) -> str:
        try:
            validated_args = validator.model_validate(arguments)
            payload = handler(validated_args)
            result = {"tool": name, **payload}
        except (ValidationError, OSError, PermissionError, ValueError, re.error) as exc:
            result = {
                "ok": False,
                "tool": name,
                "error": str(exc),
            }

        serialized = json.dumps(result, ensure_ascii=True)
        if len(serialized) <= self.settings.tool_result_max_chars:
            return serialized

        truncated_result = {
            **result,
            "truncated": True,
            "preview": truncate_text(serialized, self.settings.tool_result_max_chars - 32),
        }
        return json.dumps(truncated_result, ensure_ascii=True)

    def _normalize_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(arguments)

        if tool_name == "read_log_file":
            return self._rename_keys(
                normalized,
                {
                    "file_path": "path",
                    "log_path": "path",
                },
            )

        if tool_name == "grep_error_pattern":
            normalized = self._rename_keys(
                normalized,
                {
                    "file_path": "path",
                    "log_path": "path",
                    "query": "pattern",
                    "keyword": "pattern",
                    "limit": "max_lines",
                },
            )
            normalized.setdefault("max_lines", self.settings.grep_max_lines_default)
            return normalized

        if tool_name == "compare_two_logs":
            normalized = self._rename_keys(
                normalized,
                {
                    "log1_path": "path_a",
                    "log2_path": "path_b",
                    "path1": "path_a",
                    "path2": "path_b",
                    "baseline_path": "path_a",
                    "previous_path": "path_a",
                    "old_path": "path_a",
                    "current_path": "path_b",
                    "latest_path": "path_b",
                    "new_path": "path_b",
                },
            )
            return normalized

        if tool_name == "load_incident_template":
            return self._rename_keys(
                normalized,
                {
                    "type": "incident_type",
                    "template_type": "incident_type",
                },
            )

        if tool_name == "list_recent_incidents":
            normalized = self._rename_keys(
                normalized,
                {
                    "max_items": "limit",
                    "count": "limit",
                },
            )
            normalized.setdefault("limit", 3)
            return normalized

        return normalized

    @staticmethod
    def _rename_keys(arguments: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
        normalized = dict(arguments)
        for source_key, target_key in aliases.items():
            if source_key in normalized and target_key not in normalized:
                normalized[target_key] = normalized.pop(source_key)
        return normalized
