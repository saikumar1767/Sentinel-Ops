from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

SQLITE_BUSY_TIMEOUT_MS = 30_000


def build_metadata_engine(database_url: str) -> Engine:
    if is_sqlite_url(database_url):
        sqlite_path = sqlite_database_path(database_url)
        if sqlite_path is not None:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args={
                "check_same_thread": False,
                "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000,
            },
        )
        _install_sqlite_pragmas(engine, enable_wal=sqlite_path is not None)
        return engine

    return create_engine(database_url, future=True, pool_pre_ping=True)


def _install_sqlite_pragmas(engine: Engine, *, enable_wal: bool) -> None:
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
            if enable_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.drivername != "sqlite":
        return None

    database_name = url.database or ""
    if database_name == ":memory:":
        return None
    return Path(database_name)


def database_driver(database_url: str) -> str:
    return make_url(database_url).drivername


def is_sqlite_url(database_url: str) -> bool:
    return database_driver(database_url) == "sqlite"


def normalize_postgres_dsn(database_url: str) -> str:
    url = make_url(database_url)
    driver = url.drivername
    if not driver.startswith("postgresql"):
        return database_url

    url = url.set(drivername="postgresql")
    return url.render_as_string(hide_password=False)
