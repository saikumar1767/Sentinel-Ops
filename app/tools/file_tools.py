from __future__ import annotations

import re
from pathlib import Path

from app.log_utils import (
    dedupe_preserve_order,
    looks_like_error,
    looks_like_success,
    normalize_log_line,
    truncate_text,
)
from app.schemas import CompareTwoLogsArgs, GrepErrorPatternArgs, ReadLogFileArgs
from app.settings import PROJECT_ROOT, Settings


class FileTools:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list_recent_log_paths(self, limit: int) -> list[str]:
        candidates: list[Path] = []
        for root in self.settings.allowed_log_roots:
            if not root.exists():
                continue
            candidates.extend(path for path in root.rglob("*") if path.is_file())

        recent_paths = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
        return [self.display_path(path) for path in recent_paths[:limit]]

    def read_log_file(self, args: ReadLogFileArgs) -> dict[str, object]:
        path = self.resolve_log_path(args.path)
        indexed_lines = self._load_indexed_lines(path)
        relevant_lines = [line for line in indexed_lines if looks_like_error(line[1])]
        selected_source = relevant_lines or indexed_lines
        selected_lines = [
            self._format_indexed_line(item)
            for item in selected_source[: self.settings.read_log_line_limit]
        ]

        return {
            "ok": True,
            "path": self.display_path(path),
            "selected_lines": selected_lines or ["No non-empty lines found in the file."],
            "truncated": len(selected_source) > self.settings.read_log_line_limit,
            "total_nonempty_lines": len(indexed_lines),
        }

    def grep_error_pattern(self, args: GrepErrorPatternArgs) -> dict[str, object]:
        path = self.resolve_log_path(args.path)
        matcher = re.compile(args.pattern, re.IGNORECASE)
        indexed_lines = self._load_indexed_lines(path)
        matched_lines = [
            self._format_indexed_line((line_number, line))
            for line_number, line in indexed_lines
            if matcher.search(line)
        ]

        return {
            "ok": True,
            "path": self.display_path(path),
            "pattern": args.pattern,
            "matched_lines": matched_lines[: args.max_lines] or ["No matching lines found."],
            "truncated": len(matched_lines) > args.max_lines,
        }

    def compare_two_logs(self, args: CompareTwoLogsArgs) -> dict[str, object]:
        path_a = self.resolve_log_path(args.path_a)
        path_b = self.resolve_log_path(args.path_b)

        indexed_a = self._load_indexed_lines(path_a)
        indexed_b = self._load_indexed_lines(path_b)

        errors_a = self._signature_map(indexed_a, predicate=looks_like_error)
        errors_b = self._signature_map(indexed_b, predicate=looks_like_error)
        success_a = self._signature_map(indexed_a, predicate=looks_like_success)
        success_b = self._signature_map(indexed_b, predicate=looks_like_success)

        new_error_lines = [
            self._format_indexed_line(item)
            for signature, item in errors_b.items()
            if signature not in errors_a
        ]
        missing_success_lines = [
            self._format_indexed_line(item)
            for signature, item in success_a.items()
            if signature not in success_b
        ]

        differences = dedupe_preserve_order(
            [
                *(f"New error in {self.display_path(path_b)}: {line}" for line in new_error_lines),
                *(f"Missing success from {self.display_path(path_b)}: {line}" for line in missing_success_lines),
            ]
        )

        return {
            "ok": True,
            "path_a": self.display_path(path_a),
            "path_b": self.display_path(path_b),
            "new_error_lines": new_error_lines[: self.settings.compare_difference_limit],
            "missing_success_lines": missing_success_lines[
                : self.settings.compare_difference_limit
            ],
            "differences": differences[: self.settings.compare_difference_limit],
            "truncated": len(differences) > self.settings.compare_difference_limit,
        }

    def resolve_log_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path.strip())
        roots = [root.resolve() for root in self.settings.allowed_log_roots]
        if not raw_path.strip():
            raise ValueError("Path is required.")

        if candidate.is_absolute():
            resolved = candidate.resolve()
            if not any(resolved.is_relative_to(root) for root in roots):
                raise PermissionError("Path must stay inside the allowed log roots.")
            if not resolved.is_file():
                raise FileNotFoundError(f"Log file not found: {resolved}")
            return resolved

        # Accept project-relative paths like data/logs/foo.log in addition to
        # root-relative paths like foo.log.
        project_relative = (PROJECT_ROOT / candidate).resolve()
        if project_relative.is_file() and any(
            project_relative.is_relative_to(root) for root in roots
        ):
            return project_relative

        escaped_root = False
        for root in roots:
            resolved = (root / candidate).resolve()
            if not resolved.is_relative_to(root):
                escaped_root = True
                continue
            if resolved.is_file():
                return resolved

        if escaped_root:
            raise PermissionError("Path must stay inside the allowed log roots.")
        raise FileNotFoundError(f"Log file not found under allowed roots: {raw_path}")

    def display_path(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved.is_relative_to(PROJECT_ROOT):
            return resolved.relative_to(PROJECT_ROOT).as_posix()
        return str(resolved)

    def _load_indexed_lines(self, path: Path) -> list[tuple[int, str]]:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines: list[tuple[int, str]] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            cleaned = raw_line.strip()
            if cleaned:
                lines.append(
                    (
                        line_number,
                        truncate_text(cleaned, self.settings.tool_result_max_chars // 4),
                    )
                )
        return lines

    @staticmethod
    def _format_indexed_line(item: tuple[int, str]) -> str:
        line_number, line = item
        return f"{line_number}: {line}"

    @staticmethod
    def _signature_map(
        indexed_lines: list[tuple[int, str]],
        predicate,
    ) -> dict[str, tuple[int, str]]:
        signatures: dict[str, tuple[int, str]] = {}
        for item in indexed_lines:
            _, line = item
            if not predicate(line):
                continue
            signature = normalize_log_line(line).lower()
            signatures.setdefault(signature, item)
        return signatures
