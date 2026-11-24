"""FastAPI Backend & Web UI Server for PrintHub."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
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
from app.config import JOB_CLEANUP_INTERVAL_MINUTES, SESSION_COOKIE_NAME
from app.corel_converter import (
    COREL_VERSIONS,
    DEFAULT_COREL_VERSION,
    build_cdr_bundle_zip,
    build_standalone_converter_zip,
)
from app.jobs import cleanup_old_jobs, get_job_output_file
from app.services import label_imp_service, print_imp_service, sela_service

logger = logging.getLogger("printhub.api")
STATIC_DIR = Path(__file__).resolve().parent / "static"


async def _periodic_job_cleanup() -> None:
    interval_sec = max(60, JOB_CLEANUP_INTERVAL_MINUTES * 60)
    while True:
        try:
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
# Shared Job File Download / Preview
# ---------------------------------------------------------------------------
@app.get("/api/jobs/{job_id}/files/{filename}", dependencies=[Depends(require_auth)])
def download_job_file(job_id: str, filename: str, inline: bool = Query(False)) -> FileResponse:
    try:
        path = get_job_output_file(job_id, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ext = path.suffix.lower()
    media_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".eps": "application/postscript",
        ".zip": "application/zip",
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
    front_files: List[UploadFile] = File(...),
    dieline_file: Optional[UploadFile] = File(None),
    trim_w_mm: Optional[str] = Form(None),
    trim_h_mm: Optional[str] = Form(None),
) -> Dict[str, Any]:
    try:
        fronts = [(f.filename or "front.pdf", await f.read()) for f in front_files]
        dieline = (dieline_file.filename or "dieline.pdf", await dieline_file.read()) if dieline_file else None
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
    front_files: List[UploadFile] = File(...),
    back_file: Optional[UploadFile] = File(None),
    dieline_file: Optional[UploadFile] = File(None),
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
        fronts = [(f.filename or "front.pdf", await f.read()) for f in front_files]
        back = (back_file.filename or "back.pdf", await back_file.read()) if back_file else None
        dieline = (dieline_file.filename or "dieline.pdf", await dieline_file.read()) if dieline_file else None

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
