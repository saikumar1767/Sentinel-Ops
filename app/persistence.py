from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def build_metadata_engine(database_url: str) -> Engine:
    sqlite_path = sqlite_database_path(database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, future=True, pool_pre_ping=True)


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
