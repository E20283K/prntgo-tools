"""
Sela etiketka (stiker) PDF generatori — A4 qog'ozga terib chiqish bilan.

template.pdf asosida logotip, EAC ikonkasi, ramka, chiziqlar, shriftlar
va umumiy stiker o'lchamini (78.20 mm x 20.20 mm) o'zgartirmasdan:
  - Barkod (EAN-13)
  - Artikul
  - Rang (Colour)
  - O'lcham (Size)
ma'lumotlarini yangilaydi va barcha etiketkalarni A4 varaqlariga joylashtiradi.

Foydalanish usullari:
  1. Interaktiv rejim:
     python generate_labels.py

  2. Bitta etiketka turi (CLI):
     python generate_labels.py --artikul "SI7804050205" --colour "33" --size "104/ 4-5 YEARS" --barcode "4620544686957" --qty 26 -o output_a4.pdf

  3. CSV fayldan ko'plab etiketkalar:
     python generate_labels.py --csv orders.csv -o output_a4.pdf
     (CSV ustunlari: artikul,colour,size,barcode,qty)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pymupdf  # PyMuPDF


# ---------------------------------------------------------------------------
# EAN-13 kodlash jadvallari (GS1 standarti)
# ---------------------------------------------------------------------------
EAN13_L = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101", "4": "0100011",
    "5": "0110001", "6": "0101111", "7": "0111011", "8": "0110111", "9": "0001011",
}
EAN13_G = {
    "0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001", "4": "0011101",
    "5": "0111001", "6": "0000101", "7": "0010001", "8": "0001001", "9": "0010111",
}
EAN13_R = {
    "0": "1110010", "1": "1100110", "2": "1101100", "3": "1000010", "4": "1011100",
    "5": "1001110", "6": "1010000", "7": "1000100", "8": "1001000", "9": "1110100",
}
EAN13_PARITY = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL", "4": "LGLLGG",
    "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG", "8": "LGLGGL", "9": "LGGLGL",
}

# ---------------------------------------------------------------------------
# template.pdf dan olingan aniq geometriya va ranglar (punktlarda, 1 pt = 1/72")
# ---------------------------------------------------------------------------
MM_TO_PT = 72.0 / 25.4
A4_WIDTH_PT = 210.0 * MM_TO_PT
A4_HEIGHT_PT = 297.0 * MM_TO_PT
DEFAULT_LABEL_W_PT = 221.66929626464844  # 78.20 mm
DEFAULT_LABEL_H_PT = 57.25979995727539   # 20.20 mm

# Ranglar (template.pdf dagi asl ranglar)
COLOR_TEXT = (3 / 255, 4 / 255, 6 / 255)                 # #030406
COLOR_BARCODE = (0.1367, 0.1220, 0.1253)                 # #231f20

# Tozalanadigan (eski ma'lumotlar o'chiriladigan) sohalar
REDACT_BARCODE = pymupdf.Rect(5.0, 10.0, 96.0, 50.0)
REDACT_ARTIKUL = pymupdf.Rect(103.0, 24.0, 195.0, 33.5)
REDACT_COLOUR = pymupdf.Rect(130.0, 33.0, 195.0, 43.0)
REDACT_SIZE = pymupdf.Rect(103.0, 44.5, 195.0, 55.0)

# Matn koordinatalari va o'lchamlari (origin = baseline)
ARTIKUL_POS = (104.626, 31.224)
ARTIKUL_FONTSIZE = 6.96

COLOUR_POS = (134.146, 39.864)
COLOUR_FONTSIZE = 8.04

SIZE_POS = (105.826, 51.384)
SIZE_FONTSIZE = 6.96

MAX_TEXT_RIGHT_X = 194.5  # Punkti chiziq x=198.16 da joylashgan

# Barkod geometriyasi (template.pdf dan olingan)
BARCODE_X0 = 15.084
BARCODE_X1 = 91.521
BARCODE_Y_TOP = 13.069
BARCODE_Y_BOTTOM_SHORT = 38.170
BARCODE_Y_BOTTOM_TALL = 43.011
BARCODE_MODULE_PITCH = (BARCODE_X1 - BARCODE_X0) / 95.0  # ~0.8046 pt
BARCODE_BWR = 0.08  # Har ikki tomondan 0.08 pt (print-gain kompensatsiya, template bilan bir xil)

BARCODE_TEXT_Y = 44.160
BARCODE_TEXT_SIZE = 8.042
BARCODE_FIRST_DIGIT_X = 9.157
BARCODE_LEFT_GROUP_X = 17.926
BARCODE_RIGHT_GROUP_X = 54.996
BARCODE_DIGIT_STEP = 7.0 * BARCODE_MODULE_PITCH  # 5.632 pt


@dataclass
class LabelData:
    artikul: str
    colour: str
    size: str
    barcode: str
    qty: int = 1
    common_labels: List[Path] = field(default_factory=list)
    source: str = ""


def find_font_file(candidates: List[str]) -> Optional[str]:
    """Tizimdagi mavjud shrift faylini topadi (Windows, macOS, Linux Docker)."""
    search_dirs = [
        Path(__file__).resolve().parent.parent.parent / "data" / "fonts",
        Path(__file__).resolve().parent / "fonts",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
    ]
    for name in candidates:
        p = Path(name)
        if p.is_file():
            return str(p)
        for d in search_dirs:
            if not d.is_dir():
                continue
            fp = d / name
            if fp.is_file():
                return str(fp)
            # Linuxda shriftlar ichki papkalarda joylashadi (/usr/share/fonts/truetype/...)
            for match in d.rglob(name):
                if match.is_file():
                    return str(match)
    return None


def compute_ean13_checksum(code12: str) -> str:
    """12 xonali raqamdan 13-chi nazorat raqamini hisoblaydi."""
    total = 0
    for i, ch in enumerate(code12):
        d = int(ch)
        total += d if i % 2 == 0 else d * 3
    return str((10 - (total % 10)) % 10)


def normalize_ean13(raw_code: str) -> str:
    """EAN-13 barkodni tekshiradi va 13 xonali ko'rinishga keltiradi."""
    digits = "".join(ch for ch in raw_code.strip() if ch.isdigit())
    if len(digits) == 12:
        return digits + compute_ean13_checksum(digits)
    if len(digits) == 13:
        expected = compute_ean13_checksum(digits[:12])
        if digits[12] != expected:
            print(
                f"Ogohlantirish: '{digits}' barkodining oxirgi nazorat raqami "
                f"GS1 standartiga ko'ra '{expected}' bo'lishi kerak edi. "
                f"Kiritilgan qiymat saqlab qolindi.",
                file=sys.stderr,
            )
        return digits
    raise ValueError(
        f"Barkod 12 yoki 13 ta raqamdan iborat bo'lishi kerak (kiritildi: '{raw_code}', {len(digits)} ta raqam)."
    )


def encode_ean13_bits(code13: str) -> str:
    """13 xonali EAN-13 kodini 95 bitli (0/1) chiziqlar ketma-ketligiga o'giradi."""
    first = code13[0]
    left_digits = code13[1:7]
    right_digits = code13[7:13]
    parity = EAN13_PARITY[first]

    bits = ["101"]  # Chap himoya chiziqlari (0..2)
    for d, p in zip(left_digits, parity):
        bits.append(EAN13_L[d] if p == "L" else EAN13_G[d])
    bits.append("01010")  # Markaziy himoya chiziqlari (45..49)
    for d in right_digits:
        bits.append(EAN13_R[d])
    bits.append("101")  # O'ng himoya chiziqlari (92..94)
    return "".join(bits)


def _open_template_as_pdf(template_path: Path) -> pymupdf.Document:
    """
    PDF yoki SVG shablon faylini ochib, 1 sahifali PDF Document qaytaradi.
    SVG bo'lsa, vektor holida PDF ga o'giradi va umumiy stiker o'lchamini
    78.20 mm x 20.20 mm da saqlab qoladi.
    """
    suffix = template_path.suffix.lower()
    if suffix == ".svg":
        pdf_bytes: Optional[bytes] = None
        try:
            # Asosiy usul: svglib + reportlab (stroke-dasharray va <text> ni aniq saqlaydi)
            from io import BytesIO
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg

            drawing = svg2rlg(str(template_path))
            if drawing is None:
                raise ValueError(f"svglib SVG faylini o'qiy olmadi: {template_path}")
            buf = BytesIO()
            renderPDF.drawToFile(drawing, buf)
            pdf_bytes = buf.getvalue()
        except Exception:
            # Zaxira usul: PyMuPDF SVG o'quvchi
            with pymupdf.open(str(template_path), filetype="svg") as svg_doc:
                pdf_bytes = svg_doc.convert_to_pdf()

        raw_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        if len(raw_doc) == 0:
            raw_doc.close()
            raise ValueError(f"'{template_path}' bo'sh SVG fayl.")

        src_rect = raw_doc[0].rect
        # Agar SVG o'lchami 78.20 x 20.20 mm dan farq qilsa (masalan 96dpi px birliklari),
        # aniq 78.20 x 20.20 mm o'lchamga vektor holida moslashtiramiz.
        if (
            abs(src_rect.width - DEFAULT_LABEL_W_PT) > 1.0
            or abs(src_rect.height - DEFAULT_LABEL_H_PT) > 1.0
        ):
            norm_doc = pymupdf.open()
            norm_page = norm_doc.new_page(width=DEFAULT_LABEL_W_PT, height=DEFAULT_LABEL_H_PT)
            norm_page.show_pdf_page(norm_page.rect, raw_doc, 0, keep_proportion=False)
            raw_doc.close()
            return norm_doc
        return raw_doc

    doc = pymupdf.open(str(template_path))
    if len(doc) == 0:
        doc.close()
        raise ValueError(f"'{template_path}' bo'sh PDF fayl.")
    return doc


def prepare_clean_template(template_path: Path) -> Tuple[bytes, pymupdf.Rect]:
    """
    template.pdf yoki .svg faylidan faqat dinamik qismlarni (eski barkod, artikul,
    rang kodi, o'lcham) olib tashlab, logotip, EAC, ramka, punkti chiziq va 'Colour'
    yozuvini vektor holida saqlab qoladi.
    """
    doc = _open_template_as_pdf(template_path)
    page = doc[0]
    label_rect = pymupdf.Rect(page.rect)

    for rect in (REDACT_BARCODE, REDACT_ARTIKUL, REDACT_COLOUR, REDACT_SIZE):
        page.add_redact_annot(rect, fill=None)

    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
    )

    clean_bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return clean_bytes, label_rect


def render_label_preview_pdf(
    template_path: Path,
    data: LabelData,
    clean_cache: Optional[Tuple[bytes, pymupdf.Rect]] = None,
) -> bytes:
    """UI da ko'rsatish uchun bitta stikerning real vektorli PDF baytlarini qaytaradi."""
    arial_path = find_font_file(["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"])
    ocrb_path = find_font_file(["OCR-B 10 BT.ttf", "OCR-b___.ttf", "OCRB.ttf", "cour.ttf", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf"])
    if not arial_path or not ocrb_path:
        raise FileNotFoundError("Kerakli shriftlar (Arial / OCR-B) topilmadi.")

    arial_font = pymupdf.Font(fontfile=arial_path)
    clean_bytes, label_rect = clean_cache if clean_cache else prepare_clean_template(template_path)

    clean_doc = pymupdf.open(stream=clean_bytes, filetype="pdf")
    prev_doc = pymupdf.open()
    try:
        page = prev_doc.new_page(width=label_rect.width, height=label_rect.height)
        page.insert_font(fontname="F_ARIAL", fontfile=arial_path)
        page.insert_font(fontname="F_OCRB", fontfile=ocrb_path)
        page.show_pdf_page(page.rect, clean_doc, 0)
        draw_label_content(
            page=page,
            offset_x=0.0,
            offset_y=0.0,
            data=data,
            arial_font=arial_font,
            arial_fontname="F_ARIAL",
            ocrb_fontname="F_OCRB",
        )
        prev_doc.subset_fonts()
        return prev_doc.tobytes(garbage=4, deflate=True)
    finally:
        clean_doc.close()
        prev_doc.close()


def render_label_preview_png(
    template_path: Path,
    data: LabelData,
    dpi: int = 200,
    clean_cache: Optional[Tuple[bytes, pymupdf.Rect]] = None,
) -> bytes:
    """UI da ko'rsatish uchun bitta stikerning PNG preview tasvirini qaytaradi."""
    pdf_bytes = render_label_preview_pdf(template_path, data, clean_cache=clean_cache)
    prev_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        pix = prev_doc[0].get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        prev_doc.close()


def fit_fontsize(font_obj: pymupdf.Font, text: str, base_size: float, max_width: float) -> float:
    """Matn punkti chiziqdan chiqib ketmasligi uchun zarur bo'lsa shriftni biroz kichraytiradi."""
    if not text:
        return base_size
    w = font_obj.text_length(text, fontsize=base_size)
    if w <= max_width:
        return base_size
    return base_size * (max_width / w)


def draw_label_content(
    page: pymupdf.Page,
    offset_x: float,
    offset_y: float,
    data: LabelData,
    arial_font: pymupdf.Font,
    arial_fontname: str,
    ocrb_fontname: str,
) -> None:
    """Toza shablon ustiga yangi barkod va matn ma'lumotlarini chizadi."""
    code13 = normalize_ean13(data.barcode)
    bits = encode_ean13_bits(code13)

    # 1. EAN-13 barkod chiziqlarini vektor sifatida chizish
    shape = page.new_shape()
    i = 0
    n = len(bits)
    while i < n:
        if bits[i] == "1":
            start = i
            while i < n and bits[i] == "1":
                i += 1
            end = i

            is_guard = (start < 3) or (45 <= start < 50) or (start >= 92)
            x0 = offset_x + BARCODE_X0 + start * BARCODE_MODULE_PITCH + BARCODE_BWR
            x1 = offset_x + BARCODE_X0 + end * BARCODE_MODULE_PITCH - BARCODE_BWR
            if x1 <= x0:
                x0 = offset_x + BARCODE_X0 + start * BARCODE_MODULE_PITCH
                x1 = offset_x + BARCODE_X0 + end * BARCODE_MODULE_PITCH

            y0 = offset_y + BARCODE_Y_TOP
            y1 = offset_y + (BARCODE_Y_BOTTOM_TALL if is_guard else BARCODE_Y_BOTTOM_SHORT)
            shape.draw_rect(pymupdf.Rect(x0, y0, x1, y1))
        else:
            i += 1
    shape.finish(fill=COLOR_BARCODE, color=None, width=0)
    shape.commit()

    # 2. EAN-13 raqamlari (OCR-B 10 BT shrifti)
    y_bc = offset_y + BARCODE_TEXT_Y
    page.insert_text(
        (offset_x + BARCODE_FIRST_DIGIT_X, y_bc),
        code13[0],
        fontname=ocrb_fontname,
        fontsize=BARCODE_TEXT_SIZE,
        color=COLOR_BARCODE,
    )
    for idx, digit in enumerate(code13[1:7]):
        page.insert_text(
            (offset_x + BARCODE_LEFT_GROUP_X + idx * BARCODE_DIGIT_STEP, y_bc),
            digit,
            fontname=ocrb_fontname,
            fontsize=BARCODE_TEXT_SIZE,
            color=COLOR_BARCODE,
        )
    for idx, digit in enumerate(code13[7:13]):
        page.insert_text(
            (offset_x + BARCODE_RIGHT_GROUP_X + idx * BARCODE_DIGIT_STEP, y_bc),
            digit,
            fontname=ocrb_fontname,
            fontsize=BARCODE_TEXT_SIZE,
            color=COLOR_BARCODE,
        )

    # 3. Artikul, Rang kodi, O'lcham (ArialMT shrifti)
    art_size = fit_fontsize(
        arial_font, data.artikul, ARTIKUL_FONTSIZE, MAX_TEXT_RIGHT_X - ARTIKUL_POS[0]
    )
    page.insert_text(
        (offset_x + ARTIKUL_POS[0], offset_y + ARTIKUL_POS[1]),
        data.artikul,
        fontname=arial_fontname,
        fontsize=art_size,
        color=COLOR_TEXT,
    )

    col_size = fit_fontsize(
        arial_font, data.colour, COLOUR_FONTSIZE, MAX_TEXT_RIGHT_X - COLOUR_POS[0]
    )
    page.insert_text(
        (offset_x + COLOUR_POS[0], offset_y + COLOUR_POS[1]),
        data.colour,
        fontname=arial_fontname,
        fontsize=col_size,
        color=COLOR_TEXT,
    )

    sz_size = fit_fontsize(
        arial_font, data.size, SIZE_FONTSIZE, MAX_TEXT_RIGHT_X - SIZE_POS[0]
    )
    page.insert_text(
        (offset_x + SIZE_POS[0], offset_y + SIZE_POS[1]),
        data.size,
        fontname=arial_fontname,
        fontsize=sz_size,
        color=COLOR_TEXT,
    )


def compute_a4_grid(
    label_w: float,
    label_h: float,
    orientation: str = "portrait",
    margin_mm: float = 5.0,
    gap_mm: float = 2.0,
) -> Tuple[float, float, int, int, float, float, float]:
    """A4 sahifasiga nechta ustun va qator stiker sig'ishini hisoblaydi."""
    if orientation == "landscape":
        page_w, page_h = A4_HEIGHT_PT, A4_WIDTH_PT
    else:
        page_w, page_h = A4_WIDTH_PT, A4_HEIGHT_PT

    margin_pt = margin_mm * MM_TO_PT
    gap_pt = gap_mm * MM_TO_PT

    usable_w = page_w - 2 * margin_pt
    usable_h = page_h - 2 * margin_pt

    cols = int((usable_w + gap_pt) // (label_w + gap_pt))
    rows = int((usable_h + gap_pt) // (label_h + gap_pt))
    if cols < 1 or rows < 1:
        raise ValueError("Hoshiya (margin) yoki oraliq (gap) juda katta — A4 ga stiker sig'maydi.")

    grid_w = cols * label_w + (cols - 1) * gap_pt
    grid_h = rows * label_h + (rows - 1) * gap_pt

    # Markazlashtirilgan boshlang'ich koordinatalar
    start_x = (page_w - grid_w) / 2.0
    start_y = (page_h - grid_h) / 2.0
    return page_w, page_h, cols, rows, start_x, start_y, gap_pt


def render_static_label_preview_pdf(label_path: Path) -> bytes:
    """set/ papkasidagi umumiy etiketkaning tozalangan 1 sahifali vektorli PDF baytlarini qaytaradi."""
    src_doc = _open_template_as_pdf(label_path)
    out_doc = pymupdf.open()
    try:
        rect = src_doc[0].rect
        page = out_doc.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(page.rect, src_doc, 0)
        return out_doc.tobytes(garbage=4, deflate=True)
    finally:
        src_doc.close()
        out_doc.close()


def render_static_label_preview_png(label_path: Path, dpi: int = 200) -> bytes:
    """set/ papkasidagi umumiy etiketkaning PNG preview tasvirini qaytaradi."""
    doc = _open_template_as_pdf(label_path)
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()


def generate_a4_pdf(
    template_path: Path,
    items: List[LabelData],
    output_path: Path,
    orientation: str = "portrait",
    margin_mm: float = 5.0,
    gap_mm: float = 2.0,
    common_labels: Optional[List[Path]] = None,
    set_mode: str = "end",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[int, int, int]:
    """
    Etiketkalarni (hamda tanlangan umumiy set/ etiketkalarini) generatsiya qilib
    A4 qog'ozga terib chiqadi.

    set_mode:
      - "separate_pages": avval asosiy barkod etiketkalari, so'ngra har bir tanlangan
                          umumiy etiketka alohida A4 sahifadan boshlab teriladi.
      - "grouped":        avval barcha asosiy etiketkalar, ortidan bo'sh joydan davom
                          ettirib umumiy etiketkalar teriladi.
      - "interleaved":    har bir dona uchun [Asosiy, set1, set2, ...] ketma-ket teriladi.

    Qaytaradi: (jami_etiketkalar, sahifalar_soni, bir_sahifaga_sigimi)
    """
    arial_path = find_font_file(["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"])
    ocrb_path = find_font_file(["OCR-B 10 BT.ttf", "OCR-b___.ttf", "OCRB.ttf", "cour.ttf", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf"])

    if not arial_path:
        raise FileNotFoundError("Arial shrifti (arial.ttf) topilmadi.")
    if not ocrb_path:
        raise FileNotFoundError("OCR-B shrifti (OCR-B 10 BT.ttf) topilmadi.")

    arial_font = pymupdf.Font(fontfile=arial_path)

    clean_bytes, label_rect = prepare_clean_template(template_path)
    label_w = label_rect.width
    label_h = label_rect.height

    page_w, page_h, cols, rows, start_x, start_y, gap_pt = compute_a4_grid(
        label_w, label_h, orientation=orientation, margin_mm=margin_mm, gap_mm=gap_mm
    )
    per_page = cols * rows

    # Barcha nusxalarni tekis ro'yxatga yoyish va har bir element uchun umumiy etiketkalarni aniqlash
    fallback_common = [Path(p) for p in (common_labels or [])]
    expanded: List[Tuple[LabelData, List[Path]]] = []
    static_doc_cache: Dict[Path, pymupdf.Document] = {}

    for item in items:
        normalize_ean13(item.barcode)  # Avvaldan tekshirish
        item_common = [Path(p) for p in item.common_labels] if item.common_labels else fallback_common
        for sp in item_common:
            if sp not in static_doc_cache:
                static_doc_cache[sp] = _open_template_as_pdf(sp)
        for _ in range(max(1, item.qty)):
            expanded.append((item, item_common))

    if not expanded:
        raise ValueError("Generatsiya qilish uchun kamida bitta etiketka kiritilishi kerak.")

    clean_doc = pymupdf.open(stream=clean_bytes, filetype="pdf")
    out_doc = pymupdf.open()
    arial_fontname = "F_ARIAL"
    ocrb_fontname = "F_OCRB"

    current_page: Optional[pymupdf.Page] = None
    slot = 0
    total_placed = 0

    def start_new_page() -> None:
        nonlocal current_page, slot
        current_page = out_doc.new_page(width=page_w, height=page_h)
        current_page.insert_font(fontname=arial_fontname, fontfile=arial_path)
        current_page.insert_font(fontname=ocrb_fontname, fontfile=ocrb_path)
        slot = 0

    def next_slot_rect() -> Tuple[pymupdf.Page, float, float, pymupdf.Rect]:
        nonlocal slot
        if current_page is None or slot >= per_page:
            start_new_page()
        assert current_page is not None
        row = slot // cols
        col = slot % cols
        x = start_x + col * (label_w + gap_pt)
        y = start_y + row * (label_h + gap_pt)
        slot += 1
        return current_page, x, y, pymupdf.Rect(x, y, x + label_w, y + label_h)

    def place_dynamic(label: LabelData) -> None:
        nonlocal total_placed
        page, x, y, target_rect = next_slot_rect()
        page.show_pdf_page(target_rect, clean_doc, 0)
        draw_label_content(
            page=page,
            offset_x=x,
            offset_y=y,
            data=label,
            arial_font=arial_font,
            arial_fontname=arial_fontname,
            ocrb_fontname=ocrb_fontname,
        )
        total_placed += 1

    def place_static(sdoc: pymupdf.Document) -> None:
        nonlocal total_placed
        page, _, _, target_rect = next_slot_rect()
        page.show_pdf_page(target_rect, sdoc, 0, keep_proportion=True)
        total_placed += 1

    try:
        # Backwards-compatible nomlar
        mode = set_mode
        if mode == "separate_pages":
            mode = "end_pages"
        elif mode == "grouped":
            mode = "end"

        # Artikul bo'yicha tartibni saqlagan holda guruhlash
        art_order: List[str] = []
        art_groups: Dict[str, List[Tuple[LabelData, List[Path]]]] = {}
        for pair in expanded:
            art = pair[0].artikul
            if art not in art_groups:
                art_order.append(art)
                art_groups[art] = []
            art_groups[art].append(pair)

        # Har bir artikul uchun UNIKAL umumiy etiketkalar ro'yxati (har biridan 1 dona)
        art_unique_statics: Dict[str, List[Path]] = {}
        for art in art_order:
            seen_sp: set[Path] = set()
            uniq: List[Path] = []
            for _, item_common in art_groups[art]:
                for sp in item_common:
                    if sp not in seen_sp:
                        seen_sp.add(sp)
                        uniq.append(sp)
            art_unique_statics[art] = uniq

        # Jami joylashtiriladigan etiketkalar sonini oldindan hisoblash (progress bar uchun)
        if mode == "interleaved":
            planned_total = sum(1 + len(ic) for _, ic in expanded)
        else:
            planned_total = len(expanded) + sum(len(u) for u in art_unique_statics.values())

        def report_progress() -> None:
            if progress_callback:
                progress_callback(total_placed, max(1, planned_total))

        report_progress()

        if mode == "interleaved":
            for label, item_common in expanded:
                place_dynamic(label)
                report_progress()
                for sp in item_common:
                    place_static(static_doc_cache[sp])
                    report_progress()
        else:
            is_start = mode in ("start", "start_pages")
            is_paged = mode in ("end_pages", "start_pages")

            for art_idx, art in enumerate(art_order):
                grp = art_groups[art]
                uniq_statics = art_unique_statics[art]
                if is_paged and art_idx > 0 and slot > 0:
                    start_new_page()

                def emit_statics() -> None:
                    if not uniq_statics:
                        return
                    if is_paged and not is_start and slot > 0:
                        start_new_page()
                    for sp in uniq_statics:
                        place_static(static_doc_cache[sp])
                        report_progress()

                def emit_dynamics() -> None:
                    if is_paged and is_start and uniq_statics and slot > 0:
                        start_new_page()
                    for label, _ in grp:
                        place_dynamic(label)
                        report_progress()

                if is_start:
                    emit_statics()
                    emit_dynamics()
                else:
                    emit_dynamics()
                    emit_statics()

        out_doc.subset_fonts()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out_doc.save(str(output_path), garbage=4, deflate=True)
        page_count = len(out_doc)
    finally:
        clean_doc.close()
        for sdoc in static_doc_cache.values():
            sdoc.close()
        out_doc.close()

    return total_placed, page_count, per_page


def _resolve_set_paths(raw_set: str, set_dir: Optional[Path]) -> List[Path]:
    """CSV dagi 'set' ustunidan (masalan: madein|washinfo|lang1_95-5) fayl yo'llarini topadi."""
    if not raw_set:
        return []
    result: List[Path] = []
    base = set_dir if set_dir else Path(__file__).resolve().parent / "set"
    for token in raw_set.replace("+", "|").split("|"):
        name = token.strip()
        if not name:
            continue
        cand = Path(name)
        if cand.is_file():
            result.append(cand)
            continue
        for ext in ("", ".pdf", ".svg"):
            fp = base / f"{name}{ext}"
            if fp.is_file():
                result.append(fp)
                break
    return result


def load_items_from_csv(csv_path: Path, set_dir: Optional[Path] = None) -> List[LabelData]:
    """CSV fayldan etiketkalar ro'yxatini o'qiydi (',' va ';' ajratuvchilarini qo'llab-quvvatlaydi)."""
    items: List[LabelData] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.readline()
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        for row_num, row in enumerate(reader, start=2):
            norm = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            artikul = norm.get("artikul") or norm.get("article") or ""
            colour = norm.get("colour") or norm.get("color") or norm.get("rang") or ""
            size = norm.get("size") or norm.get("olcham") or norm.get("o'lcham") or ""
            barcode = norm.get("barcode") or norm.get("barkod") or ""
            qty_str = norm.get("qty") or norm.get("quantity") or norm.get("soni") or "1"
            raw_set = norm.get("set") or norm.get("common") or norm.get("umumiy") or ""

            if not (artikul and colour and size and barcode):
                raise ValueError(f"CSV {row_num}-qatorda majburiy maydon bo'sh.")
            items.append(
                LabelData(
                    artikul=artikul,
                    colour=colour,
                    size=size,
                    barcode=barcode,
                    qty=int(qty_str),
                    common_labels=_resolve_set_paths(raw_set, set_dir),
                    source=csv_path.name,
                )
            )
    return items


def prompt_interactive(per_page_default: int) -> Tuple[List[LabelData], Path]:
    """Foydalanuvchidan konsol orqali etiketka ma'lumotlarini so'raydi."""
    print("=" * 55)
    print("  SELA ETIKETKA GENERATORI (A4)")
    print("=" * 55)
    items: List[LabelData] = []

    while True:
        print(f"\n--- {len(items) + 1}-etiketka ma'lumotlari ---")
        artikul = input("Artikul (masalan, SI7804050205): ").strip()
        colour = input("Rang / Colour (masalan, 33): ").strip()
        size = input("O'lcham / Size (masalan, 104/ 4-5 YEARS): ").strip()

        while True:
            barcode = input("Barkod (12 yoki 13 xonali EAN-13): ").strip()
            try:
                barcode = normalize_ean13(barcode)
                break
            except ValueError as e:
                print(f"Xato: {e}")

        while True:
            qty_raw = input(f"Nechta dona? [standart: {per_page_default} (1 ta to'liq A4)]: ").strip()
            if not qty_raw:
                qty = per_page_default
                break
            if qty_raw.isdigit() and int(qty_raw) > 0:
                qty = int(qty_raw)
                break
            print("Xato: musbat butun son kiriting.")

        items.append(LabelData(artikul=artikul, colour=colour, size=size, barcode=barcode, qty=qty))

        more = input("\nYana boshqa etiketka qo'shasizmi? (h/y) [y]: ").strip().lower()
        if more not in ("h", "ha", "y", "yes", "1"):
            break

    out_raw = input("\nChiquvchi PDF fayl nomi [output_a4.pdf]: ").strip()
    out_path = Path(out_raw) if out_raw else Path("output_a4.pdf")
    if out_path.suffix.lower() != ".pdf":
        out_path = out_path.with_suffix(".pdf")
    return items, out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="template.pdf asosida Sela etiketkalarini A4 qog'ozga generatsiya qiladi."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parent / "template.pdf",
        help="Shablon PDF fayl yo'li (standart: template.pdf)",
    )
    parser.add_argument("--artikul", type=str, help="Artikul (masalan: SI7804050205)")
    parser.add_argument("--colour", "--color", "--rang", dest="colour", type=str, help="Rang kodi (masalan: 33)")
    parser.add_argument("--size", "--olcham", dest="size", type=str, help="O'lcham (masalan: 104/ 4-5 YEARS)")
    parser.add_argument("--barcode", "--barkod", dest="barcode", type=str, help="EAN-13 barkod (12 yoki 13 raqam)")
    parser.add_argument("--qty", "--soni", dest="qty", type=int, default=None, help="Etiketkalar soni (standart: 1 ta to'liq A4)")
    parser.add_argument("--csv", type=Path, help="Ko'plab etiketkalar uchun CSV fayl yo'li")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("output_a4.pdf"),
        help="Chiquvchi A4 PDF fayl nomi (standart: output_a4.pdf)",
    )
    parser.add_argument(
        "--orientation",
        choices=["portrait", "landscape"],
        default="portrait",
        help="A4 yo'nalishi: portrait (tik, 2x13=26) yoki landscape (yotiq, 3x9=27)",
    )
    parser.add_argument("--margin", type=float, default=5.0, help="A4 chetki hoshiya, mm (standart: 5.0)")
    parser.add_argument("--gap", type=float, default=2.0, help="Stikerlar orasidagi masofa, mm (standart: 2.0)")
    parser.add_argument(
        "--set",
        dest="common_labels",
        type=Path,
        nargs="*",
        default=[],
        help="set/ papkasidan biriktiriladigan umumiy etiketkalar (.pdf/.svg)",
    )
    parser.add_argument(
        "--set-mode",
        choices=["end", "start", "end_pages", "start_pages", "interleaved", "separate_pages", "grouped"],
        default="end",
        help="Umumiy etiketkalarni A4 ga joylashtirish tartibi (artikul oxirida/boshida)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.template.is_file():
        print(f"Xato: shablon fayli topilmadi: {args.template}", file=sys.stderr)
        sys.exit(1)

    # Bir sahifaga nechta sig'ishini oldindan hisoblash
    d = _open_template_as_pdf(args.template)
    lr = pymupdf.Rect(d[0].rect)
    d.close()
    _, _, cols, rows, _, _, _ = compute_a4_grid(
        lr.width, lr.height, orientation=args.orientation, margin_mm=args.margin, gap_mm=args.gap
    )
    per_page = cols * rows

    output_path = args.output
    if args.csv:
        items = load_items_from_csv(args.csv)
    elif args.artikul or args.colour or args.size or args.barcode:
        if not (args.artikul and args.colour and args.size and args.barcode):
            print(
                "Xato: CLI rejimida --artikul, --colour, --size va --barcode hammasi kiritilishi shart.",
                file=sys.stderr,
            )
            sys.exit(1)
        qty = args.qty if args.qty is not None else per_page
        items = [
            LabelData(
                artikul=args.artikul,
                colour=args.colour,
                size=args.size,
                barcode=args.barcode,
                qty=qty,
            )
        ]
    else:
        items, output_path = prompt_interactive(per_page)

    total, pages, cap = generate_a4_pdf(
        template_path=args.template,
        items=items,
        output_path=output_path,
        orientation=args.orientation,
        margin_mm=args.margin,
        gap_mm=args.gap,
        common_labels=args.common_labels,
        set_mode=args.set_mode,
    )

    print(
        f"\nTayyor! {output_path.resolve()}\n"
        f"  Stiker o'lchami : {lr.width / MM_TO_PT:.2f} mm x {lr.height / MM_TO_PT:.2f} mm (o'zgarmagan)\n"
        f"  A4 joylashuvi   : {cols} ustun x {rows} qator = {cap} dona/sahifa ({args.orientation})\n"
        f"  Jami etiketka   : {total} dona ({pages} ta A4 sahifa)"
    )


if __name__ == "__main__":
    main()
