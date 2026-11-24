"""
CorelDRAW (.cdr) Auto-Converter Script & ZIP Bundle Generator.

Allows Linux-hosted PrintHub server to deliver vector PDF imposition outputs
together with a zero-install Windows VBScript / Batch automation launcher
that drives the user's local CorelDRAW via COM (CorelDRAW.Application) and
saves native .cdr files in the exact requested CorelDRAW version (default: 18 / X8).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.jobs import get_job_dir, get_job_output_file

DEFAULT_COREL_VERSION = 18

COREL_VERSIONS: List[Dict[str, Any]] = [
    {"version": 14, "name": "CorelDRAW X4 (v14)", "short": "v14 (X4)"},
    {"version": 15, "name": "CorelDRAW X5 (v15)", "short": "v15 (X5)"},
    {"version": 16, "name": "CorelDRAW X6 (v16)", "short": "v16 (X6)"},
    {"version": 17, "name": "CorelDRAW X7 (v17)", "short": "v17 (X7)"},
    {"version": 18, "name": "CorelDRAW X8 (v18) — Standart", "short": "v18 (X8)", "default": True},
    {"version": 19, "name": "CorelDRAW 2017 (v19)", "short": "v19 (2017)"},
    {"version": 20, "name": "CorelDRAW 2018 (v20)", "short": "v20 (2018)"},
    {"version": 21, "name": "CorelDRAW 2019 (v21)", "short": "v21 (2019)"},
    {"version": 22, "name": "CorelDRAW 2020 (v22)", "short": "v22 (2020)"},
    {"version": 23, "name": "CorelDRAW 2021 (v23)", "short": "v23 (2021)"},
    {"version": 24, "name": "CorelDRAW 2022/2023 (v24)", "short": "v24 (2022/23)"},
    {"version": 25, "name": "CorelDRAW 2024 (v25)", "short": "v25 (2024)"},
]

VALID_VERSION_NUMBERS = {item["version"] for item in COREL_VERSIONS}


def normalize_corel_version(version: Optional[int]) -> int:
    if version is None:
        return DEFAULT_COREL_VERSION
    try:
        v = int(version)
    except (TypeError, ValueError):
        return DEFAULT_COREL_VERSION
    if v in VALID_VERSION_NUMBERS:
        return v
    return max(12, min(26, v))


def get_version_label(version: int) -> str:
    for item in COREL_VERSIONS:
        if item["version"] == version:
            return item["short"]
    return f"v{version}"


def generate_cdr_converter_vbs(
    target_version: int = DEFAULT_COREL_VERSION,
    ask_version: bool = False,
    target_filenames: Optional[List[str]] = None,
    keep_open_in_corel: bool = True,
) -> str:
    """
    Generate a Windows VBScript (.vbs) that converts vector PDF file(s)
    in the current folder (or dragged-and-dropped onto the script) into
    native CorelDRAW (.cdr) files using the user's installed CorelDRAW.
    """
    ver = normalize_corel_version(target_version)
    ask_flag = "True" if ask_version else "False"
    keep_open_flag = "True" if keep_open_in_corel else "False"

    if target_filenames:
        escaped_files = ", ".join(f'"{Path(fn).name}"' for fn in target_filenames)
        explicit_array_code = f"explicitFiles = Array({escaped_files})"
    else:
        explicit_array_code = "explicitFiles = Array()"

    vbs_lines = [
        "' =============================================================================",
        "' PrintHub — Avtomatik PDF -> CorelDRAW (.cdr) Konverter",
        f"' Standart CorelDRAW fayl versiyasi: {ver} ({get_version_label(ver)})",
        "' Qo'shimcha dastur o'rnatish shart emas (Windows + CorelDRAW COM API)",
        "' =============================================================================",
        "Option Explicit",
        "",
        "Dim fso, shell, scriptDir, targetVersion, askVersion, keepOpen",
        "Dim explicitFiles, pdfList(), pdfCount, i, argPath, fileObj",
        "Dim app, doc, saveOpts, pdfPath, cdrPath, convertedCount, errMsg, actualVerUsed",
        "",
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        'Set shell = CreateObject("WScript.Shell")',
        "scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)",
        "",
        f"targetVersion = {ver}",
        f"askVersion = {ask_flag}",
        f"keepOpen = {keep_open_flag}",
        explicit_array_code,
        "",
        "' 1. Agar foydalanuvchi versiyani har safar so'rashni tanlagan bo'lsa",
        "If askVersion Then",
        "    Dim userAns",
        "    userAns = InputBox( _",
        '        "CorelDRAW (.cdr) fayl versiyasini kiriting:" & vbCrLf & vbCrLf & _',
        '        "  18 = CorelDRAW X8 (Tavsiya etiladi / Standart)" & vbCrLf & _',
        '        "  17 = CorelDRAW X7" & vbCrLf & _',
        '        "  16 = CorelDRAW X6" & vbCrLf & _',
        '        "  15 = CorelDRAW X5" & vbCrLf & _',
        '        "  19 = CorelDRAW 2017" & vbCrLf & _',
        '        "  20 = CorelDRAW 2018" & vbCrLf & _',
        '        "  21 = CorelDRAW 2019" & vbCrLf & _',
        '        "  22 = CorelDRAW 2020" & vbCrLf & _',
        '        "  23 = CorelDRAW 2021" & vbCrLf & _',
        '        "  24 = CorelDRAW 2022/2023", _',
        '        "PrintHub — CorelDRAW (.cdr) Versiyasini Tanlash", _',
        "        CStr(targetVersion))",
        '    If Trim(userAns) = "" Then',
        "        WScript.Quit 0",
        "    End If",
        "    If IsNumeric(Trim(userAns)) Then",
        "        targetVersion = CInt(Trim(userAns))",
        "    End If",
        "End If",
        "",
        "' 2. Konvertatsiya qilinadigan PDF fayllar ro'yxatini yig'ish",
        "pdfCount = 0",
        "ReDim pdfList(0)",
        "",
        "' A) Agar skript ustiga PDF fayl(lar) sichqoncha bilan tashlangan bo'lsa (Drag & Drop)",
        "If WScript.Arguments.Count > 0 Then",
        "    For i = 0 To WScript.Arguments.Count - 1",
        "        argPath = WScript.Arguments(i)",
        "        If fso.FileExists(argPath) Then",
        '            If LCase(fso.GetExtensionName(argPath)) = "pdf" Then',
        "                ReDim Preserve pdfList(pdfCount)",
        "                pdfList(pdfCount) = argPath",
        "                pdfCount = pdfCount + 1",
        "            End If",
        "        End If",
        "    Next",
        "End If",
        "",
        "' B) Agar aniq montaj fayllari biriktirilgan bo'lsa",
        "If pdfCount = 0 And UBound(explicitFiles) >= 0 Then",
        "    For i = 0 To UBound(explicitFiles)",
        '        argPath = fso.BuildPath(scriptDir, explicitFiles(i))',
        "        If fso.FileExists(argPath) Then",
        "            ReDim Preserve pdfList(pdfCount)",
        "            pdfList(pdfCount) = argPath",
        "            pdfCount = pdfCount + 1",
        "        End If",
        "    Next",
        "End If",
        "",
        "' C) Aks holda shu papkadagi barcha PDF fayllarni olish",
        "If pdfCount = 0 Then",
        "    For Each fileObj In fso.GetFolder(scriptDir).Files",
        '        If LCase(fso.GetExtensionName(fileObj.Name)) = "pdf" Then',
        "            ReDim Preserve pdfList(pdfCount)",
        "            pdfList(pdfCount) = fileObj.Path",
        "            pdfCount = pdfCount + 1",
        "        End If",
        "    Next",
        "End If",
        "",
        "If pdfCount = 0 Then",
        '    MsgBox "Ushbu papkada konvertatsiya qilish uchun PDF montaj fayli topilmadi!" & vbCrLf & vbCrLf & _',
        '           "Maslahat: Skriptni PDF fayl bilan bitta papkada ishga tushiring yoki PDF faylni ushbu skript ustiga tashlang.", _',
        '           vbExclamation, "PrintHub — PDF topilmadi"',
        "    WScript.Quit 1",
        "End If",
        "",
        "' 3. Foydalanuvchi kompyuteridagi CorelDRAW dasturiga ulanish",
        "On Error Resume Next",
        'Set app = CreateObject("CorelDRAW.Application")',
        "If Err.Number <> 0 Or (app Is Nothing) Then",
        "    Err.Clear",
        "    ' Ba'zi versiyalarda aniq versiya ProgID orqali chaqirilishi mumkin",
        "    Dim tryVer",
        "    For tryVer = 26 To 14 Step -1",
        '        Set app = CreateObject("CorelDRAW.Application." & CStr(tryVer))',
        "        If Err.Number = 0 And Not (app Is Nothing) Then Exit For",
        "        Err.Clear",
        "    Next",
        "End If",
        "",
        "If app Is Nothing Then",
        '    MsgBox "Kompyuteringizda CorelDRAW dasturi topilmadi yoki COM Automation yoqilmagan!" & vbCrLf & _',
        '           "Iltimos, CorelDRAW o\'rnatilganligini tekshiring.", _',
        '           vbCritical, "PrintHub — CorelDRAW Xatosi"',
        "    WScript.Quit 1",
        "End If",
        "",
        "app.Visible = True",
        "convertedCount = 0",
        "actualVerUsed = targetVersion",
        "",
        "' 4. Har bir PDF montajni CorelDRAW da ochib, tanlangan versiyada (.cdr) saqlash",
        "For i = 0 To pdfCount - 1",
        "    pdfPath = pdfList(i)",
        '    cdrPath = fso.BuildPath(fso.GetParentFolderName(pdfPath), fso.GetBaseName(pdfPath) & ".cdr")',
        "",
        "    Err.Clear",
        "    Set doc = app.OpenDocument(pdfPath)",
        "    If Err.Number <> 0 Or (doc Is Nothing) Then",
        "        errMsg = Err.Description",
        "        Err.Clear",
        '        MsgBox "PDF faylni CorelDRAW da ochishda xatolik:" & vbCrLf & pdfPath & vbCrLf & errMsg, vbExclamation, "PrintHub"',
        "    Else",
        "        ' O'lchov birligini Millimetrga (cdrMillimeter = 4) o'rnatish",
        "        doc.Unit = 4",
        "",
        "        Set saveOpts = app.CreateStructSaveAsOptions()",
        "        If Not (saveOpts Is Nothing) Then",
        "            saveOpts.EmbedICCProfile = True",
        "            saveOpts.EmbedVBAProject = False",
        "            saveOpts.Filter = 1799 ' cdrCDR",
        "            saveOpts.IncludeCMXData = False",
        "            saveOpts.Range = 0 ' cdrAllPages",
        "            saveOpts.Overwrite = True",
        "            saveOpts.Version = targetVersion",
        "",
        "            Err.Clear",
        "            doc.SaveAs cdrPath, saveOpts",
        "            If Err.Number <> 0 Then",
        "                ' Agar foydalanuvchidagi CorelDRAW versiyasi so'ralgan versiyadan eskiroq bo'lsa (masalan X7 da v18 so'ralsa)",
        "                Err.Clear",
        "                Dim hostVer",
        "                hostVer = CInt(app.VersionMajor)",
        "                If hostVer > 0 And hostVer < targetVersion Then",
        "                    saveOpts.Version = hostVer",
        "                    actualVerUsed = hostVer",
        "                    doc.SaveAs cdrPath, saveOpts",
        "                End If",
        "                If Err.Number <> 0 Then",
        "                    Err.Clear",
        "                    doc.SaveAs cdrPath",
        "                End If",
        "            End If",
        "        Else",
        "            doc.SaveAs cdrPath",
        "        End If",
        "",
        "        If Err.Number = 0 Then",
        "            convertedCount = convertedCount + 1",
        "            If Not keepOpen Then",
        "                doc.Close",
        "            End If",
        "        Else",
        "            errMsg = Err.Description",
        "            Err.Clear",
        '            MsgBox "CDR saqlashda xatolik: " & cdrPath & vbCrLf & errMsg, vbExclamation, "PrintHub"',
        "        End If",
        "    End If",
        "Next",
        "",
        "If convertedCount > 0 Then",
        '    shell.Popup "✅ Muvaffaqiyatli! " & CStr(convertedCount) & " ta montaj fayli CorelDRAW (.cdr, Version " & CStr(actualVerUsed) & ") formatida saqlandi!", 4, "PrintHub — CDR Tayyor", 64',
        "End If",
        "",
    ]
    return "\r\n".join(vbs_lines)


def generate_cdr_converter_bat(vbs_filename: str, target_version: int = DEFAULT_COREL_VERSION) -> str:
    """Generate a Windows .bat launcher that invokes wscript on the .vbs script."""
    ver = normalize_corel_version(target_version)
    bat_lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"echo PrintHub: CorelDRAW (.cdr v{ver}) avto-konverter ishga tushirilmoqda...",
        f'start "" wscript.exe "%~dp0{vbs_filename}" %*',
        "",
    ]
    return "\r\n".join(bat_lines)


def generate_readme_txt(target_version: int = DEFAULT_COREL_VERSION, ask_version: bool = False) -> str:
    ver = normalize_corel_version(target_version)
    mode_desc = (
        f"Ishga tushganda CorelDRAW versiyasini so'raydi (Standart: {ver} / {get_version_label(ver)})"
        if ask_version
        else f"Avtomatik CorelDRAW Version {ver} ({get_version_label(ver)}) formatida saqlaydi"
    )
    lines = [
        "==================================================================",
        "   PRINTHUB — 1 BOSISHDA CORELDRAW (.CDR) AVTO-KONVERTER",
        "==================================================================",
        "",
        f"Sozlangan rejim: {mode_desc}",
        "",
        "QANDAY ISHLATILADI:",
        "1. Ushbu ZIP arxivni istalgan papkaga chiqaring (Extract / Распаковать).",
        f'2. Papka ichidagi "1_Bosishda_CDR_v{ver}_Qilish.vbs" (yoki .bat) faylini 2 marta bosing.',
        "3. Skript kompyuteringizdagi CorelDRAW dasturini avtomatik ochib,",
        f"   montaj PDF fayl(lar)ini 100% vektor holatda .CDR (Version {ver})",
        "   formatiga o'giradi va aynan shu papkaga saqlab beradi!",
        "",
        "MASLAHAT:",
        "- Ushbu .vbs skriptni Ish stoliga (Desktop) saqlab qo'ysangiz, istalgan",
        "  PDF faylni sichqoncha bilan uning ustiga tashlab (Drag & Drop)",
        "  darhol .CDR (v18) faylga aylantirishingiz mumkin.",
        "==================================================================",
        "",
    ]
    return "\r\n".join(lines)


def build_cdr_bundle_zip(
    job_id: str,
    filename: Optional[str] = None,
    target_version: int = DEFAULT_COREL_VERSION,
    ask_version: bool = False,
    keep_open_in_corel: bool = True,
) -> tuple[bytes, str]:
    """
    Create an in-memory ZIP archive containing:
    - The job's output PDF file(s)
    - 1_Bosishda_CDR_v{ver}_Qilish.vbs
    - 1_Bosishda_CDR_v{ver}_Qilish.bat
    - QOLLANMA_CDR.txt
    Returns (zip_bytes, suggested_zip_filename).
    """
    ver = normalize_corel_version(target_version)
    job_dir = get_job_dir(job_id)
    out_dir = job_dir / "outputs"

    pdf_files: List[Path] = []
    if filename:
        target_path = get_job_output_file(job_id, filename)
        pdf_files.append(target_path)
    else:
        pdf_files = [
            p
            for p in sorted(out_dir.iterdir())
            if p.is_file() and p.suffix.lower() == ".pdf"
        ]

    if not pdf_files:
        raise FileNotFoundError("Ushbu buyurtmada PDF montaj fayllari topilmadi.")

    suffix_tag = f"v{ver}_sorash" if ask_version else f"v{ver}"
    vbs_name = f"1_Bosishda_CDR_{suffix_tag}_Qilish.vbs"
    bat_name = f"1_Bosishda_CDR_{suffix_tag}_Qilish.bat"

    vbs_content = generate_cdr_converter_vbs(
        target_version=ver,
        ask_version=ask_version,
        target_filenames=[p.name for p in pdf_files],
        keep_open_in_corel=keep_open_in_corel,
    )
    bat_content = generate_cdr_converter_bat(vbs_name, target_version=ver)
    readme_content = generate_readme_txt(target_version=ver, ask_version=ask_version)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in pdf_files:
            zf.write(p, arcname=p.name)
        # UTF-8 without BOM works for .bat, while Windows VBScript handles ASCII/ANSI cleanly
        zf.writestr(vbs_name, vbs_content.encode("utf-8"))
        zf.writestr(bat_name, bat_content.encode("utf-8"))
        zf.writestr("QOLLANMA_CDR.txt", readme_content.encode("utf-8"))

    base_stem = pdf_files[0].stem if len(pdf_files) == 1 else job_id
    zip_filename = f"{base_stem}_CDR_v{ver}_Paket.zip"
    return buf.getvalue(), zip_filename


def build_standalone_converter_zip(
    target_version: int = DEFAULT_COREL_VERSION,
    ask_version: bool = False,
) -> tuple[bytes, str]:
    """
    Create a standalone universal Drag-and-Drop / Folder PDF -> CDR converter ZIP
    that the user can keep on their Desktop.
    """
    ver = normalize_corel_version(target_version)
    suffix_tag = f"v{ver}_sorash" if ask_version else f"v{ver}"
    vbs_name = f"PrintHub_Universal_PDF_to_CDR_{suffix_tag}.vbs"
    bat_name = f"PrintHub_Universal_PDF_to_CDR_{suffix_tag}.bat"

    vbs_content = generate_cdr_converter_vbs(
        target_version=ver,
        ask_version=ask_version,
        target_filenames=None,
        keep_open_in_corel=True,
    )
    bat_content = generate_cdr_converter_bat(vbs_name, target_version=ver)
    readme_content = generate_readme_txt(target_version=ver, ask_version=ask_version)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(vbs_name, vbs_content.encode("utf-8"))
        zf.writestr(bat_name, bat_content.encode("utf-8"))
        zf.writestr("QOLLANMA_CDR.txt", readme_content.encode("utf-8"))

    zip_filename = f"PrintHub_Universal_CDR_v{ver}_Konverter.zip"
    return buf.getvalue(), zip_filename
