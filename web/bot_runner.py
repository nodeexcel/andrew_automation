"""Manage bot subprocess lifecycle from the web UI."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BotRunner:
    """Thread-safe wrapper around a single bot process."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self.last_output = ""
        self.last_command = ""

    def is_running(self) -> bool:
        with self._lock:
            if self._process is None:
                return False
            code = self._process.poll()
            if code is not None:
                self._process = None
                return False
            return True

    def _run_command(self, args: list[str], *, blocking: bool = False) -> tuple[bool, str]:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False, "Bot is already running. Stop it first."

            cmd = [sys.executable, "main.py", *args]
            self.last_command = " ".join(cmd)

            try:
                if blocking:
                    result = subprocess.run(
                        cmd,
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=600,
                    )
                    output = (result.stdout or "") + (result.stderr or "")
                    self.last_output = output.strip()
                    return result.returncode == 0, self.last_output

                self._process = subprocess.Popen(
                    cmd,
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True, "Bot started."
            except subprocess.TimeoutExpired:
                return False, "Command timed out."
            except Exception as exc:
                return False, str(exc)

    def start(self, config_path: str | None = None) -> tuple[bool, str]:
        args = []
        if config_path:
            args.extend(["--config", config_path])
        return self._run_command(args)

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                return False, "Bot is not running."

            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

            self._process = None
            return True, "Bot stopped."

    def dry_run(self, config_path: str | None = None) -> tuple[bool, str]:
        args = ["--dry-run"]
        if config_path:
            args.extend(["--config", config_path])
        return self._run_command(args, blocking=True)

    def test_run(self, config_path: str | None = None) -> tuple[bool, str]:
        args = ["--test"]
        if config_path:
            args.extend(["--config", config_path])
        return self._run_command(args, blocking=True)


    def check_proxy(self, config_path: str | None = None) -> tuple[bool, str]:
        args = ["--check-proxy"]
        if config_path:
            args.extend(["--config", config_path])
        return self._run_command(args, blocking=True)


runner = BotRunner()
