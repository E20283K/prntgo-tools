"""Configuration and directory paths for PrintHub."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Set

BASE_DIR = Path(__file__).resolve().parent.parent
ENGINES_DIR = BASE_DIR / "engines"
DATA_DIR = Path(os.environ.get("PRINTHUB_DATA_DIR", str(BASE_DIR / "data"))).resolve()

GEARS_JSON_PATH = DATA_DIR / "gears.json"
SELA_TEMPLATES_DIR = DATA_DIR / "sela_templates"
SELA_SET_DIR = DATA_DIR / "sela_set"
FONTS_DIR = DATA_DIR / "fonts"
JOBS_DIR = DATA_DIR / "jobs"

# Claude Code & VectorCraft persistent directories
CLAUDE_HOME_DIR = DATA_DIR / "claude_home"
CLAUDE_WORKSPACE_DIR = DATA_DIR / "claude_workspace"
CLAUDE_SKILLS_DIR = CLAUDE_WORKSPACE_DIR / ".claude" / "skills"
CLAUDE_ASSETS_DIR = CLAUDE_WORKSPACE_DIR / "assets"
CLAUDE_MCP_CONFIG_PATH = CLAUDE_WORKSPACE_DIR / ".mcp.json"
CLAUDE_MD_PATH = CLAUDE_WORKSPACE_DIR / "CLAUDE.md"
CLAUDE_AUTH_ENV_PATH = CLAUDE_HOME_DIR / "auth_env.json"

VECTORCRAFT_WEB_DIR = Path(
    os.environ.get("VECTORCRAFT_WEB_DIR", str(DATA_DIR / "vectorcraft_web"))
).resolve()

# Ensure required directories exist
for _d in (
    DATA_DIR,
    SELA_TEMPLATES_DIR,
    SELA_SET_DIR,
    FONTS_DIR,
    JOBS_DIR,
    CLAUDE_HOME_DIR,
    CLAUDE_WORKSPACE_DIR,
    CLAUDE_SKILLS_DIR,
    CLAUDE_ASSETS_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

# Security & Access Control
WEB_PASSWORD: str = os.environ.get("WEB_PASSWORD", "").strip()
SECRET_KEY: str = os.environ.get("SECRET_KEY", "").strip() or secrets.token_hex(32)
SESSION_COOKIE_NAME: str = "printhub_session"
SESSION_MAX_AGE_SECONDS: int = int(os.environ.get("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600)))

# Telegram Bot
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
PUBLIC_URL: str = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")


def get_allowed_telegram_ids() -> Set[int]:
    """Parse comma-separated ALLOWED_TELEGRAM_IDS env var. Empty set = allow all."""
    raw = os.environ.get("ALLOWED_TELEGRAM_IDS", "").strip()
    if not raw:
        return set()
    ids: Set[int] = set()
    for part in raw.split(","):
        p = part.strip()
        if p.lstrip("-").isdigit():
            ids.add(int(p))
    return ids


# Job retention
JOB_TTL_HOURS: int = int(os.environ.get("JOB_TTL_HOURS", "24"))
JOB_CLEANUP_INTERVAL_MINUTES: int = int(os.environ.get("JOB_CLEANUP_INTERVAL_MINUTES", "30"))
MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "100"))
