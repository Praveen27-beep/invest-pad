"""Turn an uploaded file into text, page by page, and cut it into passages.

Pure functions: bytes in, text out. No database, no web framework.
"""

import io
import re
import zipfile

MAX_PASSAGE = 1800   # characters; a passage is what gets searched, shown and cited
MIN_TEXT_PER_PDF = 40  # fewer characters than this in a whole PDF means "scanned, no text layer"


class Unreadable(Exception):
    """The file is not what its name says, or cannot be opened."""


def sniff(data: bytes) -> str | None:
    """What the file really is, judged by its content rather than its name."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
    return None


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n\s*", "\n\n", text).strip()


def extract(data: bytes, fmt: str) -> list[tuple[int, str, str]]:
    """Return [(number, label, text)] — one entry per page, sheet or section, text may be ''."""
    try:
        if fmt == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise Unreadable("This PDF is password-protected.")
            return [(n, f"p. {n}", _clean(page.extract_text() or "")) for n, page in enumerate(reader.pages, 1)]
        if fmt == "docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                parts += [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            return [(1, "", _clean("\n\n".join(p for p in parts if p.strip())))]
        if fmt == "xlsx":
            from openpyxl import load_workbook
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            sheets = []
            for n, sheet in enumerate(book.worksheets, 1):
                rows = []
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                    if cells:
                        rows.append(" | ".join(cells))
                sheets.append((n, sheet.title, _clean("\n".join(rows))))
            return sheets
    except Unreadable:
        raise
    except Exception as exc:  # noqa: BLE001 - any parser failure means the same thing to the user
        raise Unreadable(f"Could not read this file ({type(exc).__name__}).") from None
    raise Unreadable("Unsupported file type.")


def passages(text: str, limit: int = MAX_PASSAGE) -> list[str]:
    """Cut one page of text into passages no longer than `limit`.

    Breaks at paragraph ends where possible, then at line ends, then at sentence ends, and
    only as a last resort mid-sentence. Nothing is dropped or repeated.
    """
    out, current = [], ""
    for piece in _pieces(text, limit):
        if current and len(current) + len(piece) + 2 > limit:
            out.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        out.append(current)
    return out


def _pieces(text: str, limit: int):
    """Yield parts of `text` that each fit in `limit`, split at the gentlest break available."""
    for separator in ("\n\n", "\n", ". "):
        if len(text) <= limit:
            break
        parts = text.split(separator)
        if len(parts) > 1:
            for i, part in enumerate(parts):
                tail = separator.strip() if separator == ". " and i < len(parts) - 1 else ""
                yield from _pieces(part + tail, limit)
            return
    text = text.strip()
    while len(text) > limit:
        yield text[:limit]
        text = text[limit:]
    if text:
        yield text


PERIOD = re.compile(r"(?<![A-Za-z0-9])(?:(Q[1-4])[\s_-]*)?FY[\s_-]*'?(\d{2}|\d{4})(?:-\d{2})?(?![0-9])", re.IGNORECASE)
TYPES = [
    ("annual report", r"annual[\s_-]*report|\bAR[\s_-]*(FY)?\d{2}"),
    ("concall", r"con[\s_-]*call|transcript|earnings[\s_-]*call"),
    ("presentation", r"presentation|investor[\s_-]*(ppt|deck)|\bppt\b"),
    ("results", r"result|financials"),
    ("credit rating", r"rating|crisil|icra|\bcare\b"),
]


def guess_metadata(filename: str) -> dict:
    """Suggest a document type and period from the file name. The user confirms or corrects."""
    name = filename.rsplit(".", 1)[0]
    period = ""
    match = PERIOD.search(name)
    if match:
        year = match.group(2)[-2:]
        period = f"{match.group(1).upper()} FY{year}" if match.group(1) else f"FY{year}"
    doc_type = next((label for label, pattern in TYPES if re.search(pattern, name, re.IGNORECASE)), "other")
    return {"doc_type": doc_type, "period": period}
