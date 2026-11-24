"""Claude Code + VectorCraft MCP + Skills & Assets Service for PrintHub."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from app.config import (
    CLAUDE_ASSETS_DIR,
    CLAUDE_AUTH_ENV_PATH,
    CLAUDE_HOME_DIR,
    CLAUDE_MD_PATH,
    CLAUDE_MCP_CONFIG_PATH,
    CLAUDE_SKILLS_DIR,
    CLAUDE_WORKSPACE_DIR,
    VECTORCRAFT_WEB_DIR,
)
from app.jobs import bundle_job_outputs_zip, create_job, get_job_dir, get_job_output_file, save_job_meta

logger = logging.getLogger("printhub.claude_design")

PT_PER_MM = 72.0 / 25.4
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
URL_RE = re.compile(r"https://[^\s\"'<>]+")

DEFAULT_MCP_CONFIG: Dict[str, Any] = {
    "mcpServers": {
        "vectorcraft": {
            "command": "vectorcraft-cli",
            "args": ["mcp", "--headless"],
        }
    }
}

DEFAULT_CLAUDE_MD = """# PrintGoo AI Design Studio (Claude Code + VectorCraft MCP)

Siz **PrintGoo (PrintHub)** poligrafiya va etiketka platformasining bosh dizayner-agentisiz.
Sizning asosiy vazifangiz — foydalanuvchi so'roviga asosan `.claude/skills/` ichidagi maxsus skillar, `assets/` papkasidagi doimiy fayllar hamda **VectorCraft MCP (`mcp__vectorcraft__*`)** vositalaridan foydalanib professional vektorli dizaynlar yaratishdir.

## Ishchi muhit tuzilishi
- `.claude/skills/` — Maxsus dizayn skillari (`SKILL.md` va yordamchi fayllar/shablonlar). Vazifani bajarishdan oldin tegishli skill qoidalarini o'qing.
- `assets/` — Serverda doimiy saqlanadigan fayllar (logotiplar, shablonlar, `.vectorcraft`, `.svg`, `.pdf`, shriftlar).
- `.mcp.json` — `vectorcraft` MCP serveri (`vectorcraft-cli mcp --headless`).

## Majburiy Natija Qoidasi
Har bir dizayn buyurtmasi yakunida natijani ko'rsatilgan `outputs/` papkasiga **ikkita formatda** saqlashingiz SHART:
1. **`.vectorcraft`** — VectorCraft'ning standart tahrirlanadigan fayli (`save_file` yoki `export` tool orqali `format: "vectorcraft"`).
2. **`.pdf`** — Bosmaga tayyor vektorli PDF fayl (`export` tool orqali `format: "pdf"` yoki `vectorcraft-cli run --in <file>.vectorcraft --export <file>.pdf`).

## O'lcham va Birliklar
- VectorCraft koordinatalari **points (pt)** da ishlaydi (`1 mm = 2.83464567 pt`, `72 pt = 25.4 mm`).
- `run_command` orqali `addon.units.convert` (`{"value": "60mm"}`) chaqirib yoki `mm * 72 / 25.4` formulasi bilan aniq pt qiymatini hisoblang.
"""

DEFAULT_SKILL_VECTORCRAFT = """---
name: vectorcraft-master
description: VectorCraft MCP serveri orqali professional vektorli dizayn, shakl, tipografika, rang va eksport amallarini bajarish bo'yicha to'liq qo'llanma.
---

# VectorCraft MCP Master Skill

Ushbu skill VectorCraft MCP (`mcp__vectorcraft__*`) tool'lari orqali noldan murakkab vektorli dizaynlar yaratish va tahrirlash qoidalarini belgilaydi.

## 1. Hujjat yaratish va Artboard o'lchami
- Yangi hujjat ochish: `run_command` -> `{"command": "file.new", "params": {"width": <width_pt>, "height": <height_pt>, "title": "<name>"}}`
  - Millimetrni pointga o'tkazish: `pt = mm * 72.0 / 25.4` (masalan: `60 mm = 170.0787 pt`, `40 mm = 113.3858 pt`, `100 mm = 283.4646 pt`).
- Mavjud `.vectorcraft`, `.svg`, `.pdf`, `.ai` yoki `.cdr` faylni ochish:
  `open_file` -> `{"path": "/to'liq/yo'l/fayl.vectorcraft"}`

## 2. Shakllar va Konturlar chizish
- **`draw_shape`**:
  - To'rtburchak: `{"shape": "rectangle", "x": 0, "y": 0, "width": 170.08, "height": 113.39, "radius": 6, "fill": "#1e293b", "stroke": "none", "name": "Background"}`
  - Aylana/Ellips: `{"shape": "ellipse", "x": 20, "y": 20, "width": 50, "height": 50, "fill": "#38bdf8", "stroke": "none"}`
  - Ko'pburchak: `{"shape": "polygon", "cx": 85, "cy": 56, "radius": 35, "sides": 6, "fill": "#f59e0b"}`
  - Yulduz: `{"shape": "star", "cx": 85, "cy": 56, "radius1": 30, "radius2": 15, "points": 5, "fill": "#eab308"}`
  - Chiziq: `{"shape": "line", "x1": 10, "y1": 50, "x2": 160, "y2": 50, "stroke": "#94a3b8", "strokeWidth": 1.5}`
- **`draw_path`**:
  - SVG path (`d`) yoki nuqtalar (`points`) orqali murakkab Bézier egri chiziqlari:
    `{"d": "M 10 10 C 40 0, 60 20, 90 10 L 90 50 Z", "fill": "#e11d48", "stroke": "none", "name": "Wave"}`

## 3. Matn va Tipografika (`add_text`)
- Nuqtaviy matn:
  `{"text": "PREMIUM PRODUCT", "x": 85, "y": 35, "size": 14, "font": "Liberation Sans", "color": "#ffffff", "justify": "center"}`
- Hududiy (Area) matn:
  `{"text": "Tarkibi va qo'shimcha ma'lumotlar...", "x": 12, "y": 65, "width": 146, "height": 36, "size": 7, "color": "#cbd5e1", "justify": "left"}`

## 4. Ranglar, Gradientlar va Effektlar
- `fill` va `stroke` qiymatlari:
  - Hex: `"#rrggbb"` (alfa kanalsiz 6 xonali hex) yoki `"none"`
  - CMYK (poligrafiya uchun): `{"c": 0, "m": 85, "y": 95, "k": 0}`
- `command_batch` orqali bir nechta chizish qadamlarini bitta chaqiruvda tez bajarish mumkin.

## 5. Tekshirish va Saqlash (MAJBURIY)
1. Hujjat daraxtini tekshirish: `inspect_document` (`{}`)
2. Standart `.vectorcraft` formatida saqlash:
   `save_file` -> `{"path": "<outputs_dir>/<name>.vectorcraft", "preview": true}`
3. Bosma `.pdf` formatida eksport qilish:
   `export` -> `{"path": "<outputs_dir>/<name>.pdf", "format": "pdf"}`
"""

DEFAULT_SKILL_PRINT_LABEL = """---
name: label-packaging-design
description: Poligrafiya etiketkalari, stikerlar, birkalar (hang-tag) va qadoqlash dizaynlarini bosma standartlar asosida tayyorlash qoidalari.
---

# Poligrafiya Etiketka va Qadoqlash Dizayni

Etiketka, birka (hang-tag) yoki qadoq dizaynini yaratishda quyidagi poligrafiya qoidalariga amal qiling:

## 1. Kompozitsiya va Xavfsiz Hudud (Safe Zone)
- Kesish chizig'idan (Artboard chetidan) kamida **2.5 mm – 3 mm (`~7-8.5 pt`)** ichkarida matn va logotiplarni joylashtiring (`Safe Margin`).
- Orqa fon (background) artboardni to'liq qoplashi kerak.
- Agar pichoq konturi (dieline / cut contour) so'ralsa, uni alohida `Dieline` nomli obyekt sifatida `fill: "none"`, `stroke: "#ec008c"`, `strokeWidth: 0.75` bilan chizing.

## 2. Vizual Ierarxiya va Shriftlar
- **Brend / Sarlavha:** Eng yuqori kontrastli va markaziy o'rinda (12 pt – 28 pt, o'lchamga qarab).
- **Sub-sarlavha / Mahsulot turi:** Dekorativ chiziq, badge yoki plashka ichida (7 pt – 11 pt).
- **Texnik ma'lumotlar (vazn, artikul, tarkib, shtrix-kod hududi):** Pastki qismda tartibli blok ko'rinishida (5.5 pt – 8 pt).
- Serverda mavjud kafolatlangan shriftlar: `Liberation Sans`, `Liberation Serif`, `Liberation Mono`, `DejaVu Sans`, shuningdek `assets/` yoki `/app/data/fonts/` ichidagi maxsus shriftlar.

## 3. Dekorativ Vektor Elementlar
- Oddiy bo'sh to'rtburchak bilan cheklanmang: ramkalar, burchak ornamentlari, badge/yorliq shakllari (`star`, `polygon`, `draw_path`), kontrastli fon qatlamlari va chiziqli separatorlardan foydalaning.
"""


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return s or "custom-skill"


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def ensure_claude_workspace() -> None:
    """Seed default .mcp.json, CLAUDE.md, and built-in skills if missing."""
    CLAUDE_HOME_DIR.mkdir(parents=True, exist_ok=True)
    CLAUDE_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    CLAUDE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    CLAUDE_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    if not CLAUDE_MCP_CONFIG_PATH.is_file():
        CLAUDE_MCP_CONFIG_PATH.write_text(
            json.dumps(DEFAULT_MCP_CONFIG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if not CLAUDE_MD_PATH.is_file():
        CLAUDE_MD_PATH.write_text(DEFAULT_CLAUDE_MD.strip() + "\n", encoding="utf-8")

    # Seed default skills if no skills exist yet
    existing_skills = [p for p in CLAUDE_SKILLS_DIR.iterdir() if p.is_dir()]
    if not existing_skills:
        vc_dir = CLAUDE_SKILLS_DIR / "vectorcraft-master"
        vc_dir.mkdir(parents=True, exist_ok=True)
        (vc_dir / "SKILL.md").write_text(DEFAULT_SKILL_VECTORCRAFT.strip() + "\n", encoding="utf-8")

        lbl_dir = CLAUDE_SKILLS_DIR / "label-packaging-design"
        lbl_dir.mkdir(parents=True, exist_ok=True)
        (lbl_dir / "SKILL.md").write_text(DEFAULT_SKILL_PRINT_LABEL.strip() + "\n", encoding="utf-8")


# Initialize workspace on module load
ensure_claude_workspace()


# ---------------------------------------------------------------------------
# Environment & Authentication Helpers
# ---------------------------------------------------------------------------
def load_saved_auth_env() -> Dict[str, str]:
    if not CLAUDE_AUTH_ENV_PATH.is_file():
        return {}
    try:
        data = json.loads(CLAUDE_AUTH_ENV_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def save_auth_env(oauth_token: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
    current = load_saved_auth_env()
    if oauth_token is not None:
        tok = oauth_token.strip()
        if tok:
            current["CLAUDE_CODE_OAUTH_TOKEN"] = tok
        else:
            current.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    if api_key is not None:
        key = api_key.strip()
        if key:
            current["ANTHROPIC_API_KEY"] = key
        else:
            current.pop("ANTHROPIC_API_KEY", None)

    CLAUDE_HOME_DIR.mkdir(parents=True, exist_ok=True)
    CLAUDE_AUTH_ENV_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return get_system_status()


def _build_claude_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(CLAUDE_HOME_DIR)
    env["CLAUDE_CONFIG_DIR"] = str(CLAUDE_HOME_DIR / ".claude")
    env["CI"] = "true"
    env["TERM"] = "dumb"
    saved = load_saved_auth_env()
    for k, v in saved.items():
        if v:
            env[k] = v
    return env


def _mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 10:
        return "***"
    return f"{val[:6]}...{val[-4:]}"


# ---------------------------------------------------------------------------
# Interactive `claude login` session manager
# ---------------------------------------------------------------------------
class _LoginSession:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.output_lines: List[str] = []
        self.oauth_url: Optional[str] = None
        self.status: str = "idle"  # idle | waiting_for_code | completed | error
        self.message: str = ""

    def reset_unlocked(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
        self.proc = None
        self.master_fd = None
        self.output_lines = []
        self.oauth_url = None
        self.status = "idle"
        self.message = ""


_LOGIN_SESSION = _LoginSession()


def start_claude_login() -> Dict[str, Any]:
    """Launch `claude auth login` (or `claude login`) and capture the OAuth URL."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError(
            "Claude Code CLI ('claude') topilmadi. Docker konteynerda '@anthropic-ai/claude-code' o'rnatilganligini tekshiring."
        )

    with _LOGIN_SESSION.lock:
        _LOGIN_SESSION.reset_unlocked()
        _LOGIN_SESSION.status = "waiting_for_code"
        _LOGIN_SESSION.message = "Claude login jarayoni boshlandi..."

        env = _build_claude_env()
        env.pop("CI", None)
        env["TERM"] = "xterm-256color"
        env["BROWSER"] = "echo"

        # Use pty on POSIX (Linux VPS / Docker) so interactive CLI prints OAuth URL properly
        if os.name == "posix":
            import pty

            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                [claude_bin, "auth", "login"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(CLAUDE_WORKSPACE_DIR),
                env=env,
                close_fds=True,
            )
            os.close(slave_fd)
            _LOGIN_SESSION.proc = proc
            _LOGIN_SESSION.master_fd = master_fd

            def _reader_posix(fd: int, p: subprocess.Popen) -> None:
                buf = ""
                while True:
                    try:
                        chunk = os.read(fd, 1024)
                        if not chunk:
                            break
                        text = _strip_ansi(chunk.decode("utf-8", errors="replace"))
                        buf += text
                        for line in buf.splitlines():
                            clean_line = line.strip()
                            if clean_line:
                                with _LOGIN_SESSION.lock:
                                    if clean_line not in _LOGIN_SESSION.output_lines:
                                        _LOGIN_SESSION.output_lines.append(clean_line)
                                    m = URL_RE.search(clean_line)
                                    if m and ("claude.ai" in m.group(0) or "anthropic.com" in m.group(0)):
                                        _LOGIN_SESSION.oauth_url = m.group(0)
                                        _LOGIN_SESSION.message = (
                                            "Quyidagi havolani ochib, Claude obunangiz bilan kiring va tasdiqlash kodini kiriting."
                                        )
                    except OSError:
                        break
                rc = p.wait()
                with _LOGIN_SESSION.lock:
                    if rc == 0:
                        _LOGIN_SESSION.status = "completed"
                        _LOGIN_SESSION.message = "Claude Code muvaffaqiyatli ulandi!"
                    elif _LOGIN_SESSION.status == "waiting_for_code":
                        _LOGIN_SESSION.status = "error"
                        _LOGIN_SESSION.message = f"Login jarayoni yakunlandi (kod: {rc})."

            threading.Thread(target=_reader_posix, args=(master_fd, proc), daemon=True).start()
        else:
            proc = subprocess.Popen(
                [claude_bin, "auth", "login"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(CLAUDE_WORKSPACE_DIR),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _LOGIN_SESSION.proc = proc

            def _reader_win(p: subprocess.Popen) -> None:
                assert p.stdout is not None
                for raw_line in p.stdout:
                    clean_line = _strip_ansi(raw_line).strip()
                    if clean_line:
                        with _LOGIN_SESSION.lock:
                            _LOGIN_SESSION.output_lines.append(clean_line)
                            m = URL_RE.search(clean_line)
                            if m:
                                _LOGIN_SESSION.oauth_url = m.group(0)
                                _LOGIN_SESSION.message = (
                                    "Havolani brauzerda ochib, olingan kodni kiriting."
                                )
                rc = p.wait()
                with _LOGIN_SESSION.lock:
                    _LOGIN_SESSION.status = "completed" if rc == 0 else "error"

            threading.Thread(target=_reader_win, args=(proc,), daemon=True).start()

    # Wait up to 4 seconds for the OAuth URL to appear
    deadline = time.time() + 4.0
    while time.time() < deadline:
        with _LOGIN_SESSION.lock:
            if _LOGIN_SESSION.oauth_url or _LOGIN_SESSION.status in ("completed", "error"):
                break
        time.sleep(0.25)

    return get_login_session_state()


def submit_claude_login_code(code: str) -> Dict[str, Any]:
    """Send the OAuth verification code to the active `claude auth login` process."""
    clean_code = code.strip()
    if not clean_code:
        raise ValueError("Tasdiqlash kodini kiriting.")

    with _LOGIN_SESSION.lock:
        proc = _LOGIN_SESSION.proc
        master_fd = _LOGIN_SESSION.master_fd
        if not proc or proc.poll() is not None:
            raise RuntimeError("Faol login jarayoni topilmadi. Qaytadan 'Login boshlash' tugmasini bosing.")

        payload = (clean_code + "\n").encode("utf-8")
        if master_fd is not None:
            os.write(master_fd, payload)
        elif proc.stdin is not None:
            proc.stdin.write(clean_code + "\n")
            proc.stdin.flush()

    # Wait up to 5 seconds for completion
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with _LOGIN_SESSION.lock:
            if _LOGIN_SESSION.status in ("completed", "error"):
                break
        time.sleep(0.3)

    return get_login_session_state()


def get_login_session_state() -> Dict[str, Any]:
    with _LOGIN_SESSION.lock:
        return {
            "status": _LOGIN_SESSION.status,
            "oauth_url": _LOGIN_SESSION.oauth_url,
            "message": _LOGIN_SESSION.message,
            "output": "\n".join(_LOGIN_SESSION.output_lines[-20:]),
        }


# ---------------------------------------------------------------------------
# System Status (Claude CLI, Auth, VectorCraft CLI, VectorCraft Web)
# ---------------------------------------------------------------------------
def _detect_binary_version(cmd: List[str]) -> Tuple[bool, str]:
    exe = shutil.which(cmd[0])
    if not exe:
        return False, "O'rnatilmagan"
    try:
        res = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=_build_claude_env(),
        )
        out = (res.stdout or res.stderr or "").strip()
        first_line = out.splitlines()[0].strip() if out else "O'rnatilgan"
        return True, first_line
    except Exception as exc:
        return True, f"Mavjud ({exc})"


def _check_claude_auth(claude_installed: bool) -> Dict[str, Any]:
    saved = load_saved_auth_env()
    env = _build_claude_env()
    oauth_tok = env.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    api_key = env.get("ANTHROPIC_API_KEY", "")

    cred_files = [
        CLAUDE_HOME_DIR / ".claude" / ".credentials.json",
        CLAUDE_HOME_DIR / ".claude.json",
    ]
    has_cred_file = any(p.is_file() and p.stat().st_size > 10 for p in cred_files)

    auth_method = "none"
    authenticated = False
    account_info = ""

    if oauth_tok:
        authenticated = True
        auth_method = "oauth_token"
        account_info = f"CLAUDE_CODE_OAUTH_TOKEN ({_mask_secret(oauth_tok)})"
    elif api_key:
        authenticated = True
        auth_method = "api_key"
        account_info = f"ANTHROPIC_API_KEY ({_mask_secret(api_key)})"

    if claude_installed:
        claude_bin = shutil.which("claude")
        if claude_bin:
            try:
                res = subprocess.run(
                    [claude_bin, "auth", "status"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=6,
                    env=env,
                    cwd=str(CLAUDE_WORKSPACE_DIR),
                )
                raw = _strip_ansi((res.stdout or "") + "\n" + (res.stderr or "")).strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        logged_in = bool(parsed.get("loggedIn") or parsed.get("authenticated"))
                        if logged_in:
                            authenticated = True
                            auth_method = parsed.get("authMethod") or parsed.get(" subscriptionType") or "subscription"
                            email = parsed.get("email") or parsed.get("account", {}).get("email") or ""
                            sub = parsed.get("subscriptionType") or ""
                            account_info = " · ".join(x for x in [email, sub, auth_method] if x) or "Claude Subscription"
                except Exception:
                    low = raw.lower()
                    if "logged in" in low or "authenticated" in low or "subscription" in low:
                        if "not logged in" not in low:
                            authenticated = True
                            auth_method = "subscription"
                            account_info = raw.splitlines()[0] if raw else "Claude Subscription"
            except Exception:
                pass

    if not authenticated and has_cred_file:
        # Check if .credentials.json has oauth data
        cred_path = CLAUDE_HOME_DIR / ".claude" / ".credentials.json"
        if cred_path.is_file():
            try:
                cdata = json.loads(cred_path.read_text(encoding="utf-8"))
                if cdata.get("claudeAiOauth"):
                    authenticated = True
                    auth_method = "subscription"
                    sub_type = cdata["claudeAiOauth"].get("subscriptionType", "Pro/Max")
                    account_info = f"Claude Obuna ({sub_type})"
            except Exception:
                pass

    return {
        "authenticated": authenticated,
        "auth_method": auth_method,
        "account_info": account_info or ("Ulangan" if authenticated else "Ulanmagan"),
        "has_saved_oauth_token": bool(saved.get("CLAUDE_CODE_OAUTH_TOKEN")),
        "has_saved_api_key": bool(saved.get("ANTHROPIC_API_KEY")),
        "masked_oauth_token": _mask_secret(saved.get("CLAUDE_CODE_OAUTH_TOKEN", "")),
        "masked_api_key": _mask_secret(saved.get("ANTHROPIC_API_KEY", "")),
        "login_session": get_login_session_state(),
    }


def get_system_status() -> Dict[str, Any]:
    ensure_claude_workspace()
    claude_ok, claude_ver = _detect_binary_version(["claude", "--version"])
    vc_ok, vc_ver = _detect_binary_version(["vectorcraft-cli", "--version"])
    vc_web_ok = (VECTORCRAFT_WEB_DIR / "index.html").is_file()

    auth_info = _check_claude_auth(claude_ok)
    skills = list_skills()
    assets = list_assets()

    return {
        "claude_cli": {
            "installed": claude_ok,
            "version": claude_ver,
        },
        "vectorcraft_cli": {
            "installed": vc_ok,
            "version": vc_ver,
        },
        "vectorcraft_web": {
            "installed": vc_web_ok,
            "url": "/vectorcraft/",
        },
        "auth": auth_info,
        "workspace_dir": str(CLAUDE_WORKSPACE_DIR),
        "skills_count": len(skills),
        "assets_count": len(assets),
    }


# ---------------------------------------------------------------------------
# Skills Management (.claude/skills/<slug>/SKILL.md + files)
# ---------------------------------------------------------------------------
def _parse_skill_frontmatter(content: str, fallback_name: str) -> Tuple[str, str]:
    name = fallback_name
    description = ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            for line in fm.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip().strip('"').strip("'")
                    if k == "name" and v:
                        name = v
                    elif k == "description" and v:
                        description = v
    return name, description


def list_skills() -> List[Dict[str, Any]]:
    ensure_claude_workspace()
    items: List[Dict[str, Any]] = []
    for folder in sorted(CLAUDE_SKILLS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        skill_md = folder / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
        name, description = _parse_skill_frontmatter(content, folder.name)
        extra_files = [
            {
                "name": f.relative_to(folder).as_posix(),
                "size_kb": round(f.stat().st_size / 1024.0, 1),
            }
            for f in sorted(folder.rglob("*"))
            if f.is_file() and f.name != "SKILL.md"
        ]
        items.append(
            {
                "slug": folder.name,
                "name": name,
                "description": description,
                "has_skill_md": skill_md.is_file(),
                "extra_files": extra_files,
                "updated_at": folder.stat().st_mtime,
            }
        )
    return items


def get_skill(slug: str) -> Dict[str, Any]:
    safe_slug = Path(slug).name
    folder = CLAUDE_SKILLS_DIR / safe_slug
    if not folder.is_dir():
        raise FileNotFoundError(f"Skill topilmadi: {safe_slug}")
    skill_md = folder / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
    name, description = _parse_skill_frontmatter(content, safe_slug)
    extra_files = [
        {
            "name": f.relative_to(folder).as_posix(),
            "size_kb": round(f.stat().st_size / 1024.0, 1),
        }
        for f in sorted(folder.rglob("*"))
        if f.is_file() and f.name != "SKILL.md"
    ]
    return {
        "slug": safe_slug,
        "name": name,
        "description": description,
        "content": content,
        "extra_files": extra_files,
    }


def save_skill(
    name: str,
    description: str,
    content: str,
    slug: Optional[str] = None,
) -> Dict[str, Any]:
    safe_slug = _slugify(slug or name)
    folder = CLAUDE_SKILLS_DIR / safe_slug
    folder.mkdir(parents=True, exist_ok=True)

    body = content.strip()
    if not body.startswith("---"):
        clean_name = name.strip() or safe_slug
        clean_desc = description.strip() or "Maxsus dizayn skilli"
        body = f"---\nname: {clean_name}\ndescription: {clean_desc}\n---\n\n{body}"

    (folder / "SKILL.md").write_text(body + "\n", encoding="utf-8")
    return get_skill(safe_slug)


def delete_skill(slug: str) -> Dict[str, Any]:
    safe_slug = Path(slug).name
    folder = CLAUDE_SKILLS_DIR / safe_slug
    if not folder.is_dir():
        raise FileNotFoundError(f"Skill topilmadi: {safe_slug}")
    shutil.rmtree(folder)
    return {"ok": True, "deleted": safe_slug}


def upload_skill_file(slug: str, filename: str, raw_bytes: bytes) -> Dict[str, Any]:
    safe_slug = _slugify(slug)
    folder = CLAUDE_SKILLS_DIR / safe_slug
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("Fayl nomi noto'g'ri.")

    # If a ZIP archive is uploaded and contains SKILL.md, extract it into the skill folder
    if safe_name.lower().endswith(".zip"):
        import io

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            names = zf.namelist()
            has_skill_md = any(Path(n).name == "SKILL.md" for n in names)
            if has_skill_md:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    member_name = Path(member.filename).name
                    if member_name:
                        (folder / member_name).write_bytes(zf.read(member))
                return get_skill(safe_slug)

    target = folder / safe_name
    target.write_bytes(raw_bytes)
    return get_skill(safe_slug)


def delete_skill_file(slug: str, filename: str) -> Dict[str, Any]:
    safe_slug = Path(slug).name
    safe_name = Path(filename).name
    target = CLAUDE_SKILLS_DIR / safe_slug / safe_name
    if not target.is_file():
        raise FileNotFoundError(f"Fayl topilmadi: {safe_name}")
    target.unlink()
    return get_skill(safe_slug)


# ---------------------------------------------------------------------------
# Server Assets Management (/app/data/claude_workspace/assets/)
# ---------------------------------------------------------------------------
def list_assets() -> List[Dict[str, Any]]:
    ensure_claude_workspace()
    items: List[Dict[str, Any]] = []
    for p in sorted(CLAUDE_ASSETS_DIR.iterdir()):
        if not p.is_file():
            continue
        items.append(
            {
                "name": p.name,
                "ext": p.suffix.lower(),
                "size_kb": round(p.stat().st_size / 1024.0, 1),
                "updated_at": p.stat().st_mtime,
            }
        )
    return items


def save_asset(filename: str, raw_bytes: bytes) -> Dict[str, Any]:
    ensure_claude_workspace()
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("Fayl nomi bo'sh bo'lishi mumkin emas.")
    target = CLAUDE_ASSETS_DIR / safe_name
    target.write_bytes(raw_bytes)
    return {
        "name": target.name,
        "ext": target.suffix.lower(),
        "size_kb": round(len(raw_bytes) / 1024.0, 1),
    }


def delete_asset(filename: str) -> Dict[str, Any]:
    safe_name = Path(filename).name
    target = CLAUDE_ASSETS_DIR / safe_name
    if not target.is_file():
        raise FileNotFoundError(f"Asset topilmadi: {safe_name}")
    target.unlink()
    return {"ok": True, "deleted": safe_name}


def get_asset_path(filename: str) -> Path:
    safe_name = Path(filename).name
    target = CLAUDE_ASSETS_DIR / safe_name
    if not target.is_file():
        raise FileNotFoundError(f"Asset topilmadi: {safe_name}")
    return target


# ---------------------------------------------------------------------------
# Workspace Config (.mcp.json & CLAUDE.md)
# ---------------------------------------------------------------------------
def get_workspace_config() -> Dict[str, Any]:
    ensure_claude_workspace()
    mcp_text = (
        CLAUDE_MCP_CONFIG_PATH.read_text(encoding="utf-8", errors="replace")
        if CLAUDE_MCP_CONFIG_PATH.is_file()
        else json.dumps(DEFAULT_MCP_CONFIG, indent=2)
    )
    claude_md = (
        CLAUDE_MD_PATH.read_text(encoding="utf-8", errors="replace")
        if CLAUDE_MD_PATH.is_file()
        else DEFAULT_CLAUDE_MD
    )
    return {
        "mcp_json": mcp_text,
        "claude_md": claude_md,
    }


def save_workspace_config(mcp_json: Optional[str] = None, claude_md: Optional[str] = None) -> Dict[str, Any]:
    ensure_claude_workspace()
    if mcp_json is not None:
        # Validate JSON
        parsed = json.loads(mcp_json)
        CLAUDE_MCP_CONFIG_PATH.write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if claude_md is not None:
        CLAUDE_MD_PATH.write_text(claude_md.strip() + "\n", encoding="utf-8")
    return get_workspace_config()


# ---------------------------------------------------------------------------
# VectorCraft CLI Headless Conversion & Preview Helpers
# ---------------------------------------------------------------------------
def _run_vectorcraft_convert(in_path: Path, out_path: Path) -> Tuple[bool, str]:
    vc_bin = shutil.which("vectorcraft-cli")
    if not vc_bin:
        return False, "vectorcraft-cli o'rnatilmagan"
    try:
        res = subprocess.run(
            [vc_bin, "run", "--in", str(in_path), "--export", str(out_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if res.returncode == 0 and out_path.is_file():
            return True, "OK"
        return False, (res.stderr or res.stdout or f"Exit code {res.returncode}").strip()
    except Exception as exc:
        return False, str(exc)


def _render_pdf_preview_png(pdf_path: Path, png_path: Path, dpi: int = 180) -> bool:
    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count < 1:
            doc.close()
            return False
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        pix.save(str(png_path))
        doc.close()
        return png_path.is_file()
    except Exception as exc:
        logger.warning("PDF preview render xatosi (%s): %s", pdf_path.name, exc)
        return False


def _ensure_dual_outputs(out_dir: Path, preferred_stem: str) -> List[str]:
    """
    Ensure that for any generated design in `out_dir`, both `.vectorcraft` and `.pdf`
    exist (plus a `*_preview.png` rendered from the PDF).
    """
    notes: List[str] = []
    vc_files = sorted(out_dir.glob("*.vectorcraft"))
    pdf_files = sorted(out_dir.glob("*.pdf"))
    svg_files = sorted(out_dir.glob("*.svg"))

    # 1. If .vectorcraft exists but no .pdf for it, convert .vectorcraft -> .pdf
    for vc_file in vc_files:
        target_pdf = out_dir / f"{vc_file.stem}.pdf"
        if not target_pdf.is_file():
            ok, msg = _run_vectorcraft_convert(vc_file, target_pdf)
            if ok:
                notes.append(f"{vc_file.name} -> {target_pdf.name} eksport qilindi.")
            else:
                notes.append(f"{vc_file.name} dan PDF eksport xatosi: {msg}")

    # Refresh list
    vc_files = sorted(out_dir.glob("*.vectorcraft"))
    pdf_files = sorted(out_dir.glob("*.pdf"))

    # 2. If .svg exists and either .vectorcraft or .pdf is missing, convert via vectorcraft-cli or svglib
    for svg_file in svg_files:
        target_vc = out_dir / f"{svg_file.stem}.vectorcraft"
        target_pdf = out_dir / f"{svg_file.stem}.pdf"
        if not target_vc.is_file():
            ok, _ = _run_vectorcraft_convert(svg_file, target_vc)
            if ok:
                notes.append(f"{svg_file.name} -> {target_vc.name} konvertatsiya qilindi.")
        if not target_pdf.is_file():
            ok, _ = _run_vectorcraft_convert(svg_file, target_pdf)
            if not ok:
                # Fallback SVG -> PDF via svglib + reportlab
                try:
                    from reportlab.graphics import renderPDF
                    from svglib.svglib import svg2rlg

                    drawing = svg2rlg(str(svg_file))
                    if drawing:
                        renderPDF.drawToFile(drawing, str(target_pdf))
                        notes.append(f"{svg_file.name} -> {target_pdf.name} (svglib) yaratildi.")
                except Exception as exc:
                    logger.warning("SVG->PDF fallback xatosi: %s", exc)

    # Refresh list
    vc_files = sorted(out_dir.glob("*.vectorcraft"))
    pdf_files = sorted(out_dir.glob("*.pdf"))

    # 3. If .pdf exists but no .vectorcraft exists for it, convert .pdf -> .vectorcraft
    for pdf_file in pdf_files:
        target_vc = out_dir / f"{pdf_file.stem}.vectorcraft"
        if not target_vc.is_file():
            ok, msg = _run_vectorcraft_convert(pdf_file, target_vc)
            if ok:
                notes.append(f"{pdf_file.name} -> {target_vc.name} yaratildi.")

    # 4. Render PNG previews for all PDFs
    for pdf_file in sorted(out_dir.glob("*.pdf")):
        preview_png = out_dir / f"{pdf_file.stem}_preview.png"
        if not preview_png.is_file():
            _render_pdf_preview_png(pdf_file, preview_png)

    return notes


def _collect_job_outputs_payload(job_id: str, out_dir: Path) -> Dict[str, Any]:
    output_files: List[Dict[str, Any]] = []
    vectorcraft_file: Optional[str] = None
    pdf_file: Optional[str] = None
    preview_file: Optional[str] = None
    svg_file: Optional[str] = None

    all_files = sorted([p for p in out_dir.iterdir() if p.is_file()], key=lambda x: x.name)

    for p in all_files:
        ext = p.suffix.lower()
        if ext == ".zip":
            continue
        if p.name.endswith("_preview.png"):
            if not preview_file:
                preview_file = p.name
            continue

        item_preview: Optional[str] = None
        candidate_prev = out_dir / f"{p.stem}_preview.png"
        if candidate_prev.is_file():
            item_preview = candidate_prev.name
        elif ext == ".png":
            item_preview = p.name

        if ext == ".vectorcraft" and not vectorcraft_file:
            vectorcraft_file = p.name
        elif ext == ".pdf" and not pdf_file:
            pdf_file = p.name
            if not preview_file and item_preview:
                preview_file = item_preview
        elif ext == ".svg" and not svg_file:
            svg_file = p.name

        output_files.append(
            {
                "filename": p.name,
                "ext": ext,
                "size_kb": round(p.stat().st_size / 1024.0, 1),
                "preview_file": item_preview,
            }
        )

    zip_name: Optional[str] = None
    if len(output_files) > 1:
        zip_path = bundle_job_outputs_zip(job_id, [f["filename"] for f in output_files])
        zip_name = zip_path.name

    return {
        "output_files": output_files,
        "vectorcraft_file": vectorcraft_file,
        "pdf_file": pdf_file,
        "svg_file": svg_file,
        "preview_file": preview_file,
        "zip_file": zip_name,
    }


# ---------------------------------------------------------------------------
# AI Design Generation via Claude Code CLI + VectorCraft MCP
# ---------------------------------------------------------------------------
def run_ai_design_job(
    prompt: str,
    skill_slugs: Optional[List[str]] = None,
    asset_names: Optional[List[str]] = None,
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    output_basename: str = "design",
    uploaded_files: Optional[List[Tuple[str, bytes]]] = None,
    source_job_id: Optional[str] = None,
    source_filename: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Claude Code headlessly with VectorCraft MCP and workspace Skills/Assets
    to generate `.vectorcraft` and `.pdf` design files.
    """
    ensure_claude_workspace()
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Dizayn topshirig'ini (prompt) kiriting.")

    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError(
            "Serverda Claude Code CLI ('claude') o'rnatilmagan. Docker obrazni qayta yig'ing (rebuild) yoki 'claude' o'rnatilganligini tekshiring."
        )

    job_id, job_dir = create_job("vcraft")
    in_dir = job_dir / "inputs"
    out_dir = job_dir / "outputs"

    safe_stem = _slugify(Path(output_basename).stem or "design")

    saved_inputs: List[Path] = []
    if uploaded_files:
        for fname, fbytes in uploaded_files:
            safe_in = Path(fname).name
            if safe_in and fbytes:
                p = in_dir / safe_in
                p.write_bytes(fbytes)
                saved_inputs.append(p)

    if source_job_id and source_filename:
        src_path = get_job_output_file(source_job_id, source_filename)
        copied_src = in_dir / src_path.name
        shutil.copy2(src_path, copied_src)
        saved_inputs.append(copied_src)

    target_vc_path = (out_dir / f"{safe_stem}.vectorcraft").resolve()
    target_pdf_path = (out_dir / f"{safe_stem}.pdf").resolve()

    # Build instructions for Claude Code
    prompt_sections: List[str] = [
        "Siz PrintGoo platformasida VectorCraft MCP (`mcp__vectorcraft__*`) orqali professional dizayn yaratuvchi AI dizaynersiz.",
        f"\n## Foydalanuvchi Topshirig'i:\n{clean_prompt}",
    ]

    if width_mm and height_mm and width_mm > 0 and height_mm > 0:
        w_pt = round(width_mm * PT_PER_MM, 4)
        h_pt = round(height_mm * PT_PER_MM, 4)
        prompt_sections.append(
            f"\n## Aniq Dizayn O'lchami:\n"
            f"- Kenglik (Width): **{width_mm} mm** (`{w_pt} pt`)\n"
            f"- Balandlik (Height): **{height_mm} mm** (`{h_pt} pt`)\n"
            f"VectorCraft'da yangi hujjat yaratishda `run_command` -> `file.new` ga aynan `{{\"width\": {w_pt}, \"height\": {h_pt}}}` bering."
        )

    if skill_slugs:
        skill_paths = []
        for slug in skill_slugs:
            sp = (CLAUDE_SKILLS_DIR / Path(slug).name / "SKILL.md").resolve()
            if sp.is_file():
                skill_paths.append(f"- `{sp}` (Skill: `{slug}`)")
        if skill_paths:
            prompt_sections.append(
                "\n## Foydalanish Shart Bo'lgan Maxsus Skillar:\n"
                "Ishni boshlashdan oldin quyidagi Skill fayllarini `Read` orqali o'qing va ulardagi qoidalarga amal qiling:\n"
                + "\n".join(skill_paths)
            )

    if asset_names:
        asset_paths = []
        for aname in asset_names:
            ap = (CLAUDE_ASSETS_DIR / Path(aname).name).resolve()
            if ap.is_file():
                asset_paths.append(f"- `{ap}`")
        if asset_paths:
            prompt_sections.append(
                "\n## Serverdagi Tanlangan Foydali Fayllar (Assets):\n"
                + "\n".join(asset_paths)
            )

    if saved_inputs:
        in_lines = [f"- `{p.resolve()}`" for p in saved_inputs]
        prompt_sections.append(
            "\n## Foydalanuvchi Yuklagan Kiruvchi (Input) Fayllar:\n"
            "Agar kiruvchi fayl `.vectorcraft`, `.pdf` yoki `.svg` bo'lsa, uni VectorCraft MCP `open_file` orqali ochib tahrirlashingiz yoki namuna sifatida ko'rishingiz mumkin:\n"
            + "\n".join(in_lines)
        )

    prompt_sections.append(
        f"\n## MAJBURIY CHIQISH FAYLLARI (Outputs):\n"
        f"Dizayn tayyor bo'lgach, uni VectorCraft MCP orqali quyidagi IKKALA manzilga aniq saqlang:\n"
        f"1. VectorCraft standart fayli: `{target_vc_path}` (`save_file` -> `{{\"path\": \"{target_vc_path}\", \"preview\": true}}`)\n"
        f"2. Bosma PDF fayli: `{target_pdf_path}` (`export` -> `{{\"path\": \"{target_pdf_path}\", \"format\": \"pdf\"}}`)\n"
        f"Barcha fayllar `{out_dir.resolve()}` papkasi ichida bo'lishi shart. Yakunda bajargan ishlaringiz haqida o'zbek tilida qisqa va tushunarli hisobot yozing."
    )

    full_prompt = "\n".join(prompt_sections)

    cmd: List[str] = [
        claude_bin,
        "-p",
        full_prompt,
        "--mcp-config",
        str(CLAUDE_MCP_CONFIG_PATH),
        "--allowedTools",
        "mcp__vectorcraft__*,Read,Write,Edit,Glob,Grep,Bash",
        "--output-format",
        "json",
    ]
    if model and model.strip():
        cmd.extend(["--model", model.strip()])

    started_at = time.time()
    env = _build_claude_env()

    try:
        res = subprocess.run(
            cmd,
            cwd=str(CLAUDE_WORKSPACE_DIR),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code javob kutish vaqti (300 soniya) tugadi.")

    duration_sec = round(time.time() - started_at, 1)
    raw_stdout = (res.stdout or "").strip()
    raw_stderr = (res.stderr or "").strip()

    assistant_reply = ""
    cost_usd: Optional[float] = None
    num_turns: Optional[int] = None
    is_error = res.returncode != 0

    if raw_stdout:
        # Parse JSON output from `claude -p --output-format json`
        try:
            parsed = json.loads(raw_stdout)
            if isinstance(parsed, dict):
                assistant_reply = str(parsed.get("result") or parsed.get("message") or "")
                cost_usd = parsed.get("total_cost_usd") or parsed.get("cost_usd")
                num_turns = parsed.get("num_turns")
                if parsed.get("is_error"):
                    is_error = True
        except Exception:
            # Might be multiple JSON lines or plain text
            for line in reversed(raw_stdout.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and ("result" in obj or "message" in obj):
                            assistant_reply = str(obj.get("result") or obj.get("message") or "")
                            cost_usd = obj.get("total_cost_usd") or obj.get("cost_usd")
                            num_turns = obj.get("num_turns")
                            break
                    except Exception:
                        pass
            if not assistant_reply:
                assistant_reply = _strip_ansi(raw_stdout)

    if not assistant_reply and raw_stderr:
        assistant_reply = _strip_ansi(raw_stderr)

    # Ensure both .vectorcraft and .pdf outputs exist if any design file was produced
    conversion_notes = _ensure_dual_outputs(out_dir, safe_stem)
    outputs_payload = _collect_job_outputs_payload(job_id, out_dir)

    if is_error and not outputs_payload["output_files"]:
        err_msg = assistant_reply or raw_stderr or f"Claude Code xatolik bilan yakunlandi (kod {res.returncode})."
        if "not logged in" in err_msg.lower() or "authentication" in err_msg.lower() or "oauth" in err_msg.lower():
            err_msg += "\n\nIltimos, 'Skills & Claude Sozlamalari' bo'limidan Claude obunangizga login qiling."
        raise RuntimeError(err_msg)

    meta = {
        "job_id": job_id,
        "tool": "vcraft",
        "created_at": time.time(),
        "prompt": clean_prompt,
        "skill_slugs": skill_slugs or [],
        "asset_names": asset_names or [],
        "width_mm": width_mm,
        "height_mm": height_mm,
        "duration_sec": duration_sec,
        "assistant_reply": assistant_reply,
        "conversion_notes": conversion_notes,
        "outputs": [f["filename"] for f in outputs_payload["output_files"]],
    }
    save_job_meta(job_id, meta)

    return {
        "job_id": job_id,
        "assistant_reply": assistant_reply,
        "duration_sec": duration_sec,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
        "conversion_notes": conversion_notes,
        "width_mm": width_mm,
        "height_mm": height_mm,
        **outputs_payload,
    }


def export_vectorcraft_document(
    filename: str,
    raw_bytes: bytes,
    save_to_assets: bool = False,
) -> Dict[str, Any]:
    """
    Take a `.vectorcraft` (or `.svg` / `.pdf`) file from the in-browser VectorCraft Web Editor
    or user upload, create a PrintHub job, and produce both `.vectorcraft` and `.pdf` outputs
    so the user can download them or send the PDF directly to Val Montaji / Varaq Montaji.
    """
    ensure_claude_workspace()
    safe_name = Path(filename).name or "editor_design.vectorcraft"
    stem = _slugify(Path(safe_name).stem or "editor_design")
    ext = Path(safe_name).suffix.lower() or ".vectorcraft"

    job_id, job_dir = create_job("vcraft_editor")
    out_dir = job_dir / "outputs"

    primary_path = out_dir / f"{stem}{ext}"
    primary_path.write_bytes(raw_bytes)

    if save_to_assets:
        save_asset(primary_path.name, raw_bytes)

    conversion_notes = _ensure_dual_outputs(out_dir, stem)
    outputs_payload = _collect_job_outputs_payload(job_id, out_dir)

    save_job_meta(
        job_id,
        {
            "job_id": job_id,
            "tool": "vcraft_editor",
            "created_at": time.time(),
            "outputs": [f["filename"] for f in outputs_payload["output_files"]],
        },
    )

    return {
        "job_id": job_id,
        "conversion_notes": conversion_notes,
        "saved_to_assets": save_to_assets,
        **outputs_payload,
    }


def save_job_file_to_assets(job_id: str, filename: str) -> Dict[str, Any]:
    """Copy a generated `.vectorcraft` or `.pdf` file from a job into persistent Server Assets."""
    path = get_job_output_file(job_id, filename)
    return save_asset(path.name, path.read_bytes())


VECTORCRAFT_WEB_RELEASE_URL = (
    "https://github.com/storytold/vectorcraft/releases/download/v0.24.1/vectorcraft-web-0.24.1.zip"
)


def install_vectorcraft_web_bundle() -> Dict[str, Any]:
    """Download and extract vectorcraft-web WASM bundle into VECTORCRAFT_WEB_DIR if not present."""
    import io
    import urllib.request

    VECTORCRAFT_WEB_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        VECTORCRAFT_WEB_RELEASE_URL,
        headers={"User-Agent": "PrintGoo-PrintHub/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            # Strip top-level folder `vectorcraft-web-<ver>/` if present
            parts = Path(member.filename).parts
            rel_parts = parts[1:] if (len(parts) > 1 and parts[0].startswith("vectorcraft-web")) else parts
            if not rel_parts:
                continue
            dest = VECTORCRAFT_WEB_DIR.joinpath(*rel_parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))

    return get_system_status()

