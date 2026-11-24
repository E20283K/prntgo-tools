"""FastAPI Backend & Web UI Server for PrintHub."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import mimetypes
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.auth import (
    clear_session_cookie,
    is_auth_enabled,
    require_auth,
    set_session_cookie,
    verify_password,
    verify_session_token,
)
from app.config import JOB_CLEANUP_INTERVAL_MINUTES, SESSION_COOKIE_NAME, VECTORCRAFT_WEB_DIR
from app.corel_converter import (
    COREL_VERSIONS,
    DEFAULT_COREL_VERSION,
    build_cdr_bundle_zip,
    build_standalone_converter_zip,
)
from app.jobs import cleanup_old_jobs, get_job_output_file
from app.services import (
    claude_design_service,
    claude_terminal_service,
    extractor_service,
    label_imp_service,
    print_imp_service,
    sela_service,
)

# Ensure WebAssembly & Font MIME types are registered for VectorCraft Web
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("font/ttf", ".ttf")

logger = logging.getLogger("printhub.api")
STATIC_DIR = Path(__file__).resolve().parent / "static"
VECTORCRAFT_WEB_DIR.mkdir(parents=True, exist_ok=True)


async def _periodic_job_cleanup() -> None:
    interval_sec = max(60, JOB_CLEANUP_INTERVAL_MINUTES * 60)
    while True:
        try:
            claude_terminal_service.PTY_MANAGER.check_idle_cleanup()
            removed = await asyncio.to_thread(cleanup_old_jobs)
            if removed > 0:
                logger.info("Avto-tozalash: %d ta eski job papkasi o'chirildi.", removed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Avto-tozalashda xato: %s", exc)
        await asyncio.sleep(interval_sec)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    claude_design_service.start_background_tools_bootstrap()
    task = asyncio.create_task(_periodic_job_cleanup())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="PrintHub — Poligrafiya & Etiketka Platformasi",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if VECTORCRAFT_WEB_DIR.is_dir():
    app.mount("/vectorcraft", StaticFiles(directory=str(VECTORCRAFT_WEB_DIR), html=True), name="vectorcraft")


# ---------------------------------------------------------------------------
# Health & Root Web UI
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    idx = STATIC_DIR / "index.html"
    if not idx.is_file():
        return HTMLResponse("<h1>PrintHub API ishlamoqda</h1>")
    return HTMLResponse(idx.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Authentication (PIN / Password)
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    password: str


@app.get("/api/auth/status")
def auth_status(request: Request) -> Dict[str, bool]:
    enabled = is_auth_enabled()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = (not enabled) or verify_session_token(token)
    return {"auth_enabled": enabled, "authenticated": authenticated}


@app.post("/api/auth/login")
def auth_login(body: LoginRequest, response: Response) -> Dict[str, Any]:
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Parol yoki PIN noto'g'ri.")
    set_session_cookie(response)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(response: Response) -> Dict[str, Any]:
    clear_session_cookie(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Shared Job File Download / Preview & Universal PDF-to-PNG Renderer
# ---------------------------------------------------------------------------
def _render_pdf_bytes_to_png_response(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    page: int = 0,
    dpi: int = 180,
) -> Response:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total_pages = doc.page_count
        if total_pages < 1:
            raise ValueError("PDF sahifalari topilmadi.")
        idx = max(0, min(page, total_pages - 1))
        pix = doc[idx].get_pixmap(dpi=dpi, alpha=False)
        png_bytes = pix.tobytes("png")
    finally:
        doc.close()

    safe_stem = Path(filename).stem
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{safe_stem}_p{idx + 1}.png"',
            "X-Page-Count": str(total_pages),
            "X-Page-Index": str(idx),
            "Access-Control-Expose-Headers": "X-Page-Count, X-Page-Index",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/pdf/render-page", dependencies=[Depends(require_auth)])
async def render_pdf_page_endpoint(
    file: UploadFile = File(...),
    page: int = Query(0, ge=0),
    dpi: int = Query(180, ge=72, le=300),
) -> Response:
    try:
        raw = await file.read()
        return await asyncio.to_thread(
            _render_pdf_bytes_to_png_response,
            raw,
            file.filename or "preview.pdf",
            page,
            dpi,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/jobs/{job_id}/files/{filename}", dependencies=[Depends(require_auth)])
def download_job_file(
    job_id: str,
    filename: str,
    inline: bool = Query(False),
    format: Optional[str] = Query(None),
    page: int = Query(0, ge=0),
    dpi: int = Query(180, ge=72, le=300),
) -> Response:
    try:
        path = get_job_output_file(job_id, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ext = path.suffix.lower()
    if format and format.lower() == "png" and ext == ".pdf":
        try:
            return _render_pdf_bytes_to_png_response(path.read_bytes(), path.name, page=page, dpi=dpi)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    media_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".eps": "application/postscript",
        ".zip": "application/zip",
        ".vectorcraft": "application/octet-stream",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    if inline or ext == ".png":
        return FileResponse(
            str(path),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{path.name}"'},
        )
    return FileResponse(str(path), media_type=media_type, filename=path.name)


# ---------------------------------------------------------------------------
# CorelDRAW (.cdr) Auto-Converter & Bundle Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/corel/versions", dependencies=[Depends(require_auth)])
def corel_versions() -> Dict[str, Any]:
    return {
        "default_version": DEFAULT_COREL_VERSION,
        "versions": COREL_VERSIONS,
    }


@app.get("/api/jobs/{job_id}/cdr-bundle", dependencies=[Depends(require_auth)])
def download_job_cdr_bundle(
    job_id: str,
    filename: Optional[str] = Query(None),
    version: int = Query(DEFAULT_COREL_VERSION, ge=12, le=26),
    ask: bool = Query(False),
) -> Response:
    try:
        zip_bytes, zip_name = build_cdr_bundle_zip(
            job_id=job_id,
            filename=filename,
            target_version=version,
            ask_version=ask,
            keep_open_in_corel=True,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.get("/api/corel/standalone-converter", dependencies=[Depends(require_auth)])
def download_standalone_cdr_converter(
    version: int = Query(DEFAULT_COREL_VERSION, ge=12, le=26),
    ask: bool = Query(False),
) -> Response:
    zip_bytes, zip_name = build_standalone_converter_zip(
        target_version=version,
        ask_version=ask,
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


# ---------------------------------------------------------------------------
# 1. SELA GENERATOR ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/api/sela/config", dependencies=[Depends(require_auth)])
def sela_config() -> Dict[str, Any]:
    return {
        "templates": sela_service.list_templates(),
        "set_catalog": sela_service.list_set_catalog(),
    }


@app.post("/api/sela/template", dependencies=[Depends(require_auth)])
async def sela_upload_template(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        raw = await file.read()
        return await asyncio.to_thread(
            sela_service.save_uploaded_template,
            file.filename or "template.pdf",
            raw,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sela/preview", dependencies=[Depends(require_auth)])
def sela_preview(
    artikul: str = Query("SI7804050205"),
    colour: str = Query("33"),
    size: str = Query("104/ 4-5 YEARS"),
    barcode: str = Query("4620544686957"),
    template_name: Optional[str] = Query(None),
) -> Response:
    try:
        pdf_bytes = sela_service.preview_label_pdf(
            artikul=artikul,
            colour=colour,
            size=size,
            barcode=barcode,
            template_name=template_name,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="sela_preview.pdf"'},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sela/set-preview/{filename}", dependencies=[Depends(require_auth)])
def sela_set_preview(
    filename: str,
    format: str = Query("pdf"),
    dpi: int = Query(150, ge=72, le=300),
) -> Response:
    try:
        safe_stem = Path(filename).stem
        if format.lower() == "png":
            png_bytes = sela_service.preview_static_set_png(filename, dpi=dpi)
            return Response(
                content=png_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f'inline; filename="{safe_stem}.png"',
                    "Cache-Control": "private, max-age=86400",
                },
            )
        pdf_bytes = sela_service.preview_static_set_pdf(filename)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{safe_stem}.pdf"',
                "Cache-Control": "private, max-age=3600",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/sela/generate", dependencies=[Depends(require_auth)])
async def sela_generate(
    items_json: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    orientation: str = Form("portrait"),
    margin_mm: float = Form(5.0),
    gap_mm: float = Form(2.0),
    general_sets_json: Optional[str] = Form(None),
    sostav_key: Optional[str] = Form(None),
    set_mode: str = Form("end"),
    csv_file: Optional[UploadFile] = File(None),
    template_file: Optional[UploadFile] = File(None),
) -> Dict[str, Any]:
    try:
        items_payload = json.loads(items_json) if items_json else None
        general_sets = json.loads(general_sets_json) if general_sets_json else []
        csv_bytes = await csv_file.read() if csv_file else None
        tpl_bytes = await template_file.read() if template_file else None

        return await asyncio.to_thread(
            sela_service.generate_sela_job,
            items_payload=items_payload,
            csv_bytes=csv_bytes,
            csv_filename=csv_file.filename if csv_file else None,
            template_name=template_name or None,
            template_bytes=tpl_bytes,
            template_upload_name=template_file.filename if template_file else None,
            orientation=orientation,
            margin_mm=margin_mm,
            gap_mm=gap_mm,
            general_sets=general_sets,
            sostav_key=sostav_key or None,
            set_mode=set_mode,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 2. LABEL IMPOSITION (FLEXO / GEAR) ENDPOINTS
# ---------------------------------------------------------------------------
class GearToggleRequest(BaseModel):
    available: bool


class GearUpsertRequest(BaseModel):
    gear: int
    pitch_diameter: float
    plate_thickness: float = 1.7
    cylinder_diameter: float
    film_length: float
    printing_length: float
    available: bool = True


@app.get("/api/label-imp/gears", dependencies=[Depends(require_auth)])
def label_imp_gears() -> Dict[str, Any]:
    return label_imp_service.list_gears()


@app.post("/api/label-imp/gears", dependencies=[Depends(require_auth)])
def label_imp_upsert_gear(body: GearUpsertRequest) -> Dict[str, Any]:
    try:
        return label_imp_service.upsert_gear(body.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/label-imp/gears/{gear_num}", dependencies=[Depends(require_auth)])
def label_imp_toggle_gear(gear_num: int, body: GearToggleRequest) -> Dict[str, Any]:
    try:
        return label_imp_service.toggle_gear(gear_num, body.available)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/label-imp/gears/{gear_num}", dependencies=[Depends(require_auth)])
def label_imp_delete_gear(gear_num: int) -> Dict[str, Any]:
    try:
        return label_imp_service.delete_gear(gear_num)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/label-imp/inspect", dependencies=[Depends(require_auth)])
async def label_imp_inspect(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    from_job_id: Optional[str] = Form(None),
    from_filename: Optional[str] = Form(None),
    rotation_mode: str = Form("auto"),
    custom_gear: Optional[str] = Form(None),
    custom_copies: Optional[str] = Form(None),
) -> Dict[str, Any]:
    try:
        uploaded: List[tuple[str, bytes]] = []
        if file and file.filename:
            uploaded.append((file.filename, await file.read()))
        for f in (files or []):
            if f.filename:
                uploaded.append((f.filename, await f.read()))

        gear_val = int(custom_gear) if (custom_gear and custom_gear.strip().isdigit()) else None
        copies_val = int(custom_copies) if (custom_copies and custom_copies.strip().isdigit()) else None

        return await asyncio.to_thread(
            label_imp_service.inspect_pdf_sources,
            uploaded_files=uploaded,
            from_job_id=from_job_id or None,
            from_filename=from_filename or None,
            rotation_mode=rotation_mode,
            custom_gear=gear_val,
            custom_copies=copies_val,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/label-imp/preview", dependencies=[Depends(require_auth)])
async def label_imp_preview(
    files: Optional[List[UploadFile]] = File(None),
    from_job_id: Optional[str] = Form(None),
    from_filename: Optional[str] = Form(None),
    custom_gear: Optional[str] = Form(None),
    custom_copies: Optional[str] = Form(None),
    rotation_mode: str = Form("auto"),
    combine_same_gear: bool = Form(True),
    separate_colors: bool = Form(True),
    color_output_mode: str = Form("side_by_side"),
    remove_outer_border: bool = Form(True),
    regmark_enabled: bool = Form(True),
    regmark_stroke_mm: float = Form(0.2),
    regmark_tick_mm: float = Form(0.7),
    regmark_custom_width_mm: Optional[str] = Form(None),
    column_gap_mm: float = Form(5.0),
    max_cylinder_width_mm: float = Form(0.0),
    design_index: Optional[str] = Form(None),
) -> Response:
    try:
        uploaded: List[tuple[str, bytes]] = []
        for f in (files or []):
            if f.filename:
                uploaded.append((f.filename, await f.read()))

        gear_val = int(custom_gear) if (custom_gear and custom_gear.strip().isdigit()) else None
        copies_val = int(custom_copies) if (custom_copies and custom_copies.strip().isdigit()) else None
        rm_w = float(regmark_custom_width_mm) if (regmark_custom_width_mm and regmark_custom_width_mm.strip()) else None
        d_idx = int(design_index) if (design_index is not None and design_index.strip().isdigit()) else None

        pdf_bytes, page_count = await asyncio.to_thread(
            label_imp_service.preview_label_imposition_pdf,
            uploaded_files=uploaded,
            from_job_id=from_job_id or None,
            from_filename=from_filename or None,
            custom_gear=gear_val,
            custom_copies=copies_val,
            rotation_mode=rotation_mode,
            combine_same_gear=combine_same_gear,
            separate_colors=separate_colors,
            color_output_mode=color_output_mode,
            remove_outer_border=remove_outer_border,
            regmark_enabled=regmark_enabled,
            regmark_stroke_mm=regmark_stroke_mm,
            regmark_tick_mm=regmark_tick_mm,
            regmark_custom_width_mm=rm_w,
            column_gap_mm=column_gap_mm,
            max_cylinder_width_mm=max_cylinder_width_mm,
            design_index=d_idx,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="label_imp_preview.pdf"',
                "X-Preview-Pages": str(page_count),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/label-imp/run", dependencies=[Depends(require_auth)])
async def label_imp_run(
    files: Optional[List[UploadFile]] = File(None),
    from_job_id: Optional[str] = Form(None),
    from_filename: Optional[str] = Form(None),
    custom_gear: Optional[str] = Form(None),
    custom_copies: Optional[str] = Form(None),
    rotation_mode: str = Form("auto"),
    combine_same_gear: bool = Form(True),
    separate_colors: bool = Form(True),
    color_output_mode: str = Form("side_by_side"),
    remove_outer_border: bool = Form(True),
    regmark_enabled: bool = Form(True),
    regmark_stroke_mm: float = Form(0.2),
    regmark_tick_mm: float = Form(0.7),
    regmark_custom_width_mm: Optional[str] = Form(None),
    column_gap_mm: float = Form(5.0),
    max_cylinder_width_mm: float = Form(0.0),
    export_svg: bool = Form(False),
    export_eps: bool = Form(False),
) -> Dict[str, Any]:
    try:
        uploaded: List[tuple[str, bytes]] = []
        for f in (files or []):
            if f.filename:
                uploaded.append((f.filename, await f.read()))

        gear_val = int(custom_gear) if (custom_gear and custom_gear.strip().isdigit()) else None
        copies_val = int(custom_copies) if (custom_copies and custom_copies.strip().isdigit()) else None
        rm_w = float(regmark_custom_width_mm) if (regmark_custom_width_mm and regmark_custom_width_mm.strip()) else None

        return await asyncio.to_thread(
            label_imp_service.run_label_imposition_job,
            uploaded_files=uploaded,
            from_job_id=from_job_id or None,
            from_filename=from_filename or None,
            custom_gear=gear_val,
            custom_copies=copies_val,
            rotation_mode=rotation_mode,
            combine_same_gear=combine_same_gear,
            separate_colors=separate_colors,
            color_output_mode=color_output_mode,
            remove_outer_border=remove_outer_border,
            regmark_enabled=regmark_enabled,
            regmark_stroke_mm=regmark_stroke_mm,
            regmark_tick_mm=regmark_tick_mm,
            regmark_custom_width_mm=rm_w,
            column_gap_mm=column_gap_mm,
            max_cylinder_width_mm=max_cylinder_width_mm,
            export_svg=export_svg,
            export_eps=export_eps,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 3. PRINT IMPOSITION (OFFSET / DIGITAL SHEET) ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/api/print-imp/presets", dependencies=[Depends(require_auth)])
def print_imp_presets() -> Dict[str, Any]:
    return {"presets": print_imp_service.PRESETS}


@app.post("/api/print-imp/preflight", dependencies=[Depends(require_auth)])
async def print_imp_preflight(
    front_files: Optional[List[UploadFile]] = File(None),
    dieline_file: Optional[UploadFile] = File(None),
    from_job_id: Optional[str] = Form(None),
    from_front_filenames_json: Optional[str] = Form(None),
    from_dieline_filename: Optional[str] = Form(None),
    trim_w_mm: Optional[str] = Form(None),
    trim_h_mm: Optional[str] = Form(None),
) -> Dict[str, Any]:
    try:
        fronts: List[tuple[str, bytes]] = []
        if from_job_id and from_front_filenames_json:
            fnames = json.loads(from_front_filenames_json)
            for fn in fnames:
                p = get_job_output_file(from_job_id, fn)
                fronts.append((p.name, p.read_bytes()))
        for f in (front_files or []):
            if f.filename:
                fronts.append((f.filename, await f.read()))
        if not fronts:
            raise ValueError("Kamida bitta Oldi (Front) PDF fayl tanlang.")

        dieline = None
        if dieline_file and dieline_file.filename:
            dieline = (dieline_file.filename, await dieline_file.read())
        elif from_job_id and from_dieline_filename:
            dp = get_job_output_file(from_job_id, from_dieline_filename)
            dieline = (dp.name, dp.read_bytes())

        expected = None
        if trim_w_mm and trim_h_mm and trim_w_mm.strip() and trim_h_mm.strip():
            expected = (float(trim_w_mm), float(trim_h_mm))
        return await asyncio.to_thread(
            print_imp_service.run_preflight_analysis, fronts, dieline, expected
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/print-imp/run", dependencies=[Depends(require_auth)])
async def print_imp_run(
    front_files: Optional[List[UploadFile]] = File(None),
    back_file: Optional[UploadFile] = File(None),
    dieline_file: Optional[UploadFile] = File(None),
    from_job_id: Optional[str] = Form(None),
    from_front_filenames_json: Optional[str] = Form(None),
    from_dieline_filename: Optional[str] = Form(None),
    sheet_w_mm: float = Form(500.0),
    sheet_h_mm: float = Form(350.0),
    trim_w_mm: Optional[str] = Form(None),
    trim_h_mm: Optional[str] = Form(None),
    bleed_mm: float = Form(1.5),
    inner_bleed_mm: float = Form(1.5),
    outer_bleed_mm: float = Form(3.0),
    gutter_mm: float = Form(3.0),
    gripper_mm: float = Form(15.0),
    crop_gap_mm: float = Form(1.0),
    mode: str = Form("single"),
    style: str = Form("offset_standard"),
    category: str = Form("guillotine"),
    cut_style: str = Form("double"),
    alignment: str = Form("center"),
    order_number: str = Form("№1001"),
    job_name: Optional[str] = Form(None),
    order_quantity: int = Form(1000),
    waste_sheets: int = Form(0),
    separate_files: bool = Form(False),
    multi_mode: str = Form("pages"),
    quantities_csv: Optional[str] = Form(None),
    strategy: str = Form("smart"),
    max_overprint_pct: float = Form(10.0),
    fill_dir: str = Form("col"),
) -> Dict[str, Any]:
    try:
        fronts: List[tuple[str, bytes]] = []
        if from_job_id and from_front_filenames_json:
            fnames = json.loads(from_front_filenames_json)
            for fn in fnames:
                p = get_job_output_file(from_job_id, fn)
                fronts.append((p.name, p.read_bytes()))
        for f in (front_files or []):
            if f.filename:
                fronts.append((f.filename, await f.read()))
        if not fronts:
            raise ValueError("Kamida bitta Oldi (Front) PDF fayl tanlang.")

        back = (back_file.filename or "back.pdf", await back_file.read()) if (back_file and back_file.filename) else None
        dieline = None
        if dieline_file and dieline_file.filename:
            dieline = (dieline_file.filename, await dieline_file.read())
        elif from_job_id and from_dieline_filename:
            dp = get_job_output_file(from_job_id, from_dieline_filename)
            dieline = (dp.name, dp.read_bytes())

        tw = float(trim_w_mm) if (trim_w_mm and trim_w_mm.strip()) else None
        th = float(trim_h_mm) if (trim_h_mm and trim_h_mm.strip()) else None
        qtys = None
        if quantities_csv and quantities_csv.strip():
            qtys = [int(x.strip()) for x in quantities_csv.split(",") if x.strip().isdigit()]

        return await asyncio.to_thread(
            print_imp_service.run_print_imposition_job,
            front_files=fronts,
            back_file=back,
            dieline_file=dieline,
            sheet_w_mm=sheet_w_mm,
            sheet_h_mm=sheet_h_mm,
            trim_w_mm=tw,
            trim_h_mm=th,
            bleed_mm=bleed_mm,
            inner_bleed_mm=inner_bleed_mm,
            outer_bleed_mm=outer_bleed_mm,
            gutter_mm=gutter_mm,
            gripper_mm=gripper_mm,
            crop_gap_mm=crop_gap_mm,
            mode=mode,
            style=style,
            category=category,
            cut_style=cut_style,
            alignment=alignment,
            order_number=order_number,
            job_name=job_name or None,
            order_quantity=order_quantity,
            waste_sheets=waste_sheets,
            separate_files=separate_files,
            multi_mode=multi_mode,
            quantities=qtys,
            strategy=strategy,
            max_overprint_pct=max_overprint_pct,
            fill_dir=fill_dir,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 4. DESIGN & DIELINE EXTRACTOR ENDPOINTS
# ---------------------------------------------------------------------------
class ExtractorSearchSizeRequest(BaseModel):
    source_job_id: str
    width_mm: float
    height_mm: float
    tolerance_mm: float = 3.0
    page_index: Optional[int] = None


class ExtractorRunRequest(BaseModel):
    source_job_id: str
    items: List[Dict[str, Any]]
    remove_border: bool = False
    remove_hole: bool = False
    bleed_mm: float = 0.0
    rotation_deg: int = 0


@app.post("/api/extractor/inspect", dependencies=[Depends(require_auth)])
async def extractor_inspect(
    file: UploadFile = File(...),
    target_w_mm: Optional[str] = Form(None),
    target_h_mm: Optional[str] = Form(None),
) -> Dict[str, Any]:
    try:
        raw = await file.read()
        tw = float(target_w_mm) if (target_w_mm and target_w_mm.strip()) else None
        th = float(target_h_mm) if (target_h_mm and target_h_mm.strip()) else None
        return await asyncio.to_thread(
            extractor_service.inspect_pdf_for_extraction,
            filename=file.filename or "document.pdf",
            raw_bytes=raw,
            target_w_mm=tw,
            target_h_mm=th,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/extractor/search-size", dependencies=[Depends(require_auth)])
async def extractor_search_size(body: ExtractorSearchSizeRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            extractor_service.search_pdf_by_dimensions,
            source_job_id=body.source_job_id,
            width_mm=body.width_mm,
            height_mm=body.height_mm,
            tolerance_mm=body.tolerance_mm,
            page_index=body.page_index,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/extractor/run", dependencies=[Depends(require_auth)])
async def extractor_run(body: ExtractorRunRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            extractor_service.run_extraction_job,
            source_job_id=body.source_job_id,
            items=body.items,
            remove_border=body.remove_border,
            remove_hole=body.remove_hole,
            bleed_mm=body.bleed_mm,
            rotation_deg=body.rotation_deg,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 5. AI DESIGN STUDIO (CLAUDE CODE + VECTORCRAFT MCP + SKILLS & ASSETS)
# ---------------------------------------------------------------------------
class ClaudeAuthTokenRequest(BaseModel):
    oauth_token: Optional[str] = None
    api_key: Optional[str] = None


class ClaudeLoginCodeRequest(BaseModel):
    code: str


class SkillSaveRequest(BaseModel):
    slug: Optional[str] = None
    name: str
    description: str = ""
    content: str


class WorkspaceConfigSaveRequest(BaseModel):
    mcp_json: Optional[str] = None
    claude_md: Optional[str] = None


@app.get("/api/ai-design/status", dependencies=[Depends(require_auth)])
async def ai_design_status() -> Dict[str, Any]:
    return await asyncio.to_thread(claude_design_service.get_system_status)


@app.post("/api/ai-design/auth/token", dependencies=[Depends(require_auth)])
async def ai_design_save_token(body: ClaudeAuthTokenRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            claude_design_service.save_auth_env,
            oauth_token=body.oauth_token,
            api_key=body.api_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/auth/login/start", dependencies=[Depends(require_auth)])
async def ai_design_start_login() -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(claude_design_service.start_claude_login)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/auth/login/code", dependencies=[Depends(require_auth)])
async def ai_design_submit_login_code(body: ClaudeLoginCodeRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(claude_design_service.submit_claude_login_code, body.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai-design/auth/login/state", dependencies=[Depends(require_auth)])
def ai_design_login_state() -> Dict[str, Any]:
    return claude_design_service.get_login_session_state()


@app.get("/api/ai-design/skills", dependencies=[Depends(require_auth)])
def ai_design_list_skills() -> Dict[str, Any]:
    return {"skills": claude_design_service.list_skills()}


@app.get("/api/ai-design/skills/{slug}", dependencies=[Depends(require_auth)])
def ai_design_get_skill(slug: str) -> Dict[str, Any]:
    try:
        return claude_design_service.get_skill(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/ai-design/skills", dependencies=[Depends(require_auth)])
def ai_design_save_skill(body: SkillSaveRequest) -> Dict[str, Any]:
    try:
        return claude_design_service.save_skill(
            name=body.name,
            description=body.description,
            content=body.content,
            slug=body.slug,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/ai-design/skills/{slug}", dependencies=[Depends(require_auth)])
def ai_design_delete_skill(slug: str) -> Dict[str, Any]:
    try:
        return claude_design_service.delete_skill(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/ai-design/skills/{slug}/files", dependencies=[Depends(require_auth)])
async def ai_design_upload_skill_file(slug: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        raw = await file.read()
        return await asyncio.to_thread(
            claude_design_service.upload_skill_file,
            slug=slug,
            filename=file.filename or "resource.bin",
            raw_bytes=raw,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/ai-design/skills/{slug}/files/{filename}", dependencies=[Depends(require_auth)])
def ai_design_delete_skill_file(slug: str, filename: str) -> Dict[str, Any]:
    try:
        return claude_design_service.delete_skill_file(slug, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/ai-design/assets", dependencies=[Depends(require_auth)])
def ai_design_list_assets() -> Dict[str, Any]:
    return {"assets": claude_design_service.list_assets()}


@app.post("/api/ai-design/assets", dependencies=[Depends(require_auth)])
async def ai_design_upload_assets(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    try:
        uploaded = []
        for f in files:
            if f.filename:
                raw = await f.read()
                item = await asyncio.to_thread(claude_design_service.save_asset, f.filename, raw)
                uploaded.append(item)
        return {"uploaded": uploaded, "assets": claude_design_service.list_assets()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai-design/assets/{filename}", dependencies=[Depends(require_auth)])
def ai_design_download_asset(filename: str) -> FileResponse:
    try:
        path = claude_design_service.get_asset_path(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(str(path), filename=path.name)


@app.delete("/api/ai-design/assets/{filename}", dependencies=[Depends(require_auth)])
def ai_design_delete_asset(filename: str) -> Dict[str, Any]:
    try:
        return claude_design_service.delete_asset(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/ai-design/workspace-config", dependencies=[Depends(require_auth)])
def ai_design_get_workspace_config() -> Dict[str, Any]:
    return claude_design_service.get_workspace_config()


@app.post("/api/ai-design/workspace-config", dependencies=[Depends(require_auth)])
def ai_design_save_workspace_config(body: WorkspaceConfigSaveRequest) -> Dict[str, Any]:
    try:
        return claude_design_service.save_workspace_config(
            mcp_json=body.mcp_json,
            claude_md=body.claude_md,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/generate", dependencies=[Depends(require_auth)])
async def ai_design_generate(
    prompt: str = Form(...),
    skill_slugs_json: Optional[str] = Form(None),
    asset_names_json: Optional[str] = Form(None),
    width_mm: Optional[str] = Form(None),
    height_mm: Optional[str] = Form(None),
    output_basename: str = Form("design"),
    source_job_id: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
) -> Dict[str, Any]:
    try:
        skill_slugs = json.loads(skill_slugs_json) if skill_slugs_json else []
        asset_names = json.loads(asset_names_json) if asset_names_json else []
        w_mm = float(width_mm) if (width_mm and width_mm.strip()) else None
        h_mm = float(height_mm) if (height_mm and height_mm.strip()) else None

        uploaded_files: List[tuple[str, bytes]] = []
        for f in (files or []):
            if f.filename:
                uploaded_files.append((f.filename, await f.read()))

        return await asyncio.to_thread(
            claude_design_service.run_ai_design_job,
            prompt=prompt,
            skill_slugs=skill_slugs,
            asset_names=asset_names,
            width_mm=w_mm,
            height_mm=h_mm,
            output_basename=output_basename,
            uploaded_files=uploaded_files,
            source_job_id=source_job_id,
            source_filename=source_filename,
            model=model,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/editor-export", dependencies=[Depends(require_auth)])
async def ai_design_editor_export(
    file: UploadFile = File(...),
    save_to_assets: bool = Form(False),
) -> Dict[str, Any]:
    try:
        raw = await file.read()
        return await asyncio.to_thread(
            claude_design_service.export_vectorcraft_document,
            filename=file.filename or "design.vectorcraft",
            raw_bytes=raw,
            save_to_assets=save_to_assets,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/jobs/{job_id}/save-asset", dependencies=[Depends(require_auth)])
async def ai_design_save_job_asset(job_id: str, filename: str = Form(...)) -> Dict[str, Any]:
    try:
        item = await asyncio.to_thread(claude_design_service.save_job_file_to_assets, job_id, filename)
        return {"saved": item, "assets": claude_design_service.list_assets()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai-design/install-vectorcraft-web", dependencies=[Depends(require_auth)])
async def ai_design_install_vectorcraft_web() -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(claude_design_service.install_vectorcraft_web_bundle)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 6. INTERACTIVE CLAUDE CODE WEB TERMINAL (PTY + WebSocket + Uploads/Outputs)
# ---------------------------------------------------------------------------
class TerminalRestartRequest(BaseModel):
    mode: str = "claude"  # "claude" | "bash"
    cols: int = 120
    rows: int = 34


@app.post("/api/ai-design/terminal/restart", dependencies=[Depends(require_auth)])
async def ai_design_terminal_restart(body: TerminalRestartRequest) -> Dict[str, Any]:
    await asyncio.to_thread(
        claude_terminal_service.PTY_MANAGER.ensure_started,
        mode=body.mode,
        cols=body.cols,
        rows=body.rows,
        force_restart=True,
    )
    return {"ok": True, "mode": body.mode}


@app.post("/api/ai-design/terminal/upload", dependencies=[Depends(require_auth)])
async def ai_design_terminal_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        raw = await file.read()
        return await asyncio.to_thread(
            claude_design_service.save_terminal_upload,
            filename=file.filename or "screenshot.png",
            raw_bytes=raw,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai-design/terminal/uploads", dependencies=[Depends(require_auth)])
def ai_design_terminal_list_uploads() -> Dict[str, Any]:
    return {"uploads": claude_design_service.list_terminal_uploads()}


@app.get("/api/ai-design/terminal/outputs", dependencies=[Depends(require_auth)])
async def ai_design_terminal_list_outputs(sync: bool = Query(False)) -> Dict[str, Any]:
    return await asyncio.to_thread(claude_design_service.list_terminal_outputs, sync_dual=sync)


@app.get("/api/ai-design/terminal/outputs/{filename}", dependencies=[Depends(require_auth)])
def ai_design_terminal_download_output(
    filename: str,
    inline: bool = Query(False),
    format: Optional[str] = Query(None),
    page: int = Query(0, ge=0),
    dpi: int = Query(180, ge=72, le=300),
) -> Response:
    try:
        path = claude_design_service.get_terminal_output_path(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ext = path.suffix.lower()
    if format and format.lower() == "png" and ext == ".pdf":
        try:
            return _render_pdf_bytes_to_png_response(path.read_bytes(), path.name, page=page, dpi=dpi)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    media_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".vectorcraft": "application/octet-stream",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    if inline or ext == ".png":
        return FileResponse(
            str(path),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{path.name}"'},
        )
    return FileResponse(str(path), media_type=media_type, filename=path.name)


@app.delete("/api/ai-design/terminal/outputs/{filename}", dependencies=[Depends(require_auth)])
def ai_design_terminal_delete_output(filename: str) -> Dict[str, Any]:
    return claude_design_service.delete_terminal_output(filename)


@app.post("/api/ai-design/terminal/outputs/{filename}/to-job", dependencies=[Depends(require_auth)])
async def ai_design_terminal_output_to_job(filename: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(claude_design_service.promote_terminal_output_to_job, filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.websocket("/api/ai-design/terminal/ws")
async def ai_design_terminal_ws(
    websocket: WebSocket,
    mode: str = Query("claude"),
    cols: int = Query(120),
    rows: int = Query(34),
) -> None:
    if is_auth_enabled():
        token = websocket.cookies.get(SESSION_COOKIE_NAME)
        if not verify_session_token(token):
            await websocket.close(code=4401)
            return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    await asyncio.to_thread(
        claude_terminal_service.PTY_MANAGER.ensure_started,
        mode=mode,
        cols=cols,
        rows=rows,
        force_restart=False,
    )

    # Send scrollback buffer immediately so the user sees the current screen
    scrollback = claude_terminal_service.PTY_MANAGER.get_scrollback()
    if scrollback:
        await websocket.send_bytes(scrollback)

    def _on_pty_output(chunk: bytes) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    claude_terminal_service.PTY_MANAGER.add_listener(_on_pty_output)

    async def _sender() -> None:
        while True:
            chunk = await queue.get()
            await websocket.send_bytes(chunk)

    sender_task = asyncio.create_task(_sender())
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"] is not None:
                await asyncio.to_thread(
                    claude_terminal_service.PTY_MANAGER.write_input,
                    msg["bytes"],
                )
            elif "text" in msg and msg["text"] is not None:
                txt = msg["text"]
                if txt.startswith("{") and '"type"' in txt:
                    try:
                        ctrl = json.loads(txt)
                        if ctrl.get("type") == "resize":
                            c = int(ctrl.get("cols", 120))
                            r = int(ctrl.get("rows", 34))
                            await asyncio.to_thread(
                                claude_terminal_service.PTY_MANAGER.resize, c, r
                            )
                            continue
                        if ctrl.get("type") == "input":
                            raw_in = str(ctrl.get("data", "")).encode("utf-8")
                            await asyncio.to_thread(
                                claude_terminal_service.PTY_MANAGER.write_input,
                                raw_in,
                            )
                            continue
                    except Exception:
                        pass
                await asyncio.to_thread(
                    claude_terminal_service.PTY_MANAGER.write_input,
                    txt.encode("utf-8"),
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Terminal WS closed: %s", exc)
    finally:
        claude_terminal_service.PTY_MANAGER.remove_listener(_on_pty_output)
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass



