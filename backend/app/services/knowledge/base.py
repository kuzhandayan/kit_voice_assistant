import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rank_bm25 import BM25Okapi

from app.core.errors import CollegeAPIError
from app.services.college.client import CollegeClient
from app.services.college.clock import CollegeClock
from app.services.knowledge.chunking import chunk_text, pdf_to_text

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "is",
        "are",
        "be",
        "can",
        "i",
        "my",
        "me",
        "what",
        "how",
        "do",
        "does",
        "with",
        "at",
        "by",
        "from",
        "as",
        "it",
        "this",
        "that",
    ]
)
SINGLE_VERSION_TYPES = frozenset({"handbook", "brochure"})


_US_SPELLING = re.compile(r"iz(?=[aei])")


def _normalise(token: str) -> str:
    token = _US_SPELLING.sub("is", token)
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_normalise(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class DocumentMeta:
    id: int
    title: str
    type: str
    version: str
    effective_date: date
    applies_to: dict[str, Any]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "DocumentMeta":
        return cls(
            id=int(raw["id"]),
            title=raw.get("title", f"Document {raw['id']}"),
            type=str(raw.get("type", "other")),
            version=str(raw.get("version", "")),
            effective_date=date.fromisoformat(raw["effective_date"]),
            applies_to=raw.get("applies_to") or {},
        )


@dataclass(frozen=True)
class Chunk:
    doc: DocumentMeta
    text: str


@dataclass(frozen=True)
class Audience:
    programme: str | None = None
    department: str | None = None
    year: int | None = None

    def can_see(self, doc: DocumentMeta) -> bool:
        rules = doc.applies_to
        if self.programme and rules.get("programmes") and self.programme not in rules["programmes"]:
            return False
        if self.department and rules.get("departments") and self.department not in rules["departments"]:
            return False
        return not (self.year and rules.get("years") and self.year not in rules["years"])


@dataclass
class _Index:
    chunks: list[Chunk] = field(default_factory=list)
    bm25: BM25Okapi | None = None


def select_active(docs: list[DocumentMeta], today: date) -> list[DocumentMeta]:
    """Newest effective version for single-version types; every effective doc for the rest."""
    effective = [d for d in docs if d.effective_date <= today]
    latest: dict[str, DocumentMeta] = {}
    others: list[DocumentMeta] = []
    for doc in effective:
        if doc.type in SINGLE_VERSION_TYPES:
            current = latest.get(doc.type)
            if current is None or doc.effective_date > current.effective_date:
                latest[doc.type] = doc
        else:
            others.append(doc)
    return [*latest.values(), *others]


class KnowledgeBase:
    """Loads college documents from the API, keeps them fresh, and searches them with BM25."""

    def __init__(self, client: CollegeClient, clock: CollegeClock, refresh_seconds: int = 300):
        self._client = client
        self._clock = clock
        self._refresh_seconds = refresh_seconds
        self._texts: dict[tuple[int, str], str] = {}
        self._index = _Index()
        self._docs: list[DocumentMeta] = []
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def documents(self) -> list[DocumentMeta]:
        return list(self._docs)

    async def refresh(self, *, force: bool = False) -> None:
        if not force and self._index.bm25 and time.monotonic() - self._loaded_at < self._refresh_seconds:
            return
        async with self._lock:
            if not force and self._index.bm25 and time.monotonic() - self._loaded_at < self._refresh_seconds:
                return
            try:
                await self._reload()
            except CollegeAPIError as exc:
                logger.warning("Document refresh failed, keeping previous index: %s", exc)
            self._loaded_at = time.monotonic()

    async def _reload(self) -> None:
        listed = [DocumentMeta.from_api(d) for d in await self._client.documents()]
        active = select_active(listed, await self._clock.today())
        chunks: list[Chunk] = []
        for doc in active:
            text = await self._text_for(doc)
            chunks.extend(Chunk(doc, f"[{doc.title}] {part}") for part in chunk_text(text))
        if chunks:
            self._index = _Index(chunks, BM25Okapi([tokenize(c.text) for c in chunks]))
            self._docs = active
            logger.info("Knowledge index built: %d documents, %d chunks", len(active), len(chunks))

    async def _text_for(self, doc: DocumentMeta) -> str:
        key = (doc.id, doc.version)
        if key not in self._texts:
            data = await self._client.document_file(doc.id)
            self._texts[key] = await asyncio.to_thread(pdf_to_text, data)
        return self._texts[key]

    async def search(self, query: str, *, doc_types: set[str], audience: Audience, limit: int = 4) -> list[Chunk]:
        await self.refresh()
        index = self._index
        if not index.bm25 or not query.strip():
            return []
        scores = index.bm25.get_scores(tokenize(query))
        ranked: list[tuple[float, Chunk]] = []
        for score, chunk in zip(scores, index.chunks, strict=True):
            if score <= 0 or chunk.doc.type not in doc_types or not audience.can_see(chunk.doc):
                continue
            boost = 1.25 if chunk.doc.type == "circular" else 1.0
            ranked.append((score * boost, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in ranked[:limit]]
