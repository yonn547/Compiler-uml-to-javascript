"""Simulator bundel JavaScript hasil compile.

Satu proses Node dijalankan terus-menerus; perintah dikirim sebagai JSON
satu baris lewat stdin dan balasannya dibaca dari stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DRIVER_PATH = Path(__file__).with_name("simulator_driver.js")


class Simulator:
    def __init__(self, node: str = "node"):
        self.node = node
        self.process: subprocess.Popen[str] | None = None
        self.bundle_path: str | None = None

    @property
    def available(self) -> bool:
        return shutil.which(self.node) is not None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, javascript: str) -> tuple[bool, str]:
        """Jalankan ulang simulator dengan bundle JavaScript diberikan."""
        self.stop()
        if not self.available:
            return False, "Node.js tidak ditemukan di PATH"

        descriptor, path = tempfile.mkstemp(prefix="xtuml_sim_", suffix=".js")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(javascript)
        self.bundle_path = path

        try:
            self.process = subprocess.Popen(
                [self.node, str(DRIVER_PATH), path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self.stop()
            return False, f"Gagal menjalankan Node.js: {exc}"

        reply = self._command({"cmd": "snapshot"})
        if not reply.get("ok"):
            message = str(reply.get("error", "Simulator gagal dimulai"))
            self.stop()
            return False, message
        return True, "Simulator siap"

    def _command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.running or self.process is None:
            return {"ok": False, "error": "Simulator tidak berjalan"}
        try:
            assert self.process.stdin is not None
            assert self.process.stdout is not None
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": f"Komunikasi simulator gagal: {exc}"}
        if not line:
            return {"ok": False, "error": "Simulator berhenti tanpa balasan"}
        try:
            result = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"Balasan simulator tidak valid: {exc}"}
        return result if isinstance(result, dict) else {"ok": False, "error": "Balasan bukan object"}

    def snapshot(self) -> dict[str, Any]:
        return self._command({"cmd": "snapshot"})

    def events(self, instance: str) -> dict[str, Any]:
        return self._command({"cmd": "events", "instance": instance})

    def send(self, instance: str, event: str, payload: Any = None) -> dict[str, Any]:
        return self._command(
            {"cmd": "send", "instance": instance, "event": event, "payload": payload}
        )

    def call(self, instance: str, method: str, args: list[Any] | None = None) -> dict[str, Any]:
        return self._command(
            {"cmd": "call", "instance": instance, "method": method, "args": args or []}
        )

    def reset(self, instance: str) -> dict[str, Any]:
        return self._command({"cmd": "reset", "instance": instance})

    def stop(self) -> None:
        if self.process is not None:
            try:
                if self.process.poll() is None and self.process.stdin is not None:
                    self.process.stdin.write('{"cmd":"stop"}\n')
                    self.process.stdin.flush()
                    self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=2)
            finally:
                for stream in (self.process.stdin, self.process.stdout):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
            self.process = None
        if self.bundle_path:
            try:
                Path(self.bundle_path).unlink(missing_ok=True)
            except OSError:
                pass
            self.bundle_path = None
