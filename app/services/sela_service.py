"""Service wrapper for Sela Label Generator."""

from __future__ import annotations

from functools import lru_cache
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf

from app.config import ENGINES_DIR, SELA_SET_DIR, SELA_TEMPLATES_DIR
from app.jobs import create_job, save_job_meta

_SELA_ENGINE_DIR = str(ENGINES_DIR / "sela")
if _SELA_ENGINE_DIR not in sys.path:
    sys.path.insert(0, _SELA_ENGINE_DIR)

import generate_labels as gl  # noqa: E402


def list_templates() -> List[Dict[str, Any]]:
    """Return available Sela template files (.pdf / .svg) in data/sela_templates."""
    items: List[Dict[str, Any]] = []
    if SELA_TEMPLATES_DIR.is_dir():
        for p in sorted(SELA_TEMPLATES_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in (".pdf", ".svg"):
                items.append({
                    "name": p.name,
                    "size_kb": round(p.stat().st_size / 1024, 1),
                })
    return items


def get_template_path(template_name: Optional[str] = None) -> Path:
    """Resolve template path by name, or return the first available template."""
    if template_name:
        safe = Path(template_name).name
        cand = SELA_TEMPLATES_DIR / safe
        if cand.is_file():
            return cand
        raise FileNotFoundError(f"Shablon topilmadi: {safe}")

    templates = list_templates()
    if templates:
        return SELA_TEMPLATES_DIR / templates[0]["name"]

    raise FileNotFoundError(
        "Sela shabloni (.pdf yoki .svg) hali yuklanmagan. Iltimos, avval shablon faylini yuklang."
    )


def save_uploaded_template(filename: str, content: bytes) -> Dict[str, Any]:
    safe = Path(filename).name
    if Path(safe).suffix.lower() not in (".pdf", ".svg"):
        raise ValueError("Shablon faqat .pdf yoki .svg formatida bo'lishi kerak.")
    dest = SELA_TEMPLATES_DIR / safe
    dest.write_bytes(content)
    return {"name": dest.name, "size_kb": round(dest.stat().st_size / 1024, 1)}


def list_set_catalog() -> Dict[str, Any]:
    """List general static labels and auto-grouped composition (sostavnik) sets."""
    general: List[Dict[str, str]] = []
    sostav_map: Dict[str, List[str]] = {}
    lang_re = re.compile(r"^lang\d+_(.+)$", re.IGNORECASE)

    if SELA_SET_DIR.is_dir():
        files = sorted(
            p for p in SELA_SET_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in (".pdf", ".svg")
        )
        for fp in files:
            m = lang_re.match(fp.stem)
            if m:
                key = m.group(1)
                sostav_map.setdefault(key, []).append(fp.name)
            else:
                general.append({"name": fp.name, "label": fp.stem})

    sostav_groups = [
        {"key": k, "label": f"{k}% ({len(v)} til)" if len(v) > 1 else f"{k}%", "files": sorted(v)}
        for k, v in sorted(sostav_map.items())
    ]
    return {"general": general, "sostav_groups": sostav_groups}


def resolve_common_label_paths(
    general_names: Optional[List[str]] = None,
    sostav_key: Optional[str] = None,
) -> List[Path]:
    paths: List[Path] = []
    for name in (general_names or []):
        safe = Path(name).name
        fp = SELA_SET_DIR / safe
        if fp.is_file():
            paths.append(fp)

    if sostav_key:
        catalog = list_set_catalog()
        for grp in catalog["sostav_groups"]:
            if grp["key"] == sostav_key:
                for fn in grp["files"]:
                    fp = SELA_SET_DIR / fn
                    if fp.is_file():
                        paths.append(fp)
                break
    return paths


def preview_label_pdf(
    artikul: str,
    colour: str,
    size: str,
    barcode: str,
    template_name: Optional[str] = None,
) -> bytes:
    tpl_path = get_template_path(template_name)
    data = gl.LabelData(
        artikul=artikul.strip() or "SI7804050205",
        colour=colour.strip() or "33",
        size=size.strip() or "104/ 4-5 YEARS",
        barcode=barcode.strip() or "4620544686957",
        qty=1,
    )
    return gl.render_label_preview_pdf(tpl_path, data)


def preview_label_png(
    artikul: str,
    colour: str,
    size: str,
    barcode: str,
    template_name: Optional[str] = None,
    dpi: int = 180,
) -> bytes:
    tpl_path = get_template_path(template_name)
    data = gl.LabelData(
        artikul=artikul.strip() or "SI7804050205",
        colour=colour.strip() or "33",
        size=size.strip() or "104/ 4-5 YEARS",
        barcode=barcode.strip() or "4620544686957",
        qty=1,
    )
    return gl.render_label_preview_png(tpl_path, data, dpi=dpi)


@lru_cache(maxsize=64)
def _cached_static_set_pdf(file_path_str: str, mtime_ns: int) -> bytes:
    del mtime_ns  # cache key invalidation
    return gl.render_static_label_preview_pdf(Path(file_path_str))


def preview_static_set_pdf(filename: str) -> bytes:
    fp = SELA_SET_DIR / Path(filename).name
    if not fp.is_file():
        raise FileNotFoundError(f"Set fayli topilmadi: {filename}")
    return _cached_static_set_pdf(str(fp), fp.stat().st_mtime_ns)


def preview_static_set_png(filename: str, dpi: int = 150) -> bytes:
    fp = SELA_SET_DIR / Path(filename).name
    if not fp.is_file():
        raise FileNotFoundError(f"Set fayli topilmadi: {filename}")
    return gl.render_static_label_preview_png(fp, dpi=dpi)


def render_pdf_first_page_png(pdf_path: Path, dpi: int = 120) -> bytes:
    doc = pymupdf.open(str(pdf_path))
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()


def generate_sela_job(
    items_payload: Optional[List[Dict[str, Any]]] = None,
    csv_bytes: Optional[bytes] = None,
    csv_filename: Optional[str] = None,
    template_name: Optional[str] = None,
    template_bytes: Optional[bytes] = None,
    template_upload_name: Optional[str] = None,
    orientation: str = "portrait",
    margin_mm: float = 5.0,
    gap_mm: float = 2.0,
    general_sets: Optional[List[str]] = None,
    sostav_key: Optional[str] = None,
    set_mode: str = "end",
) -> Dict[str, Any]:
    """Generate Sela A4 PDF inside a new job folder and return metadata."""
    job_id, job_dir = create_job("sela")
    inputs_dir = job_dir / "inputs"
    outputs_dir = job_dir / "outputs"

    # Resolve template (either uploaded for this job or saved template)
    if template_bytes and template_upload_name:
        ext = Path(template_upload_name).suffix.lower()
        if ext not in (".pdf", ".svg"):
            raise ValueError("Shablon .pdf yoki .svg bo'lishi kerak.")
        tpl_path = inputs_dir / f"template{ext}"
        tpl_path.write_bytes(template_bytes)
    else:
        tpl_path = get_template_path(template_name)

    common_paths = resolve_common_label_paths(general_sets, sostav_key)

    label_items: List[gl.LabelData] = []
    if csv_bytes:
        csv_path = inputs_dir / (Path(csv_filename or "orders.csv").name)
        csv_path.write_bytes(csv_bytes)
        loaded = gl.load_items_from_csv(csv_path, set_dir=SELA_SET_DIR)
        for it in loaded:
            if not it.common_labels and common_paths:
                it.common_labels = list(common_paths)
            label_items.append(it)
    elif items_payload:
        for row in items_payload:
            item_common = resolve_common_label_paths(
                row.get("general_sets") if row.get("general_sets") is not None else general_sets,
                row.get("sostav_key") if row.get("sostav_key") is not None else sostav_key,
            )
            label_items.append(
                gl.LabelData(
                    artikul=str(row["artikul"]).strip(),
                    colour=str(row["colour"]).strip(),
                    size=str(row["size"]).strip(),
                    barcode=gl.normalize_ean13(str(row["barcode"]).strip()),
                    qty=max(1, int(row.get("qty", 26))),
                    common_labels=item_common,
                )
            )

    if not label_items:
        raise ValueError("Kamida bitta etiketka ma'lumoti yoki CSV fayl kiritilishi shart.")

    first_art = re.sub(r"[^A-Za-z0-9_-]+", "_", label_items[0].artikul)[:32] or "sela"
    out_filename = f"sela_{first_art}_a4.pdf"
    out_path = outputs_dir / out_filename

    total_placed, page_count, per_page = gl.generate_a4_pdf(
        template_path=tpl_path,
        items=label_items,
        output_path=out_path,
        orientation=orientation,
        margin_mm=margin_mm,
        gap_mm=gap_mm,
        common_labels=common_paths,
        set_mode=set_mode,
    )

    result = {
        "job_id": job_id,
        "tool": "sela",
        "output_file": out_filename,
        "preview_file": out_filename,
        "size_kb": round(out_path.stat().st_size / 1024, 1),
        "total_labels": total_placed,
        "page_count": page_count,
        "per_page": per_page,
        "items_count": len(label_items),
        "orientation": orientation,
        "outputs": [out_filename],
    }
    save_job_meta(job_id, result)
    return result
