from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools


def build_file_tools() -> FileTools:
    settings = Settings(
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"]
    )
    return FileTools(settings)


def test_resolve_log_path_accepts_project_relative_path() -> None:
    file_tools = build_file_tools()

    resolved = file_tools.resolve_log_path("data/logs/database-current.log")

    assert resolved == (PROJECT_ROOT / "data" / "logs" / "database-current.log").resolve()


def test_resolve_log_path_accepts_root_relative_path() -> None:
    file_tools = build_file_tools()

    resolved = file_tools.resolve_log_path("database-current.log")

    assert resolved == (PROJECT_ROOT / "data" / "logs" / "database-current.log").resolve()


def test_resolve_log_path_rejects_escape_attempt() -> None:
    file_tools = build_file_tools()

    try:
        file_tools.resolve_log_path("../../Windows/System32/drivers/etc/hosts")
    except PermissionError as exc:
        assert "allowed log roots" in str(exc)
    else:
        raise AssertionError("Expected PermissionError for path escape attempt")
