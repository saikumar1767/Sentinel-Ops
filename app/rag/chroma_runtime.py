from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from textwrap import dedent

import requests

from app.settings import Settings

_START_LOCK = threading.Lock()


class ChromaRuntimeManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_ready(self) -> None:
        if self._heartbeat_ok():
            return

        if not self.settings.chroma_auto_start:
            raise RuntimeError(self._unavailable_message())

        with _START_LOCK:
            if self._heartbeat_ok():
                return
            self._start_server()
            self._wait_for_heartbeat()

    @property
    def heartbeat_url(self) -> str:
        return self._heartbeat_url()

    def is_ready(self) -> bool:
        return self._heartbeat_ok()

    def _heartbeat_ok(self) -> bool:
        try:
            response = requests.get(self._heartbeat_url(), timeout=1.5)
            return response.ok
        except requests.RequestException:
            return False

    def _start_server(self) -> None:
        mode = self.settings.chroma_client_mode
        if mode == "http":
            self._start_http_server()
            return
        raise RuntimeError(
            "Automatic startup is only supported for chroma_client_mode=http. "
            "Switch to HTTP mode or start the persistent client path manually."
        )

    def _start_http_server(self) -> None:
        local_error: Exception | None = None
        try:
            self._start_local_http_server()
            return
        except Exception as exc:
            local_error = exc

        if os.name == "nt":
            try:
                self._start_wsl_http_server()
                return
            except Exception as exc:
                raise RuntimeError(f"{self._unavailable_message()} Local start error: {local_error}. WSL start error: {exc}.") from exc

        raise RuntimeError(f"{self._unavailable_message()} Local start error: {local_error}.")

    def _start_local_http_server(self) -> None:
        chroma_command = shutil.which("chroma")
        if chroma_command:
            command = [
                chroma_command,
                "run",
                "--path",
                str(self.settings.chroma_path),
                "--host",
                self.settings.chroma_host,
                "--port",
                str(self.settings.chroma_port),
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "chromadb.cli.cli",
                "run",
                "--path",
                str(self.settings.chroma_path),
                "--host",
                self.settings.chroma_host,
                "--port",
                str(self.settings.chroma_port),
            ]

        log_path = self._log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log_handle:
            kwargs: dict[str, object] = {
                "stdin": subprocess.DEVNULL,
                "stdout": log_handle,
                "stderr": subprocess.STDOUT,
            }
            if os.name == "nt":
                kwargs["creationflags"] = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                )
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(command, **kwargs)
        time.sleep(2)

    def _start_wsl_http_server(self) -> None:
        self._assert_wsl_chroma_installed()
        command = dedent(
            f"""
            mkdir -p {self.settings.chroma_wsl_data_dir} $HOME/.sentinelops/logs
            setsid {self.settings.chroma_wsl_binary} run \
              --path {self.settings.chroma_wsl_data_dir} \
              --host 0.0.0.0 \
              --port {self.settings.chroma_port} \
              > $HOME/.sentinelops/logs/chroma.log 2>&1 < /dev/null &
            sleep 3
            """
        ).strip()

        result = subprocess.run(
            [
                "wsl.exe",
                "-d",
                self.settings.chroma_wsl_distro,
                "--",
                "bash",
                "-lc",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeError(self._unavailable_message())

    def _assert_wsl_chroma_installed(self) -> None:
        probe = subprocess.run(
            [
                "wsl.exe",
                "-d",
                self.settings.chroma_wsl_distro,
                "--",
                "bash",
                "-lc",
                f"test -x {self.settings.chroma_wsl_binary}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return

        raise RuntimeError(
            "Chroma is not installed in WSL. Run the repo helper script to install it: "
            "scripts/setup_chroma_wsl.ps1"
        )

    def _wait_for_heartbeat(self) -> None:
        deadline = time.time() + self.settings.chroma_start_timeout_seconds
        while time.time() < deadline:
            if self._heartbeat_ok():
                return
            time.sleep(1)
        raise RuntimeError(self._unavailable_message())

    def _heartbeat_url(self) -> str:
        scheme = "https" if self.settings.chroma_ssl else "http"
        return f"{scheme}://{self.settings.chroma_host}:{self.settings.chroma_port}/api/v2/heartbeat"

    def _log_path(self) -> Path:
        runtime_dir = self.settings.chroma_path.parent
        return runtime_dir / "logs" / "chroma.log"

    def _unavailable_message(self) -> str:
        return (
            "Chroma is not reachable at "
            f"{self.settings.chroma_host}:{self.settings.chroma_port}. "
            "Start a local Chroma server with `chroma run --path <dir>` or enable `chroma_auto_start` "
            "in `.sentinelops/project.toml`. On Windows, WSL remains a valid fallback via "
            "`scripts/start_chroma_wsl.ps1`."
        )
