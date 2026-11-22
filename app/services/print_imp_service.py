"""Service wrapper for Print Imposition (Offset / Digital Sheet Imposition & Preflight)."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from app.config import ENGINES_DIR
from app.jobs import bundle_job_outputs_zip, create_job, save_job_meta

_PRINT_IMP_DIR = str(ENGINES_DIR / "print_imp")
if _PRINT_IMP_DIR not in sys.path:
    sys.path.insert(0, _PRINT_IMP_DIR)

from imposition.engine import ImpositionEngine as SheetImpositionEngine  # noqa: E402
from imposition.models import (  # noqa: E402
    BleedAndGutterConfig,
    GangingStrategy,
    GridFillDirection,
    GuillotineCutStyle,
    ImpositionMode,
    JobCategory,
    JobMetadata,
    SheetAlignment,
    SheetConfig,
    TemplateStyle,
)
from imposition.preflight import PreflightChecker  # noqa: E402


PRESETS: Dict[str, Dict[str, Any]] = {
    "guillotine_50x35": {
        "name": "Gilotin Ofset (500×350 mm)",
        "description": "Vizitka, flayer, blank — 2 ta pichoq, CMYK shkala va krestlar",
        "sheet_w": 500.0,
        "sheet_h": 350.0,
        "gripper": 15.0,
        "inner_bleed": 1.5,
        "outer_bleed": 3.0,
        "gutter": 3.0,
        "style": "offset_standard",
        "category": "guillotine",
        "cut_style": "double",
    },
    "packaging_50x35": {
        "name": "Qadoqlash / Pichoqli (500×350 mm)",
        "description": "Quti va shtantsli ishlar — qo'shaloq kroplar, alohida pichoq",
        "sheet_w": 500.0,
        "sheet_h": 350.0,
        "gripper": 15.0,
        "inner_bleed": 1.5,
        "outer_bleed": 3.0,
        "gutter": 3.0,
        "style": "packaging",
        "category": "diecut",
        "cut_style": "double",
    },
    "digital_sra3": {
        "name": "Raqamli SRA3 (450×320 mm)",
        "description": "Raqamli bosma — shkalasiz ixcham krop va qisqa pasport",
        "sheet_w": 450.0,
        "sheet_h": 320.0,
        "gripper": 10.0,
        "inner_bleed": 1.5,
        "outer_bleed": 2.0,
        "gutter": 3.0,
        "style": "digital_compact",
        "category": "guillotine",
        "cut_style": "double",
    },
    "offset_70x50": {
        "name": "Katta Ofset B2 (700×500 mm)",
        "description": "Katta formatli ofset mashinalar uchun standart montaj",
        "sheet_w": 700.0,
        "sheet_h": 500.0,
        "gripper": 15.0,
        "inner_bleed": 1.5,
        "outer_bleed": 3.0,
        "gutter": 3.0,
        "style": "standard",
        "category": "guillotine",
        "cut_style": "double",
    },
}


def run_preflight_analysis(
    front_files: List[Tuple[str, bytes]],
    dieline_file: Optional[Tuple[str, bytes]] = None,
    expected_trim_mm: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    """Run PreflightChecker on uploaded PDFs and auto-detect trim dimensions."""
    job_id, job_dir = create_job("preflight")
    in_dir = job_dir / "inputs"

    front_paths: List[str] = []
    for fname, raw in front_files:
        p = in_dir / Path(fname).name
        p.write_bytes(raw)
        front_paths.append(str(p))

    detected_dieline_trim = None
    if dieline_file:
        dp = in_dir / f"dieline_{Path(dieline_file[0]).name}"
        dp.write_bytes(dieline_file[1])
        tw, th, pw, ph = SheetImpositionEngine.detect_dieline_trim_mm(str(dp))
        detected_dieline_trim = {"trim_w_mm": tw, "trim_h_mm": th, "page_w_mm": pw, "page_h_mm": ph}
        if not expected_trim_mm:
            expected_trim_mm = (tw, th)

    checker = PreflightChecker(target_dpi=300.0)
    if len(front_paths) == 1:
        report = checker.check_pdf(front_paths[0], expected_trim_mm=expected_trim_mm)
    else:
        variants = SheetImpositionEngine.build_variants_from_files(front_paths)
        report = checker.check_multi_variants(variants, expected_trim_mm=expected_trim_mm)

    return {
        "page_count": report.page_count,
        "is_valid": report.is_valid,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "media_box_mm": [round(report.media_box_mm[0], 2), round(report.media_box_mm[1], 2)],
        "trim_box_mm": [round(report.trim_box_mm[0], 2), round(report.trim_box_mm[1], 2)],
        "detected_bleed_mm": round(report.detected_bleed_mm, 2),
        "dieline_trim": detected_dieline_trim,
        "has_rgb": report.has_rgb,
        "has_low_dpi": report.has_low_dpi,
        "colors": [{"name": c.name, "is_spot": c.is_spot} for c in report.colors],
        "images_count": len(report.images),
        "fonts_count": len(set(report.fonts)),
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "details": i.details,
                "page_num": i.page_num,
            }
            for i in report.issues
        ],
    }


def _render_sheet_preview(pdf_path: Path, out_png: Path) -> Optional[str]:
    try:
        doc = pymupdf.open(str(pdf_path))
        try:
            page = doc[0]
            zoom = min(1.5, 1100.0 / max(page.rect.width, page.rect.height, 1.0))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            pix.save(str(out_png))
            return out_png.name
        finally:
            doc.close()
    except Exception:
        return None


def run_print_imposition_job(
    front_files: List[Tuple[str, bytes]],
    back_file: Optional[Tuple[str, bytes]] = None,
    dieline_file: Optional[Tuple[str, bytes]] = None,
    sheet_w_mm: float = 500.0,
    sheet_h_mm: float = 350.0,
    trim_w_mm: Optional[float] = None,
    trim_h_mm: Optional[float] = None,
    bleed_mm: float = 1.5,
    inner_bleed_mm: float = 1.5,
    outer_bleed_mm: float = 3.0,
    gutter_mm: float = 3.0,
    gripper_mm: float = 15.0,
    crop_gap_mm: float = 1.0,
    mode: str = "single",
    style: str = "offset_standard",
    category: str = "guillotine",
    cut_style: str = "double",
    alignment: str = "center",
    order_number: str = "№1001",
    job_name: Optional[str] = None,
    order_quantity: int = 1000,
    waste_sheets: int = 0,
    separate_files: bool = False,
    multi_mode: str = "pages",
    quantities: Optional[List[int]] = None,
    strategy: str = "smart",
    max_overprint_pct: float = 10.0,
    fill_dir: str = "col",
) -> Dict[str, Any]:
    """Execute full vector sheet imposition and preflight inside a new job."""
    if not front_files:
        raise ValueError("Kamida bitta Oldi (Front) PDF fayl yuklang.")

    job_id, job_dir = create_job("print_imp")
    in_dir = job_dir / "inputs"
    out_dir = job_dir / "outputs"

    front_paths: List[str] = []
    for fname, raw in front_files:
        p = in_dir / Path(fname).name
        p.write_bytes(raw)
        front_paths.append(str(p))

    back_path: Optional[str] = None
    if back_file:
        bp = in_dir / f"back_{Path(back_file[0]).name}"
        bp.write_bytes(back_file[1])
        back_path = str(bp)

    dieline_path: Optional[str] = None
    if dieline_file:
        dp = in_dir / f"dieline_{Path(dieline_file[0]).name}"
        dp.write_bytes(dieline_file[1])
        dieline_path = str(dp)

    # Auto-detect trim size if not explicitly supplied
    if not trim_w_mm or not trim_h_mm:
        if dieline_path:
            tw, th, _, _ = SheetImpositionEngine.detect_dieline_trim_mm(dieline_path)
            trim_w_mm, trim_h_mm = tw, th
        else:
            doc = pymupdf.open(front_paths[0])
            try:
                tb = doc[0].trimbox
                trim_w_mm = round(tb.width * 25.4 / 72.0, 2)
                trim_h_mm = round(tb.height * 25.4 / 72.0, 2)
            finally:
                doc.close()

    is_multi = len(front_paths) > 1 or bool(quantities)
    # Also check if single PDF has multiple pages
    if not is_multi:
        d = pymupdf.open(front_paths[0])
        try:
            if len(d) > 1:
                is_multi = True
        finally:
            d.close()

    variants = None
    checker = PreflightChecker(target_dpi=300.0)
    if is_multi:
        variants = SheetImpositionEngine.build_variants_from_files(
            front_files=front_paths,
            multi_page_mode=multi_mode,
            shared_back_pdf=back_path,
            default_quantity=order_quantity,
        )
        if quantities:
            for i, v in enumerate(variants):
                if i < len(quantities) and quantities[i] > 0:
                    v.order_quantity = quantities[i]
        report = checker.check_multi_variants(variants, expected_trim_mm=(trim_w_mm, trim_h_mm))
    else:
        report = checker.check_pdf(front_paths[0], expected_trim_mm=(trim_w_mm, trim_h_mm))

    mode_map = {
        "single": ImpositionMode.SINGLE_SIDED,
        "single_sided": ImpositionMode.SINGLE_SIDED,
        "sheetwise": ImpositionMode.SHEETWISE,
        "turn": ImpositionMode.WORK_AND_TURN,
        "work_and_turn": ImpositionMode.WORK_AND_TURN,
        "tumble": ImpositionMode.WORK_AND_TUMBLE,
        "work_and_tumble": ImpositionMode.WORK_AND_TUMBLE,
    }
    style_map = {
        "standard": TemplateStyle.STANDARD_COLORBAR,
        "compact": TemplateStyle.COMPACT_SIDE_INFO,
        "packaging": TemplateStyle.PACKAGING_DIE_CUT,
        "offset_standard": TemplateStyle.OFFSET_STANDARD,
        "digital_compact": TemplateStyle.DIGITAL_COMPACT,
    }
    strat_map = {
        "smart": GangingStrategy.SMART_NO_SPLIT,
        "split": GangingStrategy.MAX_ECONOMY_SPLIT,
        "single": GangingStrategy.SINGLE_FORM_PROPORTIONAL,
    }
    fill_map = {
        "col": GridFillDirection.COL_BY_COL,
        "row": GridFillDirection.ROW_BY_ROW,
    }

    sheet_cfg = SheetConfig(
        width_mm=sheet_w_mm,
        height_mm=sheet_h_mm,
        margin_bottom_mm=gripper_mm,
    )
    bg_cfg = BleedAndGutterConfig(
        trim_width_mm=trim_w_mm,
        trim_height_mm=trim_h_mm,
        bleed_mm=bleed_mm,
        inner_bleed_mm=inner_bleed_mm,
        outer_bleed_mm=outer_bleed_mm,
        crop_gap_mm=crop_gap_mm,
        gutter_x_mm=gutter_mm,
        gutter_y_mm=gutter_mm,
        alignment=SheetAlignment.GRIPPER if alignment == "gripper" else SheetAlignment.CENTER,
    )

    total_qty = sum(v.order_quantity for v in variants) if variants else order_quantity
    safe_job_name = (job_name or Path(front_paths[0]).stem).strip()
    job_meta = JobMetadata(
        order_number=order_number,
        job_name=safe_job_name,
        date_str=datetime.date.today().strftime("%d.%m.%Y"),
        order_quantity=total_qty,
        waste_sheets=waste_sheets,
        colors=report.colors,
        sheet_form_str=f"{int(round(sheet_w_mm / 10))}x{int(round(sheet_h_mm / 10))}sm",
        category=JobCategory.DIE_CUT if category == "diecut" else JobCategory.GUILLOTINE,
        cut_style=GuillotineCutStyle.SINGLE_CUT if cut_style == "single" else GuillotineCutStyle.DOUBLE_CUT,
    )

    out_pdf = out_dir / f"montaj_{safe_job_name[:32]}.pdf"
    engine = SheetImpositionEngine()
    res = engine.run_imposition(
        front_pdf_path=front_paths[0] if not variants else None,
        back_pdf_path=back_path,
        dieline_pdf_path=dieline_path,
        sheet=sheet_cfg,
        bg_config=bg_cfg,
        mode=mode_map.get(mode, ImpositionMode.SINGLE_SIDED),
        style=style_map.get(style, TemplateStyle.OFFSET_STANDARD),
        job=job_meta,
        output_path=str(out_pdf),
        export_separate_files=separate_files,
        variants=variants,
        ganging_strategy=strat_map.get(strategy, GangingStrategy.SMART_NO_SPLIT),
        max_overprint_pct=max_overprint_pct,
        fill_direction=fill_map.get(fill_dir, GridFillDirection.COL_BY_COL),
    )

    gen_paths = [Path(p) for p in res.get("generated_files", []) if Path(p).is_file()]
    output_meta: List[Dict[str, Any]] = []
    for p in gen_paths:
        is_pdf = p.suffix.lower() == ".pdf"
        output_meta.append({
            "filename": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "preview_file": p.name if is_pdf else None,
        })

    zip_filename = None
    if len(gen_paths) > 1:
        zip_path = bundle_job_outputs_zip(job_id, [p.name for p in gen_paths])
        zip_filename = zip_path.name

    form_plans_summary = []
    for fp in res.get("form_plans") or []:
        form_plans_summary.append({
            "form_index": fp.form_index,
            "sheet_run": fp.sheet_run,
            "total_sheets_with_waste": fp.total_sheets_with_waste,
            "summary": fp.summary_str(),
        })

    payload = {
        "job_id": job_id,
        "tool": "print_imp",
        "cols": res["cols"],
        "rows": res["rows"],
        "items_per_sheet": res["items_per_sheet"],
        "rotation": res["rotation"],
        "trim_mm": [trim_w_mm, trim_h_mm],
        "sheet_mm": [sheet_w_mm, sheet_h_mm],
        "total_quantity": total_qty,
        "calculated_sheets": res["calculated_sheets"],
        "form_plans": form_plans_summary,
        "preflight": {
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "colors": [c.name for c in report.colors],
            "issues": [
                {"severity": i.severity, "category": i.category, "message": i.message}
                for i in report.issues
            ],
        },
        "output_files": output_meta,
        "zip_file": zip_filename,
        "outputs": [p.name for p in gen_paths],
    }
    save_job_meta(job_id, payload)
    return payload
