"""Job directory management, file lookup, ZIP bundling, and automatic cleanup."""

from __future__ import annotations

import json
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import JOB_TTL_HOURS, JOBS_DIR


def create_job(tool: str) -> tuple[str, Path]:
    """Create a fresh job directory under data/jobs/<job_id>."""
    cleanup_old_jobs()
    job_id = f"{tool}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    (job_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (job_dir / "outputs").mkdir(parents=True, exist_ok=True)
    save_job_meta(job_id, {"job_id": job_id, "tool": tool, "created_at": time.time(), "outputs": []})
    return job_id, job_dir


def get_job_dir(job_id: str) -> Path:
    # Prevent path traversal
    safe_id = Path(job_id).name
    job_dir = JOBS_DIR / safe_id
    if not job_dir.is_dir():
        raise FileNotFoundError(f"Job topilmadi: {safe_id}")
    return job_dir


def save_job_meta(job_id: str, meta: Dict[str, Any]) -> None:
    job_dir = JOBS_DIR / Path(job_id).name
    meta_path = job_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_job_meta(job_id: str) -> Dict[str, Any]:
    job_dir = get_job_dir(job_id)
    meta_path = job_dir / "meta.json"
    if not meta_path.is_file():
        return {"job_id": job_id, "outputs": []}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def get_job_output_file(job_id: str, filename: str) -> Path:
    job_dir = get_job_dir(job_id)
    safe_name = Path(filename).name
    file_path = job_dir / "outputs" / safe_name
    if not file_path.is_file():
        raise FileNotFoundError(f"Fayl topilmadi: {safe_name}")
    return file_path


def bundle_job_outputs_zip(job_id: str, filenames: Optional[List[str]] = None) -> Path:
    """Bundle output files of a job into a single ZIP archive."""
    job_dir = get_job_dir(job_id)
    out_dir = job_dir / "outputs"
    zip_path = out_dir / f"{job_id}_all.zip"
    targets = (
        [out_dir / Path(f).name for f in filenames]
        if filenames
        else [p for p in sorted(out_dir.iterdir()) if p.is_file() and p.suffix.lower() != ".zip"]
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in targets:
            if p.is_file():
                zf.write(p, arcname=p.name)
    return zip_path


def cleanup_old_jobs() -> int:
    """Delete job folders older than JOB_TTL_HOURS."""
    if JOB_TTL_HOURS <= 0:
        return 0
    cutoff = time.time() - (JOB_TTL_HOURS * 3600)
    removed = 0
    for item in JOBS_DIR.iterdir():
        if not item.is_dir():
            continue
        try:
            mtime = item.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed
