from app.settings import PROJECT_ROOT, Settings
from app.tools.file_tools import FileTools


def build_file_tools() -> FileTools:
    settings = Settings(
        workspace_root=PROJECT_ROOT,
        allowed_log_roots=[PROJECT_ROOT / "samples", PROJECT_ROOT / "data" / "logs"],
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


def test_display_path_uses_workspace_root(tmp_path) -> None:
    workspace_root = tmp_path / "checkout-service"
    log_dir = workspace_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    log_path.write_text("error\n", encoding="utf-8")

    settings = Settings(
        workspace_root=workspace_root,
        allowed_log_roots=[log_dir],
    )
    file_tools = FileTools(settings)

    assert file_tools.display_path(log_path) == "logs/app.log"
