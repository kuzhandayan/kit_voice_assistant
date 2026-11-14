import io
import re

from pypdf import PdfReader

_RULE_START = re.compile(r"(?=(?<!\d)\d{1,2}\.\d{1,2}\.\d{1,2}\s+[A-Z])")
_FOOTER = re.compile(r"KIT Academic Regulations and Student Handbook \d{4} · Edition [\d.]+ · page \d+ of \d+")
_SPACES = re.compile(r"\s+")


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _SPACES.sub(" ", _FOOTER.sub(" ", text)).strip()


def chunk_text(text: str, *, window: int = 900, overlap: int = 150) -> list[str]:
    """Split by numbered rules (e.g. 6.1.4) when present, else by fixed windows."""
    parts = [p.strip() for p in _RULE_START.split(text) if p.strip()]
    if len(parts) > 5:
        return _merge_small(parts, min_chars=200, max_chars=window * 2)
    return _windows(text, window, overlap)


def _merge_small(parts: list[str], *, min_chars: int, max_chars: int) -> list[str]:
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_chars and len(merged[-1]) + len(part) < max_chars:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part[:max_chars])
    return merged


def _windows(text: str, window: int, overlap: int) -> list[str]:
    if len(text) <= window:
        return [text] if text else []
    step = window - overlap
    return [text[i : i + window] for i in range(0, len(text) - overlap, step)]
