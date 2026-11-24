"""Service wrapper for Smart PDF Design & Dieline Extractor."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from app.jobs import bundle_job_outputs_zip, create_job, get_job_dir, save_job_meta
from engines.design_extractor.extractor_engine import (
    detect_page_candidates,
    extract_region_to_pdf_doc,
    pt_to_mm,
    search_candidates_by_size,
)


def _render_page_png(page: pymupdf.Page, out_path: Path, max_px: int = 1600) -> Tuple[int, int]:
    rect = page.cropbox if not page.cropbox.is_empty else page.rect
    max_side = max(rect.width, rect.height, 1.0)
    zoom = min(2.2, max_px / max_side)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    pix.save(str(out_path))
    return pix.width, pix.height


def _find_source_pdf_in_job(source_job_id: str) -> Path:
    job_dir = get_job_dir(source_job_id)
    in_dir = job_dir / "inputs"
    pdfs = sorted(in_dir.glob("*.pdf"))
    if not pdfs:
        out_pdfs = sorted((job_dir / "outputs").glob("source_*.pdf"))
        if out_pdfs:
            return out_pdfs[0]
        raise FileNotFoundError("Yuklangan asl PDF fayl topilmadi.")
    return pdfs[0]


def inspect_pdf_for_extraction(
    filename: str,
    raw_bytes: bytes,
    target_w_mm: Optional[float] = None,
    target_h_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Saves the uploaded PDF into a new inspection job, renders page previews,
    and runs smart vector detection on every page to propose Designs and Dielines.
    """
    safe_name = Path(filename or "document.pdf").name
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"

    job_id, job_dir = create_job("extractor_src")
    in_dir = job_dir / "inputs"
    out_dir = job_dir / "outputs"

    pdf_path = in_dir / safe_name
    pdf_path.write_bytes(raw_bytes)

    target_size = (target_w_mm, target_h_mm) if (target_w_mm and target_h_mm and target_w_mm > 0 and target_h_mm > 0) else None

    doc = pymupdf.open(str(pdf_path))
    try:
        pages_meta: List[Dict[str, Any]] = []
        all_candidates: List[Dict[str, Any]] = []

        for pno in range(len(doc)):
            page = doc[pno]
            page_rect = page.cropbox if not page.cropbox.is_empty else page.rect
            w_mm = round(pt_to_mm(page_rect.width), 2)
            h_mm = round(pt_to_mm(page_rect.height), 2)

            preview_name = f"page_{pno + 1:02d}.png"
            preview_path = out_dir / preview_name
            px_w, px_h = _render_page_png(page, preview_path)

            candidates, dim_hints = detect_page_candidates(
                page,
                page_index=pno,
                target_size_mm=target_size,
            )
            cand_dicts = [c.to_dict() for c in candidates]
            all_candidates.extend(cand_dicts)

            pages_meta.append({
                "page_index": pno,
                "page_number": pno + 1,
                "width_mm": w_mm,
                "height_mm": h_mm,
                "preview_file": preview_name,
                "preview_px": [px_w, px_h],
                "dimension_hints": [[round(a, 1), round(b, 1)] for a, b in dim_hints],
                "candidates_count": len(cand_dicts),
                "designs_count": sum(1 for c in cand_dicts if c["role"] == "design"),
                "dielines_count": sum(1 for c in cand_dicts if c["role"] == "dieline"),
            })

        payload = {
            "source_job_id": job_id,
            "filename": safe_name,
            "page_count": len(doc),
            "pages": pages_meta,
            "candidates": all_candidates,
        }
        save_job_meta(job_id, payload)
        return payload
    finally:
        doc.close()


def search_pdf_by_dimensions(
    source_job_id: str,
    width_mm: float,
    height_mm: float,
    tolerance_mm: float = 3.0,
    page_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Searches a previously uploaded PDF in `source_job_id` for vector shapes matching `width_mm x height_mm`.
    """
    pdf_path = _find_source_pdf_in_job(source_job_id)
    doc = pymupdf.open(str(pdf_path))
    try:
        found: List[Dict[str, Any]] = []
        pages_to_scan = [page_index] if (page_index is not None and 0 <= page_index < len(doc)) else list(range(len(doc)))
        for pno in pages_to_scan:
            matches = search_candidates_by_size(
                doc[pno],
                page_index=pno,
                target_w_mm=width_mm,
                target_h_mm=height_mm,
                tol_mm=tolerance_mm,
            )
            for m in matches:
                found.append(m.to_dict())
        return {
            "source_job_id": source_job_id,
            "target_mm": [width_mm, height_mm],
            "found_count": len(found),
            "candidates": found,
        }
    finally:
        doc.close()


def _sanitize_stem(text: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "item"


def run_extraction_job(
    source_job_id: str,
    items: List[Dict[str, Any]],
    remove_border: bool = False,
    remove_hole: bool = False,
    bleed_mm: float = 0.0,
    rotation_deg: int = 0,
) -> Dict[str, Any]:
    """
    Surgically extracts all user-selected items (`design` and `dieline` regions) into:
    - Individual 1-page vector PDFs (`01_design_50x120mm.pdf`, `02_dieline_50x120mm.pdf`, ...)
    - Combined multi-page vector PDF of all designs (`all_designs.pdf`)
    - Combined multi-page vector PDF of all items if both designs & dielines exist (`all_extracted.pdf`)
    - PNG thumbnails for instant visual verification
    - ZIP archive of all generated vector files
    """
    if not items:
        raise ValueError("Ajratib olish uchun kamida bitta dizayn yoki pichoqni tanlang.")

    src_pdf_path = _find_source_pdf_in_job(source_job_id)
    base_stem = _sanitize_stem(src_pdf_path.stem)[:24]

    job_id, job_dir = create_job("extractor")
    out_dir = job_dir / "outputs"

    extracted_items_meta: List[Dict[str, Any]] = []
    output_files_meta: List[Dict[str, Any]] = []
    design_filenames: List[str] = []
    dieline_filenames: List[str] = []

    merged_designs_doc = pymupdf.open()
    merged_all_doc = pymupdf.open()

    try:
        for idx, item in enumerate(items, start=1):
            pno = int(item.get("page_index", 0))
            role = str(item.get("role", "design")).lower()
            if role not in ("design", "dieline"):
                role = "design"

            bbox_raw = item.get("bbox_mm")
            if not bbox_raw or len(bbox_raw) != 4:
                raise ValueError(f"Element #{idx} koordinatalari noto'g'ri.")
            bbox_mm = (
                float(bbox_raw[0]),
                float(bbox_raw[1]),
                float(bbox_raw[2]),
                float(bbox_raw[3]),
            )

            item_remove_border = bool(item.get("remove_border", remove_border))
            # Never remove outer border on a dieline (otherwise the cut contour itself disappears!)
            if role == "dieline":
                item_remove_border = False

            item_remove_hole = bool(item.get("remove_hole", remove_hole)) if role == "design" else False
            item_bleed_mm = float(item.get("bleed_mm", bleed_mm)) if role == "design" else 0.0
            item_rot = int(item.get("rotation_deg", rotation_deg))

            single_doc, out_w_mm, out_h_mm = extract_region_to_pdf_doc(
                pdf_path=src_pdf_path,
                page_index=pno,
                bbox_mm=bbox_mm,
                remove_border=item_remove_border,
                remove_hole=item_remove_hole,
                bleed_mm=item_bleed_mm,
                rotation_deg=item_rot,
            )
            try:
                dim_tag = f"{out_w_mm:g}x{out_h_mm:g}mm".replace(".", "_")
                role_tag = "dizayn" if role == "design" else "pichoq"
                pdf_fname = f"{idx:02d}_{base_stem}_{role_tag}_{dim_tag}.pdf"
                pdf_out_path = out_dir / pdf_fname
                single_doc.save(str(pdf_out_path), garbage=3, deflate=True)

                thumb_fname = f"{idx:02d}_thumb.png"
                _render_page_png(single_doc[0], out_dir / thumb_fname, max_px=600)

                merged_all_doc.insert_pdf(single_doc)
                if role == "design":
                    merged_designs_doc.insert_pdf(single_doc)
                    design_filenames.append(pdf_fname)
                else:
                    dieline_filenames.append(pdf_fname)

                size_kb = round(pdf_out_path.stat().st_size / 1024, 1)
                output_files_meta.append({
                    "filename": pdf_fname,
                    "size_kb": size_kb,
                    "role": role,
                    "width_mm": out_w_mm,
                    "height_mm": out_h_mm,
                    "preview_file": pdf_fname,
                    "thumb_file": thumb_fname,
                })
                extracted_items_meta.append({
                    "index": idx,
                    "id": item.get("id", f"item_{idx}"),
                    "label": item.get("label") or f"{role_tag.capitalize()} #{idx}",
                    "role": role,
                    "page_index": pno,
                    "width_mm": out_w_mm,
                    "height_mm": out_h_mm,
                    "bleed_mm": item_bleed_mm,
                    "filename": pdf_fname,
                    "thumb_file": thumb_fname,
                    "size_kb": size_kb,
                })
            finally:
                single_doc.close()

        combined_designs_file: Optional[str] = None
        if len(merged_designs_doc) > 1:
            combined_designs_file = f"00_{base_stem}_barcha_dizaynlar_{len(merged_designs_doc)}bet.pdf"
            c_path = out_dir / combined_designs_file
            merged_designs_doc.save(str(c_path), garbage=3, deflate=True)
            output_files_meta.insert(0, {
                "filename": combined_designs_file,
                "size_kb": round(c_path.stat().st_size / 1024, 1),
                "role": "combined_designs",
                "width_mm": extracted_items_meta[0]["width_mm"],
                "height_mm": extracted_items_meta[0]["height_mm"],
                "preview_file": combined_designs_file,
                "thumb_file": None,
            })

        combined_all_file: Optional[str] = None
        if len(merged_all_doc) > 1 and dieline_filenames and design_filenames:
            combined_all_file = f"00_{base_stem}_dizayn_va_pichoq_{len(merged_all_doc)}bet.pdf"
            a_path = out_dir / combined_all_file
            merged_all_doc.save(str(a_path), garbage=3, deflate=True)
            output_files_meta.insert(0, {
                "filename": combined_all_file,
                "size_kb": round(a_path.stat().st_size / 1024, 1),
                "role": "combined_all",
                "width_mm": extracted_items_meta[0]["width_mm"],
                "height_mm": extracted_items_meta[0]["height_mm"],
                "preview_file": combined_all_file,
                "thumb_file": None,
            })
    finally:
        merged_designs_doc.close()
        merged_all_doc.close()

    all_pdf_names = [f["filename"] for f in output_files_meta]
    zip_filename = None
    if len(all_pdf_names) > 1:
        zip_path = bundle_job_outputs_zip(job_id, all_pdf_names)
        zip_filename = zip_path.name

    # Primary file for single-file handoff (e.g. to Val Montaji)
    primary_design_pdf = combined_designs_file or (design_filenames[0] if design_filenames else all_pdf_names[0])

    payload = {
        "job_id": job_id,
        "tool": "extractor",
        "source_job_id": source_job_id,
        "source_filename": src_pdf_path.name,
        "items_count": len(extracted_items_meta),
        "items": extracted_items_meta,
        "output_files": output_files_meta,
        "design_files": design_filenames,
        "dieline_files": dieline_filenames,
        "combined_designs_file": combined_designs_file,
        "combined_all_file": combined_all_file,
        "primary_design_file": primary_design_pdf,
        "zip_file": zip_filename,
        "outputs": all_pdf_names,
    }
    save_job_meta(job_id, payload)
    return payload
