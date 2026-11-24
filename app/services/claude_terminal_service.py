"""Interactive PTY WebSocket Terminal Manager for Claude Code & VectorCraft Workspace."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import struct
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

from app.config import (
    CLAUDE_ASSETS_DIR,
    CLAUDE_HOME_DIR,
    CLAUDE_MCP_CONFIG_PATH,
    CLAUDE_OUTPUTS_DIR,
    CLAUDE_SKILLS_DIR,
    CLAUDE_UPLOADS_DIR,
    CLAUDE_WORKSPACE_DIR,
)
from app.services.claude_design_service import ensure_claude_workspace, load_saved_auth_env

logger = logging.getLogger("printhub.claude_terminal")

MAX_SCROLLBACK_BYTES = 131072  # 128 KB scrollback history
IDLE_TIMEOUT_SECONDS = 30 * 60  # Auto-close PTY if disconnected for 30 minutes


def _build_pty_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(CLAUDE_HOME_DIR)
    env["CLAUDE_CONFIG_DIR"] = str(CLAUDE_HOME_DIR / ".claude")
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["LANG"] = env.get("LANG", "C.UTF-8")
    env.pop("CI", None)
    saved = load_saved_auth_env()
    for k, v in saved.items():
        if v:
            env[k] = v
    return env


class ClaudePtyManager:
    """Manages a persistent PTY session for Claude Code TUI or Bash shell."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.mode: str = "claude"
        self.cols: int = 120
        self.rows: int = 34
        self.scrollback = bytearray()
        self.listeners: Set[Callable[[bytes], None]] = set()
        self.last_active_at: float = time.time()

    def is_running_unlocked(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        with self.lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                else:
                    self.proc.terminate()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
        self.proc = None
        self.master_fd = None
        self.scrollback.clear()

    def ensure_started(self, mode: str = "claude", cols: int = 120, rows: int = 34, force_restart: bool = False) -> None:
        ensure_claude_workspace()
        for d in (CLAUDE_ASSETS_DIR, CLAUDE_SKILLS_DIR, CLAUDE_UPLOADS_DIR, CLAUDE_OUTPUTS_DIR):
            d.mkdir(parents=True, exist_ok=True)

        with self.lock:
            if force_restart or (self.is_running_unlocked() and self.mode != mode):
                self._stop_unlocked()

            if self.is_running_unlocked():
                self.last_active_at = time.time()
                return

            self.mode = mode
            self.cols = max(40, cols)
            self.rows = max(12, rows)
            self.scrollback.clear()
            self.last_active_at = time.time()

            env = _build_pty_env()
            claude_bin = shutil.which("claude")
            bash_bin = shutil.which("bash") or shutil.which("sh") or "/bin/sh"

            if mode == "claude" and claude_bin:
                cmd = [
                    claude_bin,
                    "--mcp-config",
                    str(CLAUDE_MCP_CONFIG_PATH),
                    "--allowedTools",
                    "mcp__vectorcraft__*,Read,Write,Edit,MultiEdit,Glob,Grep,LS,Bash",
                ]
            elif os.name == "posix":
                cmd = [bash_bin]
            else:
                cmd = [claude_bin] if (mode == "claude" and claude_bin) else ["cmd.exe"]

            if os.name == "posix":
                import fcntl
                import pty
                import termios

                master_fd, slave_fd = pty.openpty()
                winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

                proc = subprocess.Popen(
                    cmd,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=str(CLAUDE_WORKSPACE_DIR),
                    env=env,
                    preexec_fn=os.setsid,
                    close_fds=True,
                )
                os.close(slave_fd)
                self.proc = proc
                self.master_fd = master_fd

                if mode == "claude" and not claude_bin:
                    banner = (
                        "\r\n\x1b[1;33m[PrintGoo Terminal]\x1b[0m 'claude' CLI topilmadi, bash shell ishga tushirildi.\r\n"
                    ).encode("utf-8")
                    self._append_output(banner)

                threading.Thread(
                    target=self._posix_reader_loop,
                    args=(master_fd, proc),
                    daemon=True,
                ).start()
            else:
                # Windows local dev fallback
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(CLAUDE_WORKSPACE_DIR),
                    env=env,
                )
                self.proc = proc
                self.master_fd = None
                banner = (
                    f"\r\n\x1b[1;36m[PrintGoo Terminal — {mode.upper()}]\x1b[0m Ishchi papka: {CLAUDE_WORKSPACE_DIR}\r\n"
                ).encode("utf-8")
                self._append_output(banner)
                threading.Thread(
                    target=self._win_reader_loop,
                    args=(proc,),
                    daemon=True,
                ).start()

    def _append_output(self, data: bytes) -> None:
        if not data:
            return
        with self.lock:
            self.scrollback.extend(data)
            if len(self.scrollback) > MAX_SCROLLBACK_BYTES:
                del self.scrollback[: len(self.scrollback) - MAX_SCROLLBACK_BYTES]
            callbacks = list(self.listeners)
        for cb in callbacks:
            try:
                cb(data)
            except Exception:
                pass

    def _posix_reader_loop(self, fd: int, proc: subprocess.Popen) -> None:
        while True:
            try:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                self._append_output(chunk)
            except OSError:
                break
        rc = proc.wait()
        exit_msg = (
            f"\r\n\x1b[1;33m[Jarayon yakunlandi (kod: {rc}). Qayta boshlash uchun Enter yoki 'Qayta ishga tushirish' tugmasini bosing]\x1b[0m\r\n"
        ).encode("utf-8")
        self._append_output(exit_msg)

    def _win_reader_loop(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(1024)
            if not chunk:
                break
            self._append_output(chunk)
        rc = proc.wait()
        exit_msg = f"\r\n\x1b[1;33m[Jarayon yakunlandi (kod: {rc})]\x1b[0m\r\n".encode("utf-8")
        self._append_output(exit_msg)

    def write_input(self, data: bytes) -> None:
        with self.lock:
            self.last_active_at = time.time()
            if not self.is_running_unlocked():
                # Auto-restart if process exited and user pressed a key
                mode = self.mode
                cols, rows = self.cols, self.rows
            else:
                mode = ""
                cols, rows = self.cols, self.rows

        if mode:
            self.ensure_started(mode=mode, cols=cols, rows=rows, force_restart=True)
            return

        with self.lock:
            fd = self.master_fd
            proc = self.proc
            if fd is not None:
                try:
                    os.write(fd, data)
                except OSError:
                    pass
            elif proc and proc.stdin:
                try:
                    proc.stdin.write(data)
                    proc.stdin.flush()
                except Exception:
                    pass

    def resize(self, cols: int, rows: int) -> None:
        c = max(40, min(cols, 400))
        r = max(10, min(rows, 200))
        with self.lock:
            self.cols = c
            self.rows = r
            fd = self.master_fd
            proc = self.proc
            if os.name == "posix" and fd is not None:
                try:
                    import fcntl
                    import termios

                    winsize = struct.pack("HHHH", r, c, 0, 0)
                    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
                    if proc and proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGWINCH)
                except Exception:
                    pass

    def get_scrollback(self) -> bytes:
        with self.lock:
            return bytes(self.scrollback)

    def add_listener(self, cb: Callable[[bytes], None]) -> None:
        with self.lock:
            self.listeners.add(cb)
            self.last_active_at = time.time()

    def remove_listener(self, cb: Callable[[bytes], None]) -> None:
        with self.lock:
            self.listeners.discard(cb)
            self.last_active_at = time.time()

    def check_idle_cleanup(self) -> None:
        with self.lock:
            if not self.listeners and self.is_running_unlocked():
                if (time.time() - self.last_active_at) > IDLE_TIMEOUT_SECONDS:
                    logger.info("Claude PTY terminal 30 daqiqa harakatsizlikdan so'ng yopildi.")
                    self._stop_unlocked()


PTY_MANAGER = ClaudePtyManager()
