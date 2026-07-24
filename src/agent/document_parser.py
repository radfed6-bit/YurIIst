import logging
import os
import re
import tempfile
import uuid
from pathlib import Path

log = logging.getLogger("legal_bot.document_parser")

MAX_FILE_SIZE = 50 * 1024 * 1024

SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


def _parse_pdf(path: str) -> str:
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n\n".join(pages)


def _parse_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paras)


def _parse_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


_PARSERS = {
    "pdf": _parse_pdf,
    "docx": _parse_docx,
    "txt": _parse_txt,
}


def _detect_type(mime: str, filename: str) -> str | None:
    if mime in SUPPORTED_MIME:
        return SUPPORTED_MIME[mime]
    ext = Path(filename).suffix.lower().lstrip(".")
    return {"pdf": "pdf", "docx": "docx", "doc": "docx", "txt": "txt"}.get(ext)


async def download_and_parse(bot, file_id: str, filename: str, mime: str) -> dict:
    doc_type = _detect_type(mime, filename)
    if not doc_type:
        return {"error": f"Неподдерживаемый формат. Поддерживаются: PDF, DOCX, TXT."}

    parser = _PARSERS.get(doc_type)
    if not parser:
        return {"error": f"Формат {doc_type} не поддерживается."}

    tmp_dir = Path(tempfile.mkdtemp(prefix="legal_doc_"))
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    tmp_path = tmp_dir / safe_name
    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_size is None:
            return {"error": "Не удалось определить размер файла."}
        if tg_file.file_size > MAX_FILE_SIZE:
            return {"error": "Файл слишком большой (макс. 50 МБ)."}

        await tg_file.download_to_drive(tmp_path)

        text = parser(str(tmp_path))
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 20:
            return {"error": "Не удалось извлечь текст из файла. Возможно, это скан или защищённый документ."}

        log.info(f"Parsed {filename}: {len(text)} chars")
        return {"text": text, "name": filename, "chars": len(text)}
    except Exception as e:
        log.warning(f"Failed to parse {filename}: {e}")
        return {"error": f"Ошибка обработки файла: {e}"}
    finally:
        for f in tmp_dir.iterdir():
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()
