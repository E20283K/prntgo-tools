"""
Smart Vector PDF Design & Dieline Extractor Engine.
- Detects filled artwork designs (hangtags, labels, packaging, cards) and unfilled dielines/cut-contours
  from technical passport pages, multi-item brandbooks, or composite vector sheets.
- Filters out header banners, dimension arrows, callout lines, Pantone color swatches, and text paragraphs.
- Extracts dimension hints from page text (e.g., "50x120мм", "50х120 мм") to score matching candidates.
- Surgically isolates selected bounding boxes in PDF content streams without `re W n` clipping masks,
  supporting optional outer border removal, punch-hole removal, background bleed extension, and rotation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0


def mm_to_pt(mm: float) -> float:
    return mm * PT_PER_MM


def pt_to_mm(pt: float) -> float:
    return pt * MM_PER_PT


@dataclass
class DetectedHole:
    center_x_mm: float
    center_y_mm: float
    diameter_mm: float
    rect_pt: pymupdf.Rect


@dataclass
class DetectedCandidate:
    id: str
    page_index: int
    role: str  # "design" | "dieline"
    label: str
    bbox_mm: Tuple[float, float, float, float]  # (x0_mm, y0_mm, x1_mm, y1_mm) relative to page cropbox
    width_mm: float
    height_mm: float
    has_outer_border: bool
    has_fill: bool
    fill_color_hex: Optional[str]
    fill_color_raw: Optional[Tuple[float, ...]]
    interior_paths_count: int
    interior_texts_count: int
    holes: List[DetectedHole] = field(default_factory=list)
    confidence: float = 0.8
    matches_text_hint: bool = False
    selected_by_default: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "page_index": self.page_index,
            "role": self.role,
            "label": self.label,
            "bbox_mm": [round(x, 2) for x in self.bbox_mm],
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "has_outer_border": self.has_outer_border,
            "has_fill": self.has_fill,
            "fill_color_hex": self.fill_color_hex,
            "interior_paths_count": self.interior_paths_count,
            "interior_texts_count": self.interior_texts_count,
            "has_hole": len(self.holes) > 0,
            "holes_count": len(self.holes),
            "holes": [
                {
                    "center_x_mm": round(h.center_x_mm, 2),
                    "center_y_mm": round(h.center_y_mm, 2),
                    "diameter_mm": round(h.diameter_mm, 2),
                }
                for h in self.holes
            ],
            "confidence": round(self.confidence, 2),
            "matches_text_hint": self.matches_text_hint,
            "selected_by_default": self.selected_by_default,
        }


def _color_tuple_to_hex(color: Optional[Tuple[float, ...]]) -> Optional[str]:
    if not color:
        return None
    if len(color) == 1:
        g = max(0, min(255, int(round(color[0] * 255))))
        return f"#{g:02x}{g:02x}{g:02x}"
    if len(color) == 3:
        r = max(0, min(255, int(round(color[0] * 255))))
        g = max(0, min(255, int(round(color[1] * 255))))
        b = max(0, min(255, int(round(color[2] * 255))))
        return f"#{r:02x}{g:02x}{b:02x}"
    if len(color) == 4:
        c, m, y, k = color
        r = max(0, min(255, int(round(255 * (1.0 - c) * (1.0 - k)))))
        g = max(0, min(255, int(round(255 * (1.0 - m) * (1.0 - k)))))
        b = max(0, min(255, int(round(255 * (1.0 - y) * (1.0 - k)))))
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _is_white_or_none(color: Optional[Tuple[float, ...]]) -> bool:
    if color is None:
        return True
    if len(color) == 1:
        return color[0] >= 0.97
    if len(color) == 3:
        return all(c >= 0.97 for c in color)
    if len(color) == 4:
        return all(c <= 0.03 for c in color)
    return False


def _is_closed_box_like_drawing(drawing: dict, tol_pt: float = 2.0) -> bool:
    """
    Returns True if a PyMuPDF drawing represents a closed rectangle or rounded rectangle
    (either filled or stroked).
    """
    rect: pymupdf.Rect = drawing.get("rect")
    if rect is None or rect.is_empty:
        return False

    w_mm = pt_to_mm(rect.width)
    h_mm = pt_to_mm(rect.height)
    if min(w_mm, h_mm) < 8.0 or max(w_mm, h_mm) < 12.0:
        return False

    items = drawing.get("items", [])
    if not items:
        return False

    if len(items) == 1 and items[0][0] in ("re", "qu"):
        return True

    # Reject paths with huge numbers of segments (like complex logos or text outlines)
    if len(items) > 24:
        return False

    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    corner_tol = min(rect.width, rect.height) * 0.42
    has_left = has_right = has_top = has_bottom = False

    for it in items:
        kind = it[0]
        if kind == "re":
            return True
        elif kind == "l":
            pts = [it[1], it[2]]
        elif kind == "c":
            pts = [it[1], it[2], it[3], it[4]]
        elif kind == "qu":
            q = it[1]
            pts = [q.ul, q.ur, q.ll, q.lr]
        else:
            return False

        for p in pts:
            on_x = (abs(p.x - x0) <= tol_pt) or (abs(p.x - x1) <= tol_pt)
            on_y = (abs(p.y - y0) <= tol_pt) or (abs(p.y - y1) <= tol_pt)
            in_corner = (
                (p.x - x0 <= corner_tol or x1 - p.x <= corner_tol)
                and (p.y - y0 <= corner_tol or y1 - p.y <= corner_tol)
            )
            if not (on_x or on_y or in_corner):
                return False

            if abs(p.x - x0) <= tol_pt:
                has_left = True
            if abs(p.x - x1) <= tol_pt:
                has_right = True
            if abs(p.y - y0) <= tol_pt:
                has_top = True
            if abs(p.y - y1) <= tol_pt:
                has_bottom = True

    return has_left and has_right and has_top and has_bottom


def _is_small_circle_or_hole(drawing: dict, parent_rect: pymupdf.Rect) -> Optional[DetectedHole]:
    """
    Checks if `drawing` is a small circular punch hole (e.g. 2..12 mm diameter) inside `parent_rect`.
    """
    r: pymupdf.Rect = drawing.get("rect")
    if r is None or r.is_empty:
        return None
    if not _rect_strictly_inside(parent_rect, r, margin_pt=1.5):
        return None

    w_mm = pt_to_mm(r.width)
    h_mm = pt_to_mm(r.height)
    if not (1.5 <= w_mm <= 14.0 and 1.5 <= h_mm <= 14.0):
        return None
    if abs(w_mm - h_mm) > max(1.2, 0.25 * max(w_mm, h_mm)):
        return None

    items = drawing.get("items", [])
    if not items or len(items) > 12:
        return None

    # Usually a circle is 4 bezier curves (`c`) or a rounded rect
    curve_count = sum(1 for it in items if it[0] == "c")
    if curve_count < 2 and not (len(items) == 1 and items[0][0] == "re"):
        return None

    fill = drawing.get("fill")
    stroke = drawing.get("color")
    # A punch hole is either unfilled outline or white-filled dot
    if not _is_white_or_none(fill) and stroke is None:
        return None

    cx_mm = pt_to_mm((r.x0 + r.x1) / 2.0 - parent_rect.x0)
    cy_mm = pt_to_mm((r.y0 + r.y1) / 2.0 - parent_rect.y0)
    diam_mm = (w_mm + h_mm) / 2.0
    return DetectedHole(
        center_x_mm=cx_mm,
        center_y_mm=cy_mm,
        diameter_mm=diam_mm,
        rect_pt=pymupdf.Rect(r),
    )


def _rect_contains(outer: pymupdf.Rect, inner: pymupdf.Rect, tol_pt: float = 2.0) -> bool:
    return (
        outer.x0 <= inner.x0 + tol_pt
        and outer.y0 <= inner.y0 + tol_pt
        and outer.x1 >= inner.x1 - tol_pt
        and outer.y1 >= inner.y1 - tol_pt
    )


def _rect_strictly_inside(outer: pymupdf.Rect, inner: pymupdf.Rect, margin_pt: float = 1.0) -> bool:
    return (
        outer.x0 + margin_pt <= inner.x0
        and outer.y0 + margin_pt <= inner.y0
        and outer.x1 - margin_pt >= inner.x1
        and outer.y1 - margin_pt >= inner.y1
    )


def _rect_nearly_equal(r1: pymupdf.Rect, r2: pymupdf.Rect, tol_pt: float = 2.5) -> bool:
    return (
        abs(r1.x0 - r2.x0) <= tol_pt
        and abs(r1.y0 - r2.y0) <= tol_pt
        and abs(r1.x1 - r2.x1) <= tol_pt
        and abs(r1.y1 - r2.y1) <= tol_pt
    )


_DIM_PAIR_RE = re.compile(
    r"(?<!\d)(\d{2,3}(?:[.,]\d+)?)\s*[xхXХ×*]\s*(\d{2,3}(?:[.,]\d+)?)\s*(?:мм|mm|см|cm)?",
    re.IGNORECASE,
)
_SINGLE_DIM_RE = re.compile(
    r"(?<!\d)(\d{2,3}(?:[.,]\d+)?)\s*(?:мм|mm)\b",
    re.IGNORECASE,
)


def extract_dimension_hints_from_text(page_text: str) -> List[Tuple[float, float]]:
    """
    Extracts explicit dimension pairs (e.g. "50x120мм", "50 x 120 mm") or combinations of
    standalone dimension callouts ("50 mm", "120 mm") from page text.
    """
    hints: List[Tuple[float, float]] = []
    seen: set[Tuple[int, int]] = set()

    for m in _DIM_PAIR_RE.finditer(page_text):
        try:
            a = float(m.group(1).replace(",", "."))
            b = float(m.group(2).replace(",", "."))
            # Avoid matching paper grammar like "230+230gr/m2"
            if 8.0 <= a <= 1000.0 and 8.0 <= b <= 1000.0:
                key = (int(round(min(a, b))), int(round(max(a, b))))
                if key not in seen:
                    seen.add(key)
                    hints.append((a, b))
        except ValueError:
            continue

    single_vals: List[float] = []
    for m in _SINGLE_DIM_RE.finditer(page_text):
        try:
            v = float(m.group(1).replace(",", "."))
            if 10.0 <= v <= 600.0 and all(abs(v - x) > 0.5 for x in single_vals):
                single_vals.append(v)
        except ValueError:
            continue

    if len(single_vals) >= 2:
        for i in range(len(single_vals)):
            for j in range(i + 1, len(single_vals)):
                a, b = single_vals[i], single_vals[j]
                key = (int(round(min(a, b))), int(round(max(a, b))))
                if key not in seen:
                    seen.add(key)
                    hints.append((a, b))

    return hints


def _matches_any_dimension_hint(
    w_mm: float,
    h_mm: float,
    hints: List[Tuple[float, float]],
    tol_mm: float = 2.0,
) -> bool:
    for hw, hh in hints:
        if (abs(w_mm - hw) <= tol_mm and abs(h_mm - hh) <= tol_mm) or (
            abs(w_mm - hh) <= tol_mm and abs(h_mm - hw) <= tol_mm
        ):
            return True
    return False


def detect_page_candidates(
    page: pymupdf.Page,
    page_index: int = 0,
    target_size_mm: Optional[Tuple[float, float]] = None,
) -> Tuple[List[DetectedCandidate], List[Tuple[float, float]]]:
    """
    Analyzes a single PDF page and detects all artwork Designs and Dieline contours.
    Automatically filters out page borders, header banners, Pantone swatches, and dimension arrows.
    """
    page_rect = page.cropbox if not page.cropbox.is_empty else page.rect
    page_w_mm = pt_to_mm(page_rect.width)
    page_h_mm = pt_to_mm(page_rect.height)
    page_area_mm2 = max(1.0, page_w_mm * page_h_mm)

    page_text = page.get_text("text", clip=page_rect) or ""
    dim_hints = extract_dimension_hints_from_text(page_text)
    if target_size_mm:
        dim_hints = [target_size_mm] + dim_hints

    raw_drawings = page.get_drawings()
    drawings = [
        d for d in raw_drawings
        if d.get("rect") is not None and page_rect.intersects(pymupdf.Rect(d["rect"]))
    ]
    text_dict = page.get_text("dict", clip=page_rect)
    text_blocks = [b for b in text_dict.get("blocks", []) if b.get("type") == 0]

    # Step 1: Collect all closed rectangular/rounded-rectangular shapes
    merged_boxes: List[Dict[str, Any]] = []
    for idx, d in enumerate(drawings):
        if not _is_closed_box_like_drawing(d):
            continue
        r = pymupdf.Rect(d["rect"])
        if not _rect_contains(page_rect, r, tol_pt=4.0):
            continue

        w_mm = pt_to_mm(r.width)
        h_mm = pt_to_mm(r.height)
        area_ratio = (w_mm * h_mm) / page_area_mm2

        # Ignore full-page frames (> 88% of page area) IF there are other paths on the page
        if area_ratio > 0.88 and len(drawings) > 3:
            continue

        # Ignore top/bottom header banners (spanning > 78% of page width and aspect ratio > 6:1 near top/bottom)
        rel_y0 = (r.y0 - page_rect.y0) / max(1.0, page_rect.height)
        if (w_mm / max(1.0, h_mm)) >= 5.5 and (w_mm / max(1.0, page_w_mm)) >= 0.72 and (rel_y0 < 0.18 or rel_y0 > 0.82):
            continue

        fill = d.get("fill")
        stroke = d.get("color")
        has_fill = not _is_white_or_none(fill)
        has_stroke = stroke is not None

        # Merge duplicate/overlapping stroke+fill paths for the same box
        existing = next((b for b in merged_boxes if _rect_nearly_equal(b["rect"], r, tol_pt=2.5)), None)
        if existing is not None:
            existing["indices"].append(idx)
            if has_fill and not existing["has_fill"]:
                existing["has_fill"] = True
                existing["fill"] = fill
            if has_stroke:
                existing["has_stroke"] = True
                existing["stroke"] = stroke
        else:
            merged_boxes.append({
                "rect": r,
                "indices": [idx],
                "has_fill": has_fill,
                "fill": fill if has_fill else None,
                "has_stroke": has_stroke,
                "stroke": stroke,
                "w_mm": w_mm,
                "h_mm": h_mm,
            })

    # Step 2: Filter out container frames that enclose 2+ disjoint smaller candidate boxes
    filtered_boxes: List[Dict[str, Any]] = []
    for box_a in merged_boxes:
        r_a = box_a["rect"]
        children = [
            box_b["rect"]
            for box_b in merged_boxes
            if box_b is not box_a
            and _rect_contains(r_a, box_b["rect"])
            and (box_b["rect"].width * box_b["rect"].height) < (r_a.width * r_a.height * 0.82)
        ]
        disjoint = 0
        used: List[pymupdf.Rect] = []
        for ch in children:
            if not any(ch.intersects(u) for u in used):
                disjoint += 1
                used.append(ch)
        if disjoint >= 2:
            continue
        filtered_boxes.append(box_a)

    # Step 3: Filter out inner sub-boxes that sit strictly inside a larger design/dieline candidate
    top_boxes: List[Dict[str, Any]] = []
    for box_a in filtered_boxes:
        r_a = box_a["rect"]
        inside_larger = False
        for box_b in filtered_boxes:
            if box_a is box_b:
                continue
            r_b = box_b["rect"]
            if _rect_contains(r_b, r_a, tol_pt=1.5) and (r_b.width * r_b.height) > (r_a.width * r_a.height * 1.08):
                inside_larger = True
                break
        if not inside_larger:
            top_boxes.append(box_a)

    # Step 4: Analyze interior content, punch holes, Pantone swatches, and role classification
    candidates: List[DetectedCandidate] = []

    for box in top_boxes:
        r: pymupdf.Rect = box["rect"]
        w_mm: float = box["w_mm"]
        h_mm: float = box["h_mm"]
        box_indices = set(box["indices"])

        holes: List[DetectedHole] = []
        interior_paths = 0
        for idx, d in enumerate(drawings):
            if idx in box_indices:
                continue
            dr = d.get("rect")
            if dr is None or dr.is_empty:
                continue
            d_rect = pymupdf.Rect(dr)
            if _rect_contains(r, d_rect, tol_pt=2.0):
                hole = _is_small_circle_or_hole(d, r)
                if hole is not None:
                    if not any(
                        math.hypot(h.center_x_mm - hole.center_x_mm, h.center_y_mm - hole.center_y_mm) < 1.5
                        for h in holes
                    ):
                        holes.append(hole)
                else:
                    interior_paths += 1

        interior_texts = 0
        for b in text_blocks:
            bbox = b.get("bbox")
            if bbox and _rect_contains(r, pymupdf.Rect(bbox), tol_pt=2.0):
                interior_texts += 1

        matches_hint = _matches_any_dimension_hint(w_mm, h_mm, dim_hints, tol_mm=2.2)

        # Filter out small Pantone / color legend swatches in specification blocks
        # (e.g., 15x6 mm filled rectangle with 0 interior paths/texts that doesn't match target size)
        if (
            max(w_mm, h_mm) < 28.0
            and min(w_mm, h_mm) < 15.0
            and interior_paths == 0
            and interior_texts == 0
            and len(holes) == 0
            and not matches_hint
        ):
            continue

        has_fill = bool(box["has_fill"])
        # Determine role: "design" vs "dieline"
        if has_fill or interior_paths >= 2 or interior_texts >= 1:
            role = "design"
        else:
            role = "dieline"

        confidence = 0.72
        if matches_hint:
            confidence += 0.22
        if has_fill and (interior_paths > 0 or interior_texts > 0):
            confidence += 0.05
        if len(holes) > 0:
            confidence += 0.04
        confidence = min(0.99, confidence)

        x0_mm = pt_to_mm(r.x0 - page_rect.x0)
        y0_mm = pt_to_mm(r.y0 - page_rect.y0)
        x1_mm = pt_to_mm(r.x1 - page_rect.x0)
        y1_mm = pt_to_mm(r.y1 - page_rect.y0)

        candidates.append(
            DetectedCandidate(
                id="",
                page_index=page_index,
                role=role,
                label="",
                bbox_mm=(x0_mm, y0_mm, x1_mm, y1_mm),
                width_mm=w_mm,
                height_mm=h_mm,
                has_outer_border=bool(box["has_stroke"]) or not has_fill,
                has_fill=has_fill,
                fill_color_hex=_color_tuple_to_hex(box["fill"]),
                fill_color_raw=box["fill"],
                interior_paths_count=interior_paths,
                interior_texts_count=interior_texts,
                holes=holes,
                confidence=confidence,
                matches_text_hint=matches_hint,
                selected_by_default=True,
            )
        )

    # Pair up dielines with matching-dimension designs on the same page to boost dieline confidence
    design_dims = [(c.width_mm, c.height_mm) for c in candidates if c.role == "design"]
    for c in candidates:
        if c.role == "dieline" and _matches_any_dimension_hint(c.width_mm, c.height_mm, design_dims, tol_mm=1.8):
            c.confidence = min(0.98, max(c.confidence, 0.90))
            c.matches_text_hint = True

    # Fallback: if no box candidates were found on a single-artwork page, offer the content bounding box or full page
    if not candidates and (drawings or text_blocks):
        content_rect: Optional[pymupdf.Rect] = None
        for d in drawings:
            dr = d.get("rect")
            if dr is not None and not dr.is_empty:
                content_rect = pymupdf.Rect(dr) if content_rect is None else (content_rect | pymupdf.Rect(dr))
        for b in text_blocks:
            bbox = b.get("bbox")
            if bbox:
                content_rect = pymupdf.Rect(bbox) if content_rect is None else (content_rect | pymupdf.Rect(bbox))

        target_r = page_rect
        if content_rect is not None:
            content_rect &= page_rect
            if not content_rect.is_empty and (content_rect.width * content_rect.height) < (page_rect.width * page_rect.height * 0.75):
                target_r = content_rect

        x0_mm = pt_to_mm(target_r.x0 - page_rect.x0)
        y0_mm = pt_to_mm(target_r.y0 - page_rect.y0)
        x1_mm = pt_to_mm(target_r.x1 - page_rect.x0)
        y1_mm = pt_to_mm(target_r.y1 - page_rect.y0)
        w_mm = pt_to_mm(target_r.width)
        h_mm = pt_to_mm(target_r.height)
        candidates.append(
            DetectedCandidate(
                id=f"p{page_index + 1}_c1",
                page_index=page_index,
                role="design",
                label=f"Dizayn #1 ({round(w_mm, 1)}×{round(h_mm, 1)} mm)",
                bbox_mm=(x0_mm, y0_mm, x1_mm, y1_mm),
                width_mm=w_mm,
                height_mm=h_mm,
                has_outer_border=False,
                has_fill=True,
                fill_color_hex=None,
                fill_color_raw=None,
                interior_paths_count=len(drawings),
                interior_texts_count=len(text_blocks),
                holes=[],
                confidence=0.65,
                matches_text_hint=_matches_any_dimension_hint(w_mm, h_mm, dim_hints),
                selected_by_default=True,
            )
        )

    # Sort: designs first (left-to-right, top-to-bottom), then dielines
    candidates.sort(key=lambda c: (0 if c.role == "design" else 1, round(c.bbox_mm[1] / 15.0), c.bbox_mm[0]))

    design_seq = 0
    dieline_seq = 0
    for idx, c in enumerate(candidates, start=1):
        c.id = f"p{page_index + 1}_item{idx}"
        dim_str = f"{round(c.width_mm, 1):g}×{round(c.height_mm, 1):g} mm"
        if c.role == "design":
            design_seq += 1
            c.label = f"Dizayn #{design_seq} ({dim_str})"
        else:
            dieline_seq += 1
            c.label = f"Pichoq / Shtants #{dieline_seq} ({dim_str})"

    return candidates, dim_hints


def search_candidates_by_size(
    page: pymupdf.Page,
    page_index: int,
    target_w_mm: float,
    target_h_mm: float,
    tol_mm: float = 3.0,
) -> List[DetectedCandidate]:
    """
    Finds any vector paths or clusters on `page` matching `(target_w_mm, target_h_mm)` within `tol_mm`.
    """
    candidates, _ = detect_page_candidates(
        page,
        page_index=page_index,
        target_size_mm=(target_w_mm, target_h_mm),
    )
    matched = [
        c
        for c in candidates
        if _matches_any_dimension_hint(c.width_mm, c.height_mm, [(target_w_mm, target_h_mm)], tol_mm=tol_mm)
    ]
    if matched:
        return matched

    # Also scan all raw drawings directly in case an unusual shape was skipped
    page_rect = page.cropbox if not page.cropbox.is_empty else page.rect
    raw_drawings = page.get_drawings()
    extra: List[DetectedCandidate] = []
    for idx, d in enumerate(raw_drawings):
        r = d.get("rect")
        if r is None or r.is_empty:
            continue
        r = pymupdf.Rect(r)
        if not _rect_contains(page_rect, r, tol_pt=4.0):
            continue
        w_mm = pt_to_mm(r.width)
        h_mm = pt_to_mm(r.height)
        if _matches_any_dimension_hint(w_mm, h_mm, [(target_w_mm, target_h_mm)], tol_mm=tol_mm):
            if any(_rect_nearly_equal(r, pymupdf.Rect(
                page_rect.x0 + mm_to_pt(e.bbox_mm[0]),
                page_rect.y0 + mm_to_pt(e.bbox_mm[1]),
                page_rect.x0 + mm_to_pt(e.bbox_mm[2]),
                page_rect.y0 + mm_to_pt(e.bbox_mm[3]),
            ), tol_pt=3.0) for e in extra):
                continue
            x0_mm = pt_to_mm(r.x0 - page_rect.x0)
            y0_mm = pt_to_mm(r.y0 - page_rect.y0)
            x1_mm = pt_to_mm(r.x1 - page_rect.x0)
            y1_mm = pt_to_mm(r.y1 - page_rect.y0)
            has_fill = not _is_white_or_none(d.get("fill"))
            role = "design" if has_fill else "dieline"
            extra.append(
                DetectedCandidate(
                    id=f"p{page_index + 1}_search{len(extra) + 1}",
                    page_index=page_index,
                    role=role,
                    label=f"{'Dizayn' if role == 'design' else 'Pichoq'} ({round(w_mm, 1):g}×{round(h_mm, 1):g} mm)",
                    bbox_mm=(x0_mm, y0_mm, x1_mm, y1_mm),
                    width_mm=w_mm,
                    height_mm=h_mm,
                    has_outer_border=d.get("color") is not None,
                    has_fill=has_fill,
                    fill_color_hex=_color_tuple_to_hex(d.get("fill")),
                    fill_color_raw=d.get("fill"),
                    interior_paths_count=1,
                    interior_texts_count=0,
                    holes=[],
                    confidence=0.92,
                    matches_text_hint=True,
                    selected_by_default=True,
                )
            )
    return extra


# ---------------------------------------------------------------------------
# Surgical PDF Content Stream Isolation (Zero Clipping Masks + Hole/Bleed Control)
# ---------------------------------------------------------------------------
_STREAM_TOKEN_RE = re.compile(
    r"""
    (\((?:\\.|[^\\()])*\)) |                                    # Literal string (...)
    (<[0-9A-Fa-f\s]*>) |                                        # Hex string <...>
    (\[(?:[^\[\]]|\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>)*\]) |  # Array [...]
    (/[A-Za-z0-9_.\-+]+) |                                      # Name /Name
    ([-+]?(?:\d+\.?\d*|\.\d+)) |                                # Number
    ([A-Za-z*'"]+)                                              # Operator
    """,
    re.VERBOSE,
)

_PAINT_OR_TEXT_RE = re.compile(r"\b(BT|ET|Tj|TJ|S|s|f|F|f\*|B|B\*|b|b\*|Do|BI|sh)\b")


def _is_num(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def _prune_empty_graphics_states(stream_text: str) -> str:
    lines = stream_text.splitlines()
    cleaned_lines: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line.endswith(" DP") and "/Corel_OTF" in line:
            j = i + 1
            found_bt = False
            while j < min(n, i + 5):
                nxt = lines[j].strip()
                if nxt == "BT":
                    found_bt = True
                    break
                if nxt.endswith(" DP") or nxt in ("q", "Q"):
                    break
                j += 1
            if not found_bt:
                if cleaned_lines and cleaned_lines[-1].endswith(" gs"):
                    cleaned_lines.pop()
                i += 1
                continue
        cleaned_lines.append(line)
        i += 1

    frames: List[Tuple[List[str], bool]] = [([], True)]
    for line in cleaned_lines:
        if line == "q":
            frames.append((["q"], False))
        elif line == "Q" and len(frames) > 1:
            frame_lines, has_paint = frames.pop()
            if has_paint:
                frame_lines.append("Q")
                parent_lines, _ = frames[-1]
                parent_lines.extend(frame_lines)
                frames[-1] = (parent_lines, True)
        else:
            curr_lines, has_paint = frames[-1]
            curr_lines.append(line)
            if not has_paint and _PAINT_OR_TEXT_RE.search(line):
                frames[-1] = (curr_lines, True)

    result_lines: List[str] = []
    for frame_lines, _ in frames:
        result_lines.extend(frame_lines)
    return "\n".join(result_lines)


def _get_xobject_map(doc: pymupdf.Document, owner_xref: int) -> dict[str, int]:
    res: dict[str, int] = {}
    try:
        t, val = doc.xref_get_key(owner_xref, "Resources/XObject")
        if t == "xref" and val:
            ref_id = int(val.split()[0])
            val = doc.xref_object(ref_id)
            t = "dict"
        if t == "dict" and val:
            for m in re.finditer(r"/([A-Za-z0-9_.\-+]+)\s+(\d+)\s+0\s+R", val):
                res["/" + m.group(1)] = int(m.group(2))
    except Exception:
        pass
    return res


def _get_form_matrix(doc: pymupdf.Document, form_xref: int) -> pymupdf.Matrix:
    try:
        t, val = doc.xref_get_key(form_xref, "Matrix")
        if t == "array" and val:
            nums = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", val)]
            if len(nums) == 6:
                return pymupdf.Matrix(*nums)
    except Exception:
        pass
    return pymupdf.Matrix(1, 0, 0, 1, 0, 0)


def _merge_form_resources_to_page(doc: pymupdf.Document, page_xref: int, form_xref: int) -> None:
    for subkey in ("Font", "ExtGState", "ColorSpace", "Pattern", "Shading", "Properties", "XObject"):
        try:
            ft, fval = doc.xref_get_key(form_xref, f"Resources/{subkey}")
            if ft == "xref" and fval:
                fval = doc.xref_object(int(fval.split()[0]))
                ft = "dict"
            if ft != "dict" or not fval:
                continue
            pt, pval = doc.xref_get_key(page_xref, f"Resources/{subkey}")
            if pt == "xref" and pval:
                pval = doc.xref_object(int(pval.split()[0]))
                pt = "dict"
            entries: dict[str, str] = {}
            for src in (fval, pval if pt == "dict" else ""):
                if src:
                    for m in re.finditer(r"(/[A-Za-z0-9_.\-+]+)\s+(\d+\s+0\s+R)", src):
                        entries[m.group(1)] = m.group(2)
            if entries:
                merged_dict = "<<" + " ".join(f"{k} {v}" for k, v in entries.items()) + ">>"
                doc.xref_set_key(page_xref, f"Resources/{subkey}", merged_dict)
        except Exception:
            continue


def _inline_form_xobjects(
    doc: pymupdf.Document,
    page_xref: int,
    owner_xref: int,
    stream_bytes: bytes,
    depth: int = 0,
) -> Tuple[bytes, set[str]]:
    if depth > 5:
        return stream_bytes, set()
    xmap = _get_xobject_map(doc, owner_xref)
    if not xmap:
        return stream_bytes, set()
    try:
        text = stream_bytes.decode("latin1")
    except Exception:
        return stream_bytes, set()
    if "Do" not in text:
        return stream_bytes, set()

    tokens = [m.group(0) for m in _STREAM_TOKEN_RE.finditer(text)]
    out_cmds: List[str] = []
    operands: List[str] = []
    inlined_names: set[str] = set()

    for tok in tokens:
        if _is_num(tok) or tok.startswith(("/", "(", "<", "[")):
            operands.append(tok)
            continue
        op = tok
        if op == "Do" and len(operands) == 1 and operands[0] in xmap:
            xname = operands[0]
            fxref = xmap[xname]
            sub = doc.xref_get_key(fxref, "Subtype")
            if sub and sub[1] == "/Form" and doc.xref_is_stream(fxref):
                _merge_form_resources_to_page(doc, page_xref, fxref)
                fmat = _get_form_matrix(doc, fxref)
                fstream = doc.xref_stream(fxref) or b""
                inlined_child, child_inlined = _inline_form_xobjects(
                    doc, page_xref, fxref, fstream, depth + 1
                )
                inlined_names.add(xname)
                inlined_names.update(child_inlined)
                child_text = inlined_child.decode("latin1", errors="ignore")
                mat_cmd = f"{fmat.a:.6f} {fmat.b:.6f} {fmat.c:.6f} {fmat.d:.6f} {fmat.e:.6f} {fmat.f:.6f} cm"
                out_cmds.append(f"q\n{mat_cmd}\n{child_text}\nQ")
                operands.clear()
                continue
        cmd_str = (" ".join(operands) + " " + op).strip()
        out_cmds.append(cmd_str)
        operands.clear()

    return "\n".join(out_cmds).encode("latin1"), inlined_names


def _isolate_region_from_stream(
    stream_bytes: bytes,
    target_pdf_rect: Tuple[float, float, float, float],
    remove_border: bool = False,
    remove_hole: bool = False,
    bleed_pt: float = 0.0,
    background_fill_color: Optional[Tuple[float, ...]] = None,
) -> bytes:
    """
    Surgically filters a PDF content stream to keep only vector paths and text inside
    `target_pdf_rect = (tx0, ty0, tx1, ty1)`:
    - Physically deletes all paths and text blocks outside `target_pdf_rect`.
    - When `remove_border=True`, removes outer border stroke matching `target_pdf_rect` (or converts `B`/`b`
      fill+stroke background rectangle into pure fill `f`).
    - When `remove_hole=True`, removes small circular punch-hole paths inside the design so the background
      prints solid across the hole area.
    - Translates origin so content sits at `(bleed_pt, bleed_pt, W + bleed_pt, H + bleed_pt)`.
    - If `bleed_pt > 0` and `background_fill_color` is known, prepends a bleed background rectangle covering
      `(0, 0, W + 2*bleed_pt, H + 2*bleed_pt)`.
    """
    try:
        text = stream_bytes.decode("latin1")
    except Exception:
        return stream_bytes

    tx0, ty0, tx1, ty1 = target_pdf_rect
    tw = tx1 - tx0
    th = ty1 - ty0
    outside_tol = 2.8
    border_tol = 2.5

    tokens = [m.group(0) for m in _STREAM_TOKEN_RE.finditer(text)]
    out_cmds: List[str] = []
    operands: List[str] = []

    ctm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    ctm_stack: List[pymupdf.Matrix] = []

    in_bt = False
    bt_cmds: List[str] = []
    bt_has_tf = False
    active_font_cmd: Optional[str] = None
    font_stack: List[Optional[str]] = []
    tm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    tlm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    bt_points: List[pymupdf.Point] = []

    path_cmds: List[str] = []
    path_points: List[pymupdf.Point] = []
    path_has_curves = False
    path_seg_count = 0

    def point_in_target(pt: pymupdf.Point, tol: float = outside_tol) -> bool:
        return (tx0 - tol) <= pt.x <= (tx1 + tol) and (ty0 - tol) <= pt.y <= (ty1 + tol)

    for tok in tokens:
        if _is_num(tok) or tok.startswith(("/", "(", "<", "[")):
            operands.append(tok)
            continue

        op = tok
        cmd_str = (" ".join(operands) + " " + op).strip()

        if in_bt:
            bt_cmds.append(cmd_str)
            if op == "Tf":
                active_font_cmd = cmd_str
                bt_has_tf = True
            elif op == "Tm" and len(operands) >= 6 and all(_is_num(x) for x in operands[-6:]):
                vals = [float(x) for x in operands[-6:]]
                tm = pymupdf.Matrix(*vals)
                tlm = pymupdf.Matrix(*vals)
            elif op in ("Td", "TD") and len(operands) >= 2 and all(_is_num(x) for x in operands[-2:]):
                dx, dy = float(operands[-2]), float(operands[-1])
                tlm = pymupdf.Matrix(1, 0, 0, 1, dx, dy) * tlm
                tm = pymupdf.Matrix(tlm)
            elif op in ("Tj", "TJ", "'", '"'):
                bt_points.append(pymupdf.Point(tm.e, tm.f) * ctm)
            elif op == "ET":
                in_bt = False
                if not bt_points or any(point_in_target(p, tol=3.5) for p in bt_points):
                    if not bt_has_tf and active_font_cmd:
                        bt_cmds.insert(1, active_font_cmd)
                    out_cmds.extend(bt_cmds)
                bt_cmds.clear()
                bt_points.clear()
                bt_has_tf = False
            operands.clear()
            continue

        if op == "Tf":
            active_font_cmd = cmd_str

        if op == "BT":
            in_bt = True
            bt_cmds = ["BT"]
            bt_has_tf = False
            tm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            tlm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            bt_points.clear()
            operands.clear()
            continue

        if op == "m" and len(operands) >= 2 and all(_is_num(x) for x in operands[-2:]):
            x, y = float(operands[-2]), float(operands[-1])
            path_points.append(pymupdf.Point(x, y) * ctm)
            path_cmds.append(cmd_str)
            operands.clear()
            continue

        if op == "l" and len(operands) >= 2 and all(_is_num(x) for x in operands[-2:]):
            x, y = float(operands[-2]), float(operands[-1])
            path_points.append(pymupdf.Point(x, y) * ctm)
            path_seg_count += 1
            path_cmds.append(cmd_str)
            operands.clear()
            continue

        if op == "c" and len(operands) >= 6 and all(_is_num(x) for x in operands[-6:]):
            vals = [float(x) for x in operands[-6:]]
            path_points.append(pymupdf.Point(vals[0], vals[1]) * ctm)
            path_points.append(pymupdf.Point(vals[2], vals[3]) * ctm)
            path_points.append(pymupdf.Point(vals[4], vals[5]) * ctm)
            path_has_curves = True
            path_seg_count += 1
            path_cmds.append(cmd_str)
            operands.clear()
            continue

        if op in ("v", "y") and len(operands) >= 4 and all(_is_num(x) for x in operands[-4:]):
            vals = [float(x) for x in operands[-4:]]
            path_points.append(pymupdf.Point(vals[0], vals[1]) * ctm)
            path_points.append(pymupdf.Point(vals[2], vals[3]) * ctm)
            path_has_curves = True
            path_seg_count += 1
            path_cmds.append(cmd_str)
            operands.clear()
            continue

        if op == "re" and len(operands) >= 4 and all(_is_num(x) for x in operands[-4:]):
            x, y, w, h = (float(operands[-4]), float(operands[-3]), float(operands[-2]), float(operands[-1]))
            path_points.append(pymupdf.Point(x, y) * ctm)
            path_points.append(pymupdf.Point(x + w, y + h) * ctm)
            path_seg_count += 1
            path_cmds.append(cmd_str)
            operands.clear()
            continue

        if op == "h" and not operands:
            path_cmds.append("h")
            operands.clear()
            continue

        if op in ("W", "W*") and not operands:
            path_cmds.append(op)
            operands.clear()
            continue

        if op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n") and not operands:
            if path_points:
                min_x = min(p.x for p in path_points)
                max_x = max(p.x for p in path_points)
                min_y = min(p.y for p in path_points)
                max_y = max(p.y for p in path_points)

                inside = (
                    min_x >= (tx0 - outside_tol)
                    and max_x <= (tx1 + outside_tol)
                    and min_y >= (ty0 - outside_tol)
                    and max_y <= (ty1 + outside_tol)
                )

                matches_outer_box = (
                    path_seg_count <= 12
                    and abs(min_x - tx0) <= border_tol
                    and abs(max_x - tx1) <= border_tol
                    and abs(min_y - ty0) <= border_tol
                    and abs(max_y - ty1) <= border_tol
                )

                is_pure_outer_stroke = False
                paint_op = op
                if remove_border and matches_outer_box:
                    if op in ("S", "s"):
                        is_pure_outer_stroke = True
                    elif op in ("B", "b"):
                        paint_op = "f"
                    elif op in ("B*", "b*"):
                        paint_op = "f*"

                is_punch_hole = False
                if remove_hole and inside and not matches_outer_box and path_has_curves and path_seg_count <= 8:
                    pw_mm = pt_to_mm(max_x - min_x)
                    ph_mm = pt_to_mm(max_y - min_y)
                    if 1.5 <= pw_mm <= 14.0 and 1.5 <= ph_mm <= 14.0 and abs(pw_mm - ph_mm) <= 1.5:
                        # Check if located strictly inside the box (usually near top or center)
                        if (
                            min_x > tx0 + 2.0
                            and max_x < tx1 - 2.0
                            and min_y > ty0 + 2.0
                            and max_y < ty1 - 2.0
                        ):
                            is_punch_hole = True

                has_clip_op = any(c in ("W", "W*") for c in path_cmds)

                if inside and not is_pure_outer_stroke and not is_punch_hole and not (op == "n" and has_clip_op):
                    out_cmds.extend(path_cmds)
                    out_cmds.append(paint_op)

            path_cmds.clear()
            path_points.clear()
            path_has_curves = False
            path_seg_count = 0
            operands.clear()
            continue

        if op == "q" and not operands:
            ctm_stack.append(pymupdf.Matrix(ctm))
            font_stack.append(active_font_cmd)
            out_cmds.append("q")
            operands.clear()
            continue

        if op == "Q" and not operands:
            if ctm_stack:
                ctm = ctm_stack.pop()
            if font_stack:
                active_font_cmd = font_stack.pop()
            out_cmds.append("Q")
            operands.clear()
            continue

        if op == "cm" and len(operands) >= 6 and all(_is_num(x) for x in operands[-6:]):
            vals = [float(x) for x in operands[-6:]]
            ctm = pymupdf.Matrix(*vals) * ctm
            out_cmds.append(cmd_str)
            operands.clear()
            continue

        out_cmds.append(cmd_str)
        operands.clear()

    bleed_bg_cmd = ""
    if bleed_pt > 0 and background_fill_color and not _is_white_or_none(background_fill_color):
        total_w = tw + 2.0 * bleed_pt
        total_h = th + 2.0 * bleed_pt
        if len(background_fill_color) == 1:
            c_cmd = f"{background_fill_color[0]:.4f} g"
        elif len(background_fill_color) == 3:
            r_c, g_c, b_c = background_fill_color
            c_cmd = f"{r_c:.4f} {g_c:.4f} {b_c:.4f} rg"
        elif len(background_fill_color) == 4:
            c_c, m_c, y_c, k_c = background_fill_color
            c_cmd = f"{c_c:.4f} {m_c:.4f} {y_c:.4f} {k_c:.4f} k"
        else:
            c_cmd = ""
        if c_cmd:
            bleed_bg_cmd = f"q {c_cmd} 0 0 {total_w:.4f} {total_h:.4f} re f Q\n"

    shift_x = -tx0 + bleed_pt
    shift_y = -ty0 + bleed_pt
    translate_prefix = f"{bleed_bg_cmd}q 1 0 0 1 {shift_x:.4f} {shift_y:.4f} cm\n"
    translate_suffix = "\nQ\n"
    body = _prune_empty_graphics_states("\n".join(out_cmds))
    return (translate_prefix + body + translate_suffix).encode("latin1")


def _detect_dominant_fill_color_in_rect(
    page: pymupdf.Page,
    target_rect_pt: pymupdf.Rect,
) -> Optional[Tuple[float, ...]]:
    """Finds the dominant background fill color inside `target_rect_pt` for bleed extension."""
    best_color: Optional[Tuple[float, ...]] = None
    best_area = 0.0
    for d in page.get_drawings():
        r = d.get("rect")
        fill = d.get("fill")
        if r is None or r.is_empty or _is_white_or_none(fill):
            continue
        dr = pymupdf.Rect(r)
        if _rect_contains(target_rect_pt, dr, tol_pt=3.0):
            area = dr.width * dr.height
            if area > best_area and area >= (target_rect_pt.width * target_rect_pt.height * 0.45):
                best_area = area
                best_color = fill
    return best_color


def extract_region_to_pdf_doc(
    pdf_path: Path | str,
    page_index: int,
    bbox_mm: Tuple[float, float, float, float],
    remove_border: bool = False,
    remove_hole: bool = False,
    bleed_mm: float = 0.0,
    rotation_deg: int = 0,
) -> Tuple[pymupdf.Document, float, float]:
    """
    Extracts the vector artwork inside `bbox_mm = (x0_mm, y0_mm, x1_mm, y1_mm)` from `page_index`
    into a clean, standalone 1-page `pymupdf.Document` with exact dimensions:
    - Surgically deletes all outside vectors/texts and clipping masks.
    - Applies optional outer border removal, punch hole removal, background bleed extension, and rotation.
    Returns `(clean_doc, out_width_mm, out_height_mm)`.
    """
    src_doc = pymupdf.open(str(pdf_path))
    try:
        if page_index < 0 or page_index >= len(src_doc):
            raise ValueError(f"Sahifa topilmadi: {page_index + 1}")

        src_page = src_doc[page_index]
        page_rect = src_page.cropbox if not src_page.cropbox.is_empty else src_page.rect

        x0_mm, y0_mm, x1_mm, y1_mm = bbox_mm
        if x1_mm < x0_mm:
            x0_mm, x1_mm = x1_mm, x0_mm
        if y1_mm < y0_mm:
            y0_mm, y1_mm = y1_mm, y0_mm

        design_rect = pymupdf.Rect(
            page_rect.x0 + mm_to_pt(x0_mm),
            page_rect.y0 + mm_to_pt(y0_mm),
            page_rect.x0 + mm_to_pt(x1_mm),
            page_rect.y0 + mm_to_pt(y1_mm),
        )
        bleed_pt = mm_to_pt(max(0.0, bleed_mm))
        bg_fill = _detect_dominant_fill_color_in_rect(src_page, design_rect) if bleed_pt > 0 else None

        doc = pymupdf.open()
        doc.insert_pdf(src_doc, from_page=page_index, to_page=page_index)
        page = doc[0]
        page.clean_contents()

        xrefs = page.get_contents()
        if xrefs:
            raw_stream = page.read_contents()
            raw_stream, inlined_xobjs = _inline_form_xobjects(doc, page.xref, page.xref, raw_stream)
            inv_mat = ~page.transformation_matrix
            p0 = pymupdf.Point(design_rect.x0, design_rect.y0) * inv_mat
            p1 = pymupdf.Point(design_rect.x1, design_rect.y1) * inv_mat
            target_pdf_rect = (
                min(p0.x, p1.x),
                min(p0.y, p1.y),
                max(p0.x, p1.x),
                max(p0.y, p1.y),
            )

            isolated_stream = _isolate_region_from_stream(
                raw_stream,
                target_pdf_rect=target_pdf_rect,
                remove_border=remove_border,
                remove_hole=remove_hole,
                bleed_pt=bleed_pt,
                background_fill_color=bg_fill,
            )
            doc.update_stream(xrefs[0], isolated_stream)

            if inlined_xobjs:
                try:
                    xmap = _get_xobject_map(doc, page.xref)
                    kept_xobjs = [f"{k} {v} 0 R" for k, v in xmap.items() if k not in inlined_xobjs]
                    doc.xref_set_key(page.xref, "Resources/XObject", "<<" + " ".join(kept_xobjs) + ">>")
                except Exception:
                    pass

            try:
                stream_str = isolated_stream.decode("latin1", errors="ignore")
                used_fonts = set(re.findall(r"/([A-Za-z0-9_.\-+]+)\s+[-+]?\d*\.?\d+\s+Tf\b", stream_str))
                fdict_type, fdict_val = doc.xref_get_key(page.xref, "Resources/Font")
                if fdict_type == "dict" and fdict_val:
                    kept = [
                        m.group(0)
                        for m in re.finditer(r"/([A-Za-z0-9_.\-+]+)\s+\d+\s+0\s+R", fdict_val)
                        if m.group(1) in used_fonts
                    ]
                    doc.xref_set_key(page.xref, "Resources/Font", "<<" + " ".join(kept) + ">>")
            except Exception:
                pass

        out_w_pt = design_rect.width + 2.0 * bleed_pt
        out_h_pt = design_rect.height + 2.0 * bleed_pt
        norm_rect = pymupdf.Rect(0.0, 0.0, out_w_pt, out_h_pt)
        page.set_mediabox(norm_rect)
        mb = page.mediabox
        page.set_cropbox(mb)
        if bleed_pt > 0:
            trim_rect = pymupdf.Rect(bleed_pt, bleed_pt, out_w_pt - bleed_pt, out_h_pt - bleed_pt)
            try:
                page.set_trimbox(trim_rect)
            except Exception:
                pass

        if rotation_deg in (90, 180, 270):
            page.set_rotation(rotation_deg)

        for xref in range(1, doc.xref_length()):
            try:
                obj = doc.xref_object(xref)
                if "/Type /FontDescriptor" in obj and "/CapHeight" not in obj:
                    ascent_type, ascent_val = doc.xref_get_key(xref, "Ascent")
                    cap_h = ascent_val if (ascent_type in ("int", "float") and ascent_val) else "700"
                    doc.xref_set_key(xref, "CapHeight", str(cap_h))
            except Exception:
                continue

        compact_bytes = doc.tobytes(garbage=3, deflate=True)
        doc.close()
        clean_doc = pymupdf.open("pdf", compact_bytes)
        final_rect = clean_doc[0].rect
        return clean_doc, round(pt_to_mm(final_rect.width), 2), round(pt_to_mm(final_rect.height), 2)
    finally:
        src_doc.close()
