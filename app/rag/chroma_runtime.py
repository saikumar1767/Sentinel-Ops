from __future__ import annotations

import os
import subprocess
import threading
import time
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
        if os.name != "nt":
            raise RuntimeError(
                "Automatic Chroma startup is currently configured for Windows + WSL. "
                "Start the Chroma server manually or use the simple backend."
            )

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

    def _unavailable_message(self) -> str:
        return (
            "Chroma is not reachable at "
            f"{self.settings.chroma_host}:{self.settings.chroma_port}. "
            "On this Windows machine, the reliable setup is WSL-hosted Chroma over HTTP. "
            "Start it with scripts/start_chroma_wsl.ps1 and inspect "
            "$HOME/.sentinelops/logs/chroma.log inside WSL if startup fails."
        )
