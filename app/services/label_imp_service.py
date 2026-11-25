"""Service wrapper for Label Imposition (Flexo / Cylinder Gear Imposition)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pymupdf

from app.config import ENGINES_DIR, GEARS_JSON_PATH
from app.jobs import bundle_job_outputs_zip, create_job, get_job_output_file, save_job_meta

_LABEL_IMP_DIR = str(ENGINES_DIR / "label_imp")
if _LABEL_IMP_DIR not in sys.path:
    sys.path.insert(0, _LABEL_IMP_DIR)

from core.gear_manager import GearData, GearManager  # noqa: E402
from core.imposition_engine import (  # noqa: E402
    ImpositionConfig,
    ImpositionEngine,
    resolve_design_orientation,
)
from core.pdf_inspector import inspect_pdf_designs  # noqa: E402
from core.color_separator import detect_design_colors  # noqa: E402


def _get_gear_manager() -> GearManager:
    return GearManager(json_path=GEARS_JSON_PATH)


def list_gears() -> Dict[str, Any]:
    gm = _get_gear_manager()
    return {
        "plate_thickness_mm": gm.plate_thickness_mm,
        "gears": [asdict(g) for g in gm.gears],
    }


def toggle_gear(gear_num: int, available: bool) -> Dict[str, Any]:
    gm = _get_gear_manager()
    ok = gm.set_gear_availability(gear_num, available)
    if not ok:
        raise ValueError(f"Val topilmadi: {gear_num}")
    gm.save()
    return {"gear": gear_num, "available": available}


def upsert_gear(payload: Dict[str, Any]) -> Dict[str, Any]:
    gm = _get_gear_manager()
    g = GearData(
        gear=int(payload["gear"]),
        pitch_diameter=float(payload["pitch_diameter"]),
        plate_thickness=float(payload.get("plate_thickness", gm.plate_thickness_mm)),
        cylinder_diameter=float(payload["cylinder_diameter"]),
        film_length=float(payload["film_length"]),
        printing_length=float(payload["printing_length"]),
        available=bool(payload.get("available", True)),
    )
    gm.gears = [x for x in gm.gears if x.gear != g.gear]
    gm.gears.append(g)
    gm.gears.sort(key=lambda x: x.gear)
    gm.save()
    return asdict(g)


def delete_gear(gear_num: int) -> Dict[str, Any]:
    gm = _get_gear_manager()
    before = len(gm.gears)
    gm.gears = [x for x in gm.gears if x.gear != gear_num]
    if len(gm.gears) == before:
        raise ValueError(f"Val topilmadi: {gear_num}")
    gm.save()
    return {"deleted": gear_num}


def inspect_pdf_file(
    pdf_path: Path,
    rotation_mode: str = "auto",
    custom_gear: Optional[int] = None,
    custom_copies: Optional[int] = None,
) -> Dict[str, Any]:
    """Inspect a PDF file and return all detected sticker designs with auto-matched gears."""
    gm = _get_gear_manager()
    designs = inspect_pdf_designs(pdf_path)
    items: List[Dict[str, Any]] = []
    for idx, d in enumerate(designs):
        eff_w, eff_l, rot_deg = resolve_design_orientation(
            d.width_mm, d.length_mm, rotation_mode
        )
        match = gm.find_best_gear(
            eff_l,
            custom_copies=custom_copies,
            custom_gear=custom_gear,
        )
        items.append({
            "index": idx,
            "display_name": d.display_name,
            "width_mm": round(eff_w, 2),
            "length_mm": round(eff_l, 2),
            "orig_width_mm": round(d.width_mm, 2),
            "orig_length_mm": round(d.length_mm, 2),
            "rotation_deg": rot_deg,
            "has_outer_border": d.has_outer_border,
            "page_index": d.page_index,
            "recommended_gear": match.gear if match else None,
            "recommended_copies": match.copies_count if match else None,
            "printing_length_mm": round(match.printing_length_mm, 2) if match else None,
            "film_length_mm": round(match.film_length_mm, 2) if match else None,
            "per_copy_diff_mm": round(match.per_copy_diff_mm, 2) if match else None,
        })
    return {
        "filename": pdf_path.name,
        "design_count": len(items),
        "designs": items,
    }


def inspect_pdf_sources(
    uploaded_files: Optional[List[Tuple[str, bytes]]] = None,
    from_job_id: Optional[str] = None,
    from_filename: Optional[str] = None,
    rotation_mode: str = "auto",
    custom_gear: Optional[int] = None,
    custom_copies: Optional[int] = None,
) -> Dict[str, Any]:
    """Inspect one or more uploaded PDFs and/or a Sela handoff PDF."""
    all_items: List[Dict[str, Any]] = []
    filenames: List[str] = []

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        paths: List[Path] = []

        if from_job_id and from_filename:
            src = get_job_output_file(from_job_id, from_filename)
            paths.append(src)

        for idx, (fname, raw) in enumerate(uploaded_files or []):
            safe = Path(fname).name
            if not safe.lower().endswith(".pdf"):
                continue
            dst = tmp_dir / f"{idx:02d}_{safe}"
            dst.write_bytes(raw)
            paths.append(dst)

        if not paths:
            raise ValueError("PDF fayl yuborilmadi.")

        for p in paths:
            res = inspect_pdf_file(
                p,
                rotation_mode=rotation_mode,
                custom_gear=custom_gear,
                custom_copies=custom_copies,
            )
            filenames.append(res["filename"])
            for item in res["designs"]:
                item["index"] = len(all_items)
                all_items.append(item)

    return {
        "filename": ", ".join(filenames),
        "design_count": len(all_items),
        "designs": all_items,
    }


def preview_label_imposition_pdf(
    uploaded_files: Optional[List[Tuple[str, bytes]]] = None,
    from_job_id: Optional[str] = None,
    from_filename: Optional[str] = None,
    custom_gear: Optional[int] = None,
    custom_copies: Optional[int] = None,
    rotation_mode: str = "auto",
    combine_same_gear: bool = True,
    separate_by_file: bool = False,
    separate_colors: bool = True,
    color_output_mode: str = "side_by_side",
    remove_outer_border: bool = True,
    regmark_enabled: bool = True,
    regmark_stroke_mm: float = 0.2,
    regmark_tick_mm: float = 0.7,
    regmark_custom_width_mm: Optional[float] = None,
    column_gap_mm: float = 5.0,
    max_cylinder_width_mm: float = 0.0,
    design_index: Optional[int] = None,
) -> Tuple[bytes, int]:
    """
    Runs label imposition in a temporary directory and returns (pdf_bytes, page_count)
    for live preview before saving a permanent job.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        inputs_dir = tmp_dir / "inputs"
        outputs_dir = tmp_dir / "outputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        input_paths: List[Path] = []
        if from_job_id and from_filename:
            src = get_job_output_file(from_job_id, from_filename)
            dst = inputs_dir / src.name
            shutil.copy2(src, dst)
            input_paths.append(dst)

        for idx, (fname, raw) in enumerate(uploaded_files or []):
            safe = Path(fname).name
            if not safe.lower().endswith(".pdf"):
                continue
            dst = inputs_dir / f"{idx:02d}_{safe}"
            dst.write_bytes(raw)
            input_paths.append(dst)

        if not input_paths:
            raise ValueError("Kamida bitta PDF fayl yuklang yoki Sela natijasidan yuboring.")

        config = ImpositionConfig(
            remove_outer_border=remove_outer_border,
            separate_colors=separate_colors,
            color_output_mode=color_output_mode,
            rotation_mode=rotation_mode,
            regmark_enabled=regmark_enabled,
            regmark_stroke_mm=regmark_stroke_mm,
            regmark_tick_mm=regmark_tick_mm,
            regmark_custom_width_mm=regmark_custom_width_mm if (regmark_custom_width_mm and regmark_custom_width_mm > 0) else None,
            column_gap_mm=column_gap_mm,
            max_cylinder_width_mm=max_cylinder_width_mm,
            export_svg=False,
            export_eps=False,
        )

        gm = _get_gear_manager()
        engine = ImpositionEngine(gm)

        if design_index is not None:
            all_designs = []
            for p in input_paths:
                all_designs.extend(inspect_pdf_designs(p))
            if not all_designs:
                raise ValueError("Stiker dizaynlari topilmadi.")
            chosen_idx = max(0, min(design_index, len(all_designs) - 1))
            results = [
                engine.process_design_info(
                    all_designs[chosen_idx],
                    output_dir=outputs_dir,
                    config=config,
                    custom_gear=custom_gear,
                    custom_copies=custom_copies,
                )
            ]
        elif combine_same_gear:
            overrides = {str(p): (custom_gear, custom_copies) for p in input_paths}
            results = engine.process_batch_combined_by_gear(
                input_paths,
                output_dir=outputs_dir,
                config=config,
                overrides=overrides,
                group_by_file=separate_by_file,
            )
        else:
            results = []
            for p in input_paths:
                results.extend(
                    engine.process_all_designs_in_file(
                        p,
                        output_dir=outputs_dir,
                        config=config,
                        custom_gear=custom_gear,
                        custom_copies=custom_copies,
                    )
                )

        pdf_outputs: List[Path] = []
        seen: set[str] = set()
        for res in results:
            for out_f in res.output_files:
                if out_f.suffix.lower() == ".pdf" and out_f.name not in seen and out_f.is_file():
                    seen.add(out_f.name)
                    pdf_outputs.append(out_f)

        if not pdf_outputs:
            raise ValueError("Preview uchun PDF natija hosil bo'lmadi.")

        if len(pdf_outputs) == 1:
            return pdf_outputs[0].read_bytes(), 1

        merged = pymupdf.open()
        try:
            for pdf_p in pdf_outputs:
                part = pymupdf.open(str(pdf_p))
                try:
                    merged.insert_pdf(part)
                finally:
                    part.close()
            page_count = len(merged)
            return merged.tobytes(deflate=True), page_count
        finally:
            merged.close()


def _render_pdf_preview(pdf_path: Path, out_png: Path, dpi: int = 120) -> Optional[str]:
    try:
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            # Limit max pixel size for very tall narrow strips
            zoom = min(dpi / 72.0, 1400.0 / max(page.rect.width, page.rect.height, 1.0))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            pix.save(str(out_png))
            return out_png.name
        finally:
            doc.close()
    except Exception:
        return None


def run_label_imposition_job(
    uploaded_files: Optional[List[Tuple[str, bytes]]] = None,
    from_job_id: Optional[str] = None,
    from_filename: Optional[str] = None,
    custom_gear: Optional[int] = None,
    custom_copies: Optional[int] = None,
    rotation_mode: str = "auto",
    combine_same_gear: bool = True,
    separate_by_file: bool = False,
    separate_colors: bool = True,
    color_output_mode: str = "side_by_side",
    remove_outer_border: bool = True,
    regmark_enabled: bool = True,
    regmark_stroke_mm: float = 0.2,
    regmark_tick_mm: float = 0.7,
    regmark_custom_width_mm: Optional[float] = None,
    column_gap_mm: float = 5.0,
    max_cylinder_width_mm: float = 0.0,
    export_svg: bool = False,
    export_eps: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Run Label Imposition on uploaded PDFs or directly on a previous Sela job output."""
    def _report(cur: int, tot: int, msg: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(cur, tot, msg)
            except Exception:
                pass

    _report(0, 1, "Fayllar qabul qilinmoqda...")
    job_id, job_dir = create_job("label_imp")
    inputs_dir = job_dir / "inputs"
    outputs_dir = job_dir / "outputs"

    input_paths: List[Path] = []
    if from_job_id and from_filename:
        src = get_job_output_file(from_job_id, from_filename)
        dst = inputs_dir / src.name
        shutil.copy2(src, dst)
        input_paths.append(dst)

    for idx, (fname, raw) in enumerate(uploaded_files or [], start=1):
        safe = Path(fname).name
        if not safe.lower().endswith(".pdf"):
            continue
        dst = inputs_dir / safe
        if dst.exists():
            dst = inputs_dir / f"{dst.stem}_{idx}{dst.suffix}"
        dst.write_bytes(raw)
        input_paths.append(dst)

    if not input_paths:
        raise ValueError("Kamida bitta PDF fayl yuklang yoki Sela natijasidan yuboring.")

    config = ImpositionConfig(
        remove_outer_border=remove_outer_border,
        separate_colors=separate_colors,
        color_output_mode=color_output_mode,
        rotation_mode=rotation_mode,
        regmark_enabled=regmark_enabled,
        regmark_stroke_mm=regmark_stroke_mm,
        regmark_tick_mm=regmark_tick_mm,
        regmark_custom_width_mm=regmark_custom_width_mm if (regmark_custom_width_mm and regmark_custom_width_mm > 0) else None,
        column_gap_mm=column_gap_mm,
        max_cylinder_width_mm=max_cylinder_width_mm,
        export_svg=export_svg,
        export_eps=export_eps,
    )

    gm = _get_gear_manager()
    engine = ImpositionEngine(gm)

    _report(0, max(1, len(input_paths)), f"{len(input_paths)} ta PDF fayl tahlil qilinmoqda...")

    if combine_same_gear:
        overrides = {str(p): (custom_gear, custom_copies) for p in input_paths}
        results = engine.process_batch_combined_by_gear(
            input_paths,
            output_dir=outputs_dir,
            config=config,
            overrides=overrides,
            progress_callback=_report,
            group_by_file=separate_by_file,
        )
    else:
        all_designs = []
        for idx, p in enumerate(input_paths, start=1):
            _report(idx, len(input_paths) + 1, f"Fayl tahlil qilinmoqda ({idx}/{len(input_paths)}): {p.name}")
            all_designs.extend(inspect_pdf_designs(p))
        total_d = max(1, len(all_designs))
        results = []
        src_docs: Dict[Path, pymupdf.Document] = {}
        try:
            for idx, d in enumerate(all_designs, start=1):
                _report(idx - 1, total_d, f"[{idx}/{total_d}] Montaj qilinmoqda: {d.display_name}...")
                if d.file_path not in src_docs:
                    src_docs[d.file_path] = pymupdf.open(d.file_path)
                results.append(
                    engine.process_design_info(
                        d,
                        output_dir=outputs_dir,
                        config=config,
                        custom_gear=custom_gear,
                        custom_copies=custom_copies,
                        src_doc=src_docs[d.file_path],
                    )
                )
        finally:
            for sd in src_docs.values():
                try:
                    sd.close()
                except Exception:
                    pass
        _report(total_d, total_d, "Barcha stikerlar montaj qilindi!")

    unique_outputs: List[Path] = []
    seen_out: set[str] = set()
    items_summary: List[Dict[str, Any]] = []

    for res in results:
        for out_f in res.output_files:
            if out_f.name not in seen_out and out_f.is_file():
                seen_out.add(out_f.name)
                unique_outputs.append(out_f)

        items_summary.append({
            "design_name": res.design_info.display_name,
            "width_mm": round(res.effective_width_mm, 2),
            "length_mm": round(res.effective_length_mm, 2),
            "rotation_deg": res.rotation_deg,
            "has_outer_border": res.design_info.has_outer_border,
            "gear": res.gear_match.gear,
            "copies": res.gear_match.copies_count,
            "printing_length_mm": round(res.gear_match.printing_length_mm, 2),
            "film_length_mm": round(res.gear_match.film_length_mm, 2),
            "colors": [c.name for c in res.detected_colors],
            "grayscale_passed": res.audit_report.passed if res.audit_report else True,
            "output_files": [f.name for f in res.output_files],
        })

    output_meta: List[Dict[str, Any]] = []
    for p in unique_outputs:
        is_pdf = p.suffix.lower() == ".pdf"
        output_meta.append({
            "filename": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "ext": p.suffix.lower().lstrip("."),
            "preview_file": p.name if is_pdf else None,
        })

    zip_filename = None
    if len(unique_outputs) > 1:
        _report(99, 100, f"ZIP arxiv tayyorlanmoqda ({len(unique_outputs)} ta fayl)...")
        zip_path = bundle_job_outputs_zip(job_id, [p.name for p in unique_outputs])
        zip_filename = zip_path.name

    payload = {
        "job_id": job_id,
        "tool": "label_imp",
        "source_job_id": from_job_id,
        "designs_count": len(items_summary),
        "designs": items_summary,
        "output_files": output_meta,
        "zip_file": zip_filename,
        "outputs": [p.name for p in unique_outputs],
    }
    save_job_meta(job_id, payload)
    _report(100, 100, "Montaj muvaffaqiyatli yakunlandi!")
    return payload


_LABEL_IMP_RUNS_LOCK = threading.Lock()
_LABEL_IMP_RUNS: Dict[str, Dict[str, Any]] = {}


def _prune_old_runs(max_age_sec: float = 3600.0, max_entries: int = 50) -> None:
    now = time.time()
    stale = [
        rid
        for rid, rec in _LABEL_IMP_RUNS.items()
        if rec["status"] != "running" and (now - rec["updated_at"]) > max_age_sec
    ]
    for rid in stale:
        _LABEL_IMP_RUNS.pop(rid, None)
    if len(_LABEL_IMP_RUNS) > max_entries:
        finished = sorted(
            ((rec["updated_at"], rid) for rid, rec in _LABEL_IMP_RUNS.items() if rec["status"] != "running")
        )
        for _, rid in finished[: len(_LABEL_IMP_RUNS) - max_entries]:
            _LABEL_IMP_RUNS.pop(rid, None)


def start_label_imposition_run(**kwargs: Any) -> Dict[str, Any]:
    """Start label imposition in a background thread and return a pollable run_id."""
    uploaded_files = kwargs.get("uploaded_files") or []
    from_job_id = kwargs.get("from_job_id")
    from_filename = kwargs.get("from_filename")
    has_pdf = any(Path(fn).name.lower().endswith(".pdf") for fn, _ in uploaded_files)
    if not has_pdf and not (from_job_id and from_filename):
        raise ValueError("Kamida bitta PDF fayl yuklang yoki Sela natijasidan yuboring.")

    run_id = uuid.uuid4().hex[:12]
    now = time.time()
    record: Dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "current": 0,
        "total": 1,
        "percent": 0,
        "message": "Montaj boshlanmoqda...",
        "started_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
    }
    with _LABEL_IMP_RUNS_LOCK:
        _prune_old_runs()
        _LABEL_IMP_RUNS[run_id] = record

    def _on_progress(cur: int, tot: int, msg: str) -> None:
        safe_tot = max(1, int(tot))
        safe_cur = max(0, min(int(cur), safe_tot))
        pct = int(round((safe_cur / safe_tot) * 100))
        with _LABEL_IMP_RUNS_LOCK:
            rec = _LABEL_IMP_RUNS.get(run_id)
            if rec is not None and rec["status"] == "running":
                rec["current"] = safe_cur
                rec["total"] = safe_tot
                rec["percent"] = min(99, pct)
                rec["message"] = msg
                rec["updated_at"] = time.time()

    def _worker() -> None:
        try:
            res = run_label_imposition_job(**kwargs, progress_callback=_on_progress)
            with _LABEL_IMP_RUNS_LOCK:
                rec = _LABEL_IMP_RUNS.get(run_id)
                if rec is not None:
                    rec["status"] = "done"
                    rec["percent"] = 100
                    rec["current"] = rec["total"]
                    rec["message"] = "Montaj muvaffaqiyatli yakunlandi!"
                    rec["result"] = res
                    rec["updated_at"] = time.time()
        except Exception as exc:
            with _LABEL_IMP_RUNS_LOCK:
                rec = _LABEL_IMP_RUNS.get(run_id)
                if rec is not None:
                    rec["status"] = "error"
                    rec["error"] = str(exc)
                    rec["message"] = str(exc)
                    rec["updated_at"] = time.time()

    thread = threading.Thread(target=_worker, name=f"label-imp-{run_id}", daemon=True)
    thread.start()
    return {"run_id": run_id}


def get_label_imposition_run(run_id: str) -> Dict[str, Any]:
    with _LABEL_IMP_RUNS_LOCK:
        rec = _LABEL_IMP_RUNS.get(run_id)
        if rec is None:
            raise KeyError(f"Montaj jarayoni topilmadi: {run_id}")
        elapsed = (
            rec["updated_at"] - rec["started_at"]
            if rec["status"] != "running"
            else time.time() - rec["started_at"]
        )
        return {
            "run_id": rec["run_id"],
            "status": rec["status"],
            "current": rec["current"],
            "total": rec["total"],
            "percent": rec["percent"],
            "message": rec["message"],
            "elapsed_sec": round(max(0.0, elapsed), 1),
            "result": rec["result"],
            "error": rec["error"],
        }
