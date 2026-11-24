"""User-friendly Uzbek Telegram Bot handlers for all 3 PrintHub tools."""

from __future__ import annotations

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Any, Callable, Awaitable, Dict

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    WebAppInfo,
)

from app.config import PUBLIC_URL, get_allowed_telegram_ids
from app.corel_converter import build_cdr_bundle_zip
from app.jobs import get_job_output_file
from app.services import claude_design_service, label_imp_service, print_imp_service, sela_service

router = Router()


# ---------------------------------------------------------------------------
# Access Control Middleware (ALLOWED_TELEGRAM_IDS)
# ---------------------------------------------------------------------------
class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        allowed = get_allowed_telegram_ids()
        if not allowed:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user and user.id in allowed:
            return await handler(event, data)

        uid = user.id if user else "noma'lum"
        msg_text = (
            f"⛔ Sizda ushbu botdan foydalanish ruxsati yo'q.\n"
            f"Admin ruxsat berishi uchun ID raqamingiz: <code>{uid}</code>"
        )
        if isinstance(event, Message):
            await event.answer(msg_text)
        elif isinstance(event, CallbackQuery):
            await event.answer("Ruxsat yo'q", show_alert=True)
        return None


# ---------------------------------------------------------------------------
# FSM States
# ---------------------------------------------------------------------------
class SelaStates(StatesGroup):
    waiting_mode = State()
    waiting_artikul = State()
    waiting_colour = State()
    waiting_size = State()
    waiting_barcode = State()
    waiting_qty = State()
    waiting_csv = State()


class LabelImpStates(StatesGroup):
    waiting_pdf = State()
    confirm_run = State()
    waiting_custom_gear = State()


class PrintImpStates(StatesGroup):
    waiting_front_pdf = State()
    waiting_preset = State()
    waiting_qty = State()


class AiDesignStates(StatesGroup):
    waiting_size = State()
    waiting_prompt = State()


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏷️ Sela Etiketka (1-qadam)", callback_data="menu:sela")],
        [InlineKeyboardButton(text="⚙️ Stiker Val Montaji (2-qadam)", callback_data="menu:label_imp")],
        [InlineKeyboardButton(text="📄 Varaq Montaji (Ofset/Raqamli)", callback_data="menu:print_imp")],
        [InlineKeyboardButton(text="✨ AI Dizayn (Claude + VectorCraft)", callback_data="menu:ai_design")],
    ]
    if PUBLIC_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🌐 Web Ilovani Ochish", web_app=WebAppInfo(url=PUBLIC_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")]]
    )


def cdr_result_kb(job_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🟢 CorelDRAW (.cdr v18 / X8) Paket",
                callback_data=f"cdr:{job_id}:18:0",
            )
        ],
        [
            InlineKeyboardButton(text="CDR v17 (X7)", callback_data=f"cdr:{job_id}:17:0"),
            InlineKeyboardButton(text="CDR v15 (X5)", callback_data=f"cdr:{job_id}:15:0"),
            InlineKeyboardButton(text="CDR (So'rash)", callback_data=f"cdr:{job_id}:18:1"),
        ],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Start & Home
# ---------------------------------------------------------------------------
@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 <b>PrintHub Poligrafiya Botiga xush kelibsiz!</b>\n\n"
        "Kerakli bo'limni tanlang:\n"
        "• <b>Sela Etiketka</b> — barkodli etiketka yaratish (so'ngra 1 tugma bilan Valga joylashtirish)\n"
        "• <b>Stiker Val Montaji</b> — istalgan PDF stikerni avtomatik valga terish\n"
        "• <b>Varaq Montaji</b> — ofset/raqamli varaq montaji va preflight",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "🏠 <b>Bosh menyu</b> — kerakli asbobni tanlang:",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# 1. SELA GENERATOR FLOW
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "menu:sela")
async def cb_sela_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    templates = sela_service.list_templates()
    if not templates:
        await call.message.edit_text(
            "⚠️ Serverda hali Sela shabloni (.pdf/.svg) yuklanmagan.\n"
            "Iltimos, avval Web sayt orqali Sela shablonini bir marta yuklab qo'ying.",
            reply_markup=cancel_kb(),
        )
        await call.answer()
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Qo'lda kiritish (1 ta etiketka)", callback_data="sela:manual")],
            [InlineKeyboardButton(text="📊 CSV fayl yuborish", callback_data="sela:csv")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
        ]
    )
    await state.set_state(SelaStates.waiting_mode)
    await call.message.edit_text(
        f"🏷️ <b>Sela Etiketka Generatori</b>\n"
        f"Faol shablon: <code>{templates[0]['name']}</code>\n\n"
        f"Ma'lumotni qanday kiritasiz?",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "sela:manual")
async def cb_sela_manual(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SelaStates.waiting_artikul)
    await call.message.edit_text(
        "1/5 — <b>Artikul</b>ni kiriting (masalan: <code>SI7804050205</code>):",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(SelaStates.waiting_artikul)
async def sela_got_artikul(message: Message, state: FSMContext) -> None:
    await state.update_data(artikul=message.text.strip())
    await state.set_state(SelaStates.waiting_colour)
    await message.answer("2/5 — <b>Rang (Colour)</b> kodini kiriting (masalan: <code>33</code>):", reply_markup=cancel_kb())


@router.message(SelaStates.waiting_colour)
async def sela_got_colour(message: Message, state: FSMContext) -> None:
    await state.update_data(colour=message.text.strip())
    await state.set_state(SelaStates.waiting_size)
    await message.answer("3/5 — <b>O'lcham (Size)</b>ni kiriting (masalan: <code>104/ 4-5 YEARS</code>):", reply_markup=cancel_kb())


@router.message(SelaStates.waiting_size)
async def sela_got_size(message: Message, state: FSMContext) -> None:
    await state.update_data(size=message.text.strip())
    await state.set_state(SelaStates.waiting_barcode)
    await message.answer("4/5 — <b>EAN-13 barkod</b>ni kiriting (12 yoki 13 raqam):", reply_markup=cancel_kb())


@router.message(SelaStates.waiting_barcode)
async def sela_got_barcode(message: Message, state: FSMContext) -> None:
    await state.update_data(barcode=message.text.strip())
    await state.set_state(SelaStates.waiting_qty)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="26 dona (1 ta A4)", callback_data="sela_qty:26"),
                InlineKeyboardButton(text="52 dona (2 ta A4)", callback_data="sela_qty:52"),
            ],
            [InlineKeyboardButton(text="🏠 Bekor qilish", callback_data="menu:home")],
        ]
    )
    await message.answer("5/5 — <b>Nechta dona</b> kerak? (Raqam yozing yoki tugmani bosing):", reply_markup=kb)


async def _finish_sela_manual(target_msg: Message, state: FSMContext, qty: int) -> None:
    data = await state.get_data()
    wait_msg = await target_msg.answer("⏳ A4 PDF yaratilmoqda...")
    try:
        res = await asyncio.to_thread(
            sela_service.generate_sela_job,
            items_payload=[
                {
                    "artikul": data["artikul"],
                    "colour": data["colour"],
                    "size": data["size"],
                    "barcode": data["barcode"],
                    "qty": qty,
                }
            ],
        )
        pdf_path = get_job_output_file(res["job_id"], res["output_file"])
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚙️ Keyingi qadam: Valga joylashtirish →",
                        callback_data=f"handoff:{res['job_id']}:{res['output_file']}",
                    )
                ],
                [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
            ]
        )
        await wait_msg.delete()
        await target_msg.answer_document(
            FSInputFile(str(pdf_path)),
            caption=(
                f"✅ <b>Sela A4 PDF tayyor!</b>\n"
                f"• Jami stiker: {res['total_labels']} dona\n"
                f"• Sahifalar: {res['page_count']} ta A4\n\n"
                f"👇 1 tugma bilan <b>Val Montaji</b>ga o'tkazishingiz mumkin:"
            ),
            reply_markup=kb,
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("sela_qty:"))
async def cb_sela_qty(call: CallbackQuery, state: FSMContext) -> None:
    qty = int(call.data.split(":")[1])
    await call.answer()
    await _finish_sela_manual(call.message, state, qty)


@router.message(SelaStates.waiting_qty)
async def sela_got_qty(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("Iltimos, musbat son kiriting (masalan: 26):")
        return
    await _finish_sela_manual(message, state, int(message.text.strip()))


@router.callback_query(F.data == "sela:csv")
async def cb_sela_csv(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SelaStates.waiting_csv)
    await call.message.edit_text(
        "📊 <b>CSV faylni yuboring</b>\n"
        "Ustunlar: <code>artikul,colour,size,barcode,qty</code>",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(SelaStates.waiting_csv, F.document)
async def sela_got_csv(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".csv"):
        await message.answer("Iltimos, .csv formatidagi fayl yuboring.")
        return
    wait_msg = await message.answer("⏳ CSV o'qilmoqda va A4 PDF yaratilmoqda...")
    try:
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        res = await asyncio.to_thread(
            sela_service.generate_sela_job,
            csv_bytes=buf.getvalue(),
            csv_filename=doc.file_name,
        )
        pdf_path = get_job_output_file(res["job_id"], res["output_file"])
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚙️ Keyingi qadam: Valga joylashtirish →",
                        callback_data=f"handoff:{res['job_id']}:{res['output_file']}",
                    )
                ],
                [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
            ]
        )
        await wait_msg.delete()
        await message.answer_document(
            FSInputFile(str(pdf_path)),
            caption=f"✅ <b>CSV asosida A4 PDF tayyor!</b>\nJami: {res['total_labels']} ta stiker ({res['page_count']} sahifa).",
            reply_markup=kb,
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


# ---------------------------------------------------------------------------
# SELA -> LABEL IMPOSITION HANDOFF
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("handoff:"))
async def cb_handoff_to_label_imp(call: CallbackQuery, state: FSMContext) -> None:
    _, job_id, filename = call.data.split(":", 2)
    await call.answer("Valga joylashtirish boshlandi...")
    wait_msg = await call.message.answer("⏳ Stikerlar ajratilib, avtomatik valga joylashtirilmoqda...")
    try:
        res = await asyncio.to_thread(
            label_imp_service.run_label_imposition_job,
            from_job_id=job_id,
            from_filename=filename,
            combine_same_gear=True,
        )
        await _send_label_imp_result(call.message, wait_msg, res)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


# ---------------------------------------------------------------------------
# 2. LABEL IMPOSITION FLOW
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "menu:label_imp")
async def cb_label_imp_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(LabelImpStates.waiting_pdf)
    await call.message.edit_text(
        "⚙️ <b>Stiker Val Montaji (Flexo / Gear)</b>\n\n"
        "📎 Istalgan stiker PDF faylini yuboring (bitta stiker, ko'p betli PDF yoki Sela A4 varag'i).",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(LabelImpStates.waiting_pdf, F.document)
async def label_imp_got_pdf(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".pdf"):
        await message.answer("Iltimos, faqat .pdf fayl yuboring.")
        return

    wait_msg = await message.answer("🔍 PDF tahlil qilinmoqda...")
    try:
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        raw = buf.getvalue()

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / (Path(doc.file_name).name)
            p.write_bytes(raw)
            info = await asyncio.to_thread(label_imp_service.inspect_pdf_file, p)

        # Save raw bytes to a temp job input so we don't keep large bytes in FSM memory
        tmp_job_id, tmp_dir = label_imp_service.create_job("tg_tmp")
        saved_name = Path(doc.file_name).name
        (tmp_dir / "outputs" / saved_name).write_bytes(raw)

        await state.update_data(src_job_id=tmp_job_id, src_filename=saved_name)
        await state.set_state(LabelImpStates.confirm_run)

        lines = [f"📄 <b>{doc.file_name}</b> — {info['design_count']} ta stiker aniqlandi:"]
        for d in info["designs"][:8]:
            lines.append(
                f"• {d['width_mm']}×{d['length_mm']} mm → <b>{d['recommended_gear']} val</b> ({d['recommended_copies']}x)"
            )
        if info["design_count"] > 8:
            lines.append(f"... va yana {info['design_count'] - 8} ta stiker")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Avtomatik joylashtirish", callback_data="limp:auto")],
                [InlineKeyboardButton(text="🔧 Val raqamini qo'lda kiritish", callback_data="limp:custom")],
                [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
            ]
        )
        await wait_msg.edit_text("\n".join(lines), reply_markup=kb)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


async def _send_label_imp_result(target_msg: Message, wait_msg: Message, res: Dict[str, Any]) -> None:
    lines = ["✅ <b>Val Montaji tayyor!</b>"]
    for d in res["designs"][:6]:
        lines.append(
            f"• {d['design_name']}: <b>{d['gear']} val</b> ({d['copies']}x) | "
            f"Film: {d['film_length_mm']} mm | Ranglar: {', '.join(d['colors'])}"
        )
    if len(res["designs"]) > 6:
        lines.append(f"... jami {len(res['designs'])} ta dizayn")

    await wait_msg.delete()
    kb = cdr_result_kb(res["job_id"])
    if res.get("zip_file"):
        zp = get_job_output_file(res["job_id"], res["zip_file"])
        await target_msg.answer_document(
            FSInputFile(str(zp)),
            caption="\n".join(lines),
            reply_markup=kb,
        )
    else:
        for f in res["output_files"]:
            fp = get_job_output_file(res["job_id"], f["filename"])
            await target_msg.answer_document(
                FSInputFile(str(fp)),
                caption="\n".join(lines),
                reply_markup=kb,
            )


@router.callback_query(LabelImpStates.confirm_run, F.data == "limp:auto")
async def cb_limp_auto(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await call.answer()
    wait_msg = await call.message.edit_text("⏳ Valga joylashtirilmoqda...")
    try:
        res = await asyncio.to_thread(
            label_imp_service.run_label_imposition_job,
            from_job_id=data["src_job_id"],
            from_filename=data["src_filename"],
            combine_same_gear=True,
        )
        await _send_label_imp_result(call.message, wait_msg, res)
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


@router.callback_query(LabelImpStates.confirm_run, F.data == "limp:custom")
async def cb_limp_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LabelImpStates.waiting_custom_gear)
    await call.message.edit_text(
        "🔧 Val raqamini kiriting (masalan: <code>59</code> yoki <code>59 2</code> — val va nusxa soni):",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(LabelImpStates.waiting_custom_gear)
async def limp_got_custom_gear(message: Message, state: FSMContext) -> None:
    parts = message.text.strip().split()
    if not parts or not parts[0].isdigit():
        await message.answer("Iltimos, val raqamini kiriting (masalan: 59):")
        return
    gear = int(parts[0])
    copies = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    data = await state.get_data()
    wait_msg = await message.answer(f"⏳ {gear}-valga joylashtirilmoqda...")
    try:
        res = await asyncio.to_thread(
            label_imp_service.run_label_imposition_job,
            from_job_id=data["src_job_id"],
            from_filename=data["src_filename"],
            custom_gear=gear,
            custom_copies=copies,
            combine_same_gear=True,
        )
        await _send_label_imp_result(message, wait_msg, res)
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


# ---------------------------------------------------------------------------
# 3. PRINT IMPOSITION (SHEET) FLOW
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "menu:print_imp")
async def cb_print_imp_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PrintImpStates.waiting_front_pdf)
    await call.message.edit_text(
        "📄 <b>Varaq Montaji (Ofset / Raqamli)</b>\n\n"
        "📎 Dizayn PDF faylini yuboring (avtomatik Preflight + o'lcham aniqlanadi).",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(PrintImpStates.waiting_front_pdf, F.document)
async def print_imp_got_pdf(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".pdf"):
        await message.answer("Iltimos, faqat .pdf fayl yuboring.")
        return

    wait_msg = await message.answer("🔍 Preflight tahlil qilinmoqda...")
    try:
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        raw = buf.getvalue()

        preflight = await asyncio.to_thread(
            print_imp_service.run_preflight_analysis,
            [(doc.file_name, raw)],
        )

        tmp_job_id, tmp_dir = print_imp_service.create_job("tg_ptmp")
        saved_name = Path(doc.file_name).name
        (tmp_dir / "outputs" / saved_name).write_bytes(raw)

        await state.update_data(src_job_id=tmp_job_id, src_filename=saved_name)
        await state.set_state(PrintImpStates.waiting_preset)

        rows = [
            [InlineKeyboardButton(text=p["name"], callback_data=f"ppreset:{k}")]
            for k, p in print_imp_service.PRESETS.items()
        ]
        rows.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")])

        colors_str = ", ".join(c["name"] for c in preflight["colors"]) or "-"
        await wait_msg.edit_text(
            f"🔍 <b>Preflight natijasi:</b>\n"
            f"• O'lcham: {preflight['trim_box_mm'][0]}×{preflight['trim_box_mm'][1]} mm\n"
            f"• Bleed: {preflight['detected_bleed_mm']} mm | Ranglar: {colors_str}\n"
            f"• Ogohlantirishlar: {preflight['warning_count']} | Xatolar: {preflight['error_count']}\n\n"
            f"Qog'oz shablonini tanlang:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


@router.callback_query(PrintImpStates.waiting_preset, F.data.startswith("ppreset:"))
async def cb_print_preset(call: CallbackQuery, state: FSMContext) -> None:
    preset_key = call.data.split(":")[1]
    await state.update_data(preset_key=preset_key)
    await state.set_state(PrintImpStates.waiting_qty)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 000 dona", callback_data="pqty:1000"),
                InlineKeyboardButton(text="5 000 dona", callback_data="pqty:5000"),
                InlineKeyboardButton(text="10 000 dona", callback_data="pqty:10000"),
            ],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
        ]
    )
    await call.message.edit_text("Buyurtma sonini (tirajni) tanlang yoki raqam yozing:", reply_markup=kb)
    await call.answer()


async def _finish_print_imp(target_msg: Message, state: FSMContext, qty: int) -> None:
    data = await state.get_data()
    preset = print_imp_service.PRESETS[data["preset_key"]]
    wait_msg = await target_msg.answer("⏳ Varaq montaji bajarilmoqda...")
    try:
        src_path = get_job_output_file(data["src_job_id"], data["src_filename"])
        raw = src_path.read_bytes()
        res = await asyncio.to_thread(
            print_imp_service.run_print_imposition_job,
            front_files=[(src_path.name, raw)],
            sheet_w_mm=preset["sheet_w"],
            sheet_h_mm=preset["sheet_h"],
            gripper_mm=preset["gripper"],
            inner_bleed_mm=preset["inner_bleed"],
            outer_bleed_mm=preset["outer_bleed"],
            gutter_mm=preset["gutter"],
            style=preset["style"],
            category=preset["category"],
            cut_style=preset["cut_style"],
            order_quantity=qty,
        )
        caption = (
            f"✅ <b>Varaq montaji tayyor!</b>\n"
            f"• Qolip: <b>{res['cols']}×{res['rows']} ({res['items_per_sheet']} dona/list)</b>\n"
            f"• Aylantirish: {res['rotation']}°\n"
            f"• Bosiladigan listlar: <b>{res['calculated_sheets']} list</b>"
        )
        await wait_msg.delete()
        target_file = res["zip_file"] or res["output_files"][0]["filename"]
        out_path = get_job_output_file(res["job_id"], target_file)
        await target_msg.answer_document(
            FSInputFile(str(out_path)),
            caption=caption,
            reply_markup=cdr_result_kb(res["job_id"]),
        )
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("cdr:"))
async def cb_send_cdr_bundle(call: CallbackQuery) -> None:
    try:
        _, job_id, ver_str, ask_str = call.data.split(":", 3)
        version = int(ver_str)
        ask_flag = ask_str == "1"
        await call.answer(f"CDR (v{version}) paket tayyorlanmoqda...")
        zip_bytes, zip_name = await asyncio.to_thread(
            build_cdr_bundle_zip,
            job_id=job_id,
            target_version=version,
            ask_version=ask_flag,
        )
        mode_note = f"versiyani so'raydi (standart: v{version})" if ask_flag else f"Version {version}"
        await call.message.answer_document(
            BufferedInputFile(zip_bytes, filename=zip_name),
            caption=(
                f"🟢 <b>CorelDRAW (.cdr) Avto-Konverter Paketi ({mode_note})</b>\n\n"
                f"1️⃣ ZIP arxivni kompyuterda papkaga chiqaring.\n"
                f"2️⃣ Ichidagi <code>1_Bosishda_CDR_v{version}_Qilish.vbs</code> faylini 2 marta bosing — "
                f"CorelDRAW avtomatik ochilib, <b>.cdr (v{version})</b> faylni saqlab beradi!"
            ),
            reply_markup=main_menu_kb(),
        )
    except Exception as e:
        await call.message.answer(f"❌ CDR paket yaratishda xatolik: {e}")


@router.callback_query(PrintImpStates.waiting_qty, F.data.startswith("pqty:"))
async def cb_print_qty(call: CallbackQuery, state: FSMContext) -> None:
    qty = int(call.data.split(":")[1])
    await call.answer()
    await _finish_print_imp(call.message, state, qty)


@router.message(PrintImpStates.waiting_qty)
async def print_got_qty(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("Iltimos, musbat son kiriting (masalan: 2000):")
        return
    await _finish_print_imp(message, state, int(message.text.strip()))


# ---------------------------------------------------------------------------
# 4. AI DESIGN (CLAUDE CODE + VECTORCRAFT MCP) FLOW
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "menu:ai_design")
@router.message(Command("ai"))
async def cb_ai_design_start(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    skills = claude_design_service.list_skills()
    assets = claude_design_service.list_assets()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="60×40 mm (Etiketka)", callback_data="ai_size:60:40"),
                InlineKeyboardButton(text="50×90 mm (Birka)", callback_data="ai_size:50:90"),
            ],
            [
                InlineKeyboardButton(text="80×50 mm (Stiker)", callback_data="ai_size:80:50"),
                InlineKeyboardButton(text="50×50 mm (Kvadrat)", callback_data="ai_size:50:50"),
            ],
            [InlineKeyboardButton(text="📐 Erkin o'lcham (Matnda yozaman)", callback_data="ai_size:0:0")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
        ]
    )
    text = (
        f"✨ <b>AI Dizayn Studio (Claude Code + VectorCraft MCP)</b>\n"
        f"• Faol skillar: <b>{len(skills)} ta</b>\n"
        f"• Serverdagi fayllar (Assets): <b>{len(assets)} ta</b>\n\n"
        f"1/2 — Dizayn o'lchamini tanlang (yoki <code>60x40</code> shaklida yozib yuboring):"
    )
    await state.set_state(AiDesignStates.waiting_size)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(AiDesignStates.waiting_size, F.data.startswith("ai_size:"))
async def cb_ai_got_size(call: CallbackQuery, state: FSMContext) -> None:
    _, w_str, h_str = call.data.split(":", 2)
    w_mm = float(w_str) if float(w_str) > 0 else None
    h_mm = float(h_str) if float(h_str) > 0 else None
    await state.update_data(width_mm=w_mm, height_mm=h_mm)
    await state.set_state(AiDesignStates.waiting_prompt)
    size_label = f"{w_mm:g}×{h_mm:g} mm" if (w_mm and h_mm) else "Erkin o'lcham"
    await call.message.edit_text(
        f"✨ Tanlangan o'lcham: <b>{size_label}</b>\n\n"
        f"2/2 — <b>Dizayn topshirig'ini (TZ) yozib yuboring</b>\n"
        f"(Xohlasangiz rasm, skrinshot yoki faylga izoh (caption) qilib yuborishingiz ham mumkin):",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(AiDesignStates.waiting_size)
async def msg_ai_got_custom_size(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").lower().replace("mm", "").replace("×", "x").replace("*", "x").strip()
    if "x" in raw:
        parts = raw.split("x", 1)
        try:
            w_mm = float(parts[0].strip())
            h_mm = float(parts[1].strip())
            await state.update_data(width_mm=w_mm, height_mm=h_mm)
            await state.set_state(AiDesignStates.waiting_prompt)
            await message.answer(
                f"✨ O'lcham: <b>{w_mm:g}×{h_mm:g} mm</b>\n\n"
                f"2/2 — <b>Dizayn topshirig'ini (TZ) yozib yuboring:</b>",
                reply_markup=cancel_kb(),
            )
            return
        except ValueError:
            pass
    # If the user directly typed a prompt instead of size, run directly!
    await state.update_data(width_mm=None, height_mm=None)
    await _run_bot_ai_design(message, state)


@router.message(AiDesignStates.waiting_prompt)
async def msg_ai_got_prompt(message: Message, state: FSMContext) -> None:
    await _run_bot_ai_design(message, state)


async def _run_bot_ai_design(message: Message, state: FSMContext) -> None:
    prompt_text = (message.text or message.caption or "").strip()
    if not prompt_text:
        await message.answer("Iltimos, dizayn topshirig'ini matn sifatida yozing:")
        return

    data = await state.get_data()
    w_mm = data.get("width_mm")
    h_mm = data.get("height_mm")

    uploaded_files: list[tuple[str, bytes]] = []
    if message.document:
        buf = io.BytesIO()
        await message.bot.download(message.document, destination=buf)
        uploaded_files.append((message.document.file_name or "input.bin", buf.getvalue()))
    elif message.photo:
        photo = message.photo[-1]
        buf = io.BytesIO()
        await message.bot.download(photo, destination=buf)
        uploaded_files.append((f"photo_{photo.file_unique_id}.jpg", buf.getvalue()))

    skills = [s["slug"] for s in claude_design_service.list_skills()]
    assets = [a["name"] for a in claude_design_service.list_assets()]

    wait_msg = await message.answer(
        "⏳ <b>Claude Code + VectorCraft MCP ishlamoqda...</b>\n"
        "Maxsus skillar asosida <code>.vectorcraft</code> va <code>.pdf</code> dizayn chizilmoqda (30-90 soniya olishi mumkin)."
    )

    try:
        res = await asyncio.to_thread(
            claude_design_service.run_ai_design_job,
            prompt=prompt_text,
            skill_slugs=skills,
            asset_names=assets,
            width_mm=w_mm,
            height_mm=h_mm,
            output_basename="ai_design",
            uploaded_files=uploaded_files,
        )
        await wait_msg.delete()

        job_id = res["job_id"]
        vc_file = res.get("vectorcraft_file")
        pdf_file = res.get("pdf_file")
        reply_summary = (res.get("assistant_reply") or "").strip()
        if len(reply_summary) > 650:
            reply_summary = reply_summary[:650] + "..."

        # 1. Send .vectorcraft file if present
        if vc_file:
            vc_path = get_job_output_file(job_id, vc_file)
            await message.answer_document(
                FSInputFile(str(vc_path)),
                caption=f"🎨 <b>VectorCraft standart fayli:</b> <code>{vc_file}</code>",
            )

        # 2. Send .pdf file with Val Montaji & CorelDRAW (.cdr) buttons
        if pdf_file:
            pdf_path = get_job_output_file(job_id, pdf_file)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⚙️ Val Montajiga joylashtirish →",
                            callback_data=f"handoff:{job_id}:{pdf_file}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🟢 CorelDRAW (.cdr v18 / X8) Paket",
                            callback_data=f"cdr:{job_id}:18:0",
                        )
                    ],
                    [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:home")],
                ]
            )
            await message.answer_document(
                FSInputFile(str(pdf_path)),
                caption=(
                    f"✅ <b>AI Dizayn PDF tayyor!</b> ({res.get('duration_sec', 0)} s)\n\n"
                    + (f"💬 <b>Claude hisoboti:</b>\n{reply_summary}" if reply_summary else "")
                ),
                reply_markup=kb,
            )
        else:
            await message.answer(
                f"ℹ️ <b>Claude javobi:</b>\n{reply_summary or 'Fayl yaratilmadi.'}",
                reply_markup=main_menu_kb(),
            )

        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}", reply_markup=cancel_kb())

