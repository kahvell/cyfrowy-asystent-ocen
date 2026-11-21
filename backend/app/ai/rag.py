"""RAG na przepisach: chunking po jednostkach redakcyjnych, wyszukiwanie hybrydowe.

- Gdy dostępny jest model embeddingów (np. bge-m3 w Ollamie): podobieństwo cosinusowe.
- W przeciwnym razie: wyszukiwanie leksykalne (prefiksy słów, ważone IDF) - działa offline i w CI.
Wektory trzymamy w kolumnie JSON (przenośne SQLite/Postgres); przy dużych zbiorach -> pgvector (ADR 0002).
"""

import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlmodel import Session, delete, select

from app.ai.provider import LLMError, get_provider
from app.models import DocChunk, LegalDoc

log = logging.getLogger(__name__)

_WORD = re.compile(r"[a-ząćęłńóśźż0-9]+", re.I)
_STOP = {"i", "w", "z", "na", "do", "o", "się", "nie", "jest", "czy", "lub", "oraz", "a", "że", "to", "po", "od",
         "jak", "co", "mam", "muszę", "przez", "dla", "który", "która", "które", "jeżeli", "albo", "ich", "jego"}


def _tokens(text: str) -> list[str]:
    return [w.lower()[:6] for w in _WORD.findall(text) if w.lower() not in _STOP and len(w) > 2]


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Dzieli dokument na fragmenty po nagłówkach '## ' (jedna jednostka redakcyjna = jeden fragment)."""
    chunks: list[tuple[str, str]] = []
    ref, buf = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if ref and buf:
                chunks.append((ref, "\n".join(buf).strip()))
            ref, buf = line[3:].strip(), []
        elif ref is not None:
            buf.append(line)
    if ref and buf:
        chunks.append((ref, "\n".join(buf).strip()))
    return [(r, t) for r, t in chunks if t]


def ingest_dir(session: Session, directory: Path) -> int:
    """Indeksuje przepisy z katalogu. Nowy plik -> dodany; zmieniona treść -> stary dokument usunięty
    i zaindeksowany ponownie; plik bez zmian -> pominięty. Aktualizacja przepisu = podmiana pliku .md."""
    # dokumenty z wersji bez wersjonowania (brak file_name) indeksujemy od nowa
    for old in session.exec(select(LegalDoc).where(LegalDoc.file_name.is_(None))).all():
        _drop_doc(session, old)
    count = 0
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = session.exec(select(LegalDoc).where(LegalDoc.file_name == path.name)).first()
        if existing and existing.content_hash == digest:
            continue
        if existing:
            log.info("Zmieniona treść %s - ponowne indeksowanie", path.name)
            _drop_doc(session, existing)
        title = text.splitlines()[0].lstrip("# ").strip()
        source = next((ln[len("Źródło:"):].strip() for ln in text.splitlines() if ln.startswith("Źródło:")), path.name)
        doc = LegalDoc(title=title, source=source, file_name=path.name, content_hash=digest)
        session.add(doc)
        session.flush()
        chunks = chunk_markdown(text)
        vectors: list[list[float]] | None = None
        provider = get_provider()
        if not provider.is_fake:
            try:
                vectors = provider.embed([f"{r}\n{t}" for r, t in chunks])
            except LLMError as exc:
                log.warning("Embeddingi niedostępne, RAG użyje wyszukiwania leksykalnego: %s", exc)
        for i, (ref, body) in enumerate(chunks):
            session.add(DocChunk(doc_id=doc.id, ref=ref, text=body, embedding=vectors[i] if vectors else None))
            count += 1
    session.commit()
    return count


def _drop_doc(session: Session, doc: LegalDoc) -> None:
    session.exec(delete(DocChunk).where(DocChunk.doc_id == doc.id))
    session.delete(doc)
    session.flush()


def backfill_embeddings(session: Session) -> int:
    """Uzupełnia brakujące wektory (np. baza powstała bez Ollamy, model doinstalowany później)."""
    provider = get_provider()
    if provider.is_fake:
        return 0
    missing = [c for c in session.exec(select(DocChunk)).all() if not c.embedding]
    if not missing:
        return 0
    try:
        vectors = provider.embed([f"{c.ref}\n{c.text}" for c in missing])
    except LLMError as exc:
        log.warning("Embeddingi niedostępne, RAG zostaje przy wyszukiwaniu leksykalnym: %s", exc)
        return 0
    for c, v in zip(missing, vectors, strict=True):
        c.embedding = v
        session.add(c)
    session.commit()
    log.info("Uzupełniono embeddingi dla %d fragmentów", len(missing))
    return len(missing)


@dataclass
class Hit:
    ref: str
    text: str
    source: str
    score: float


def _lexical(query: str, chunks: list[DocChunk]) -> list[float]:
    docs = [Counter(_tokens(f"{c.ref} {c.text}")) for c in chunks]
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    q = _tokens(query)
    scores = []
    for d in docs:
        length = sum(d.values()) or 1
        s = sum((d[t] / length) * math.log(1 + n / (1 + df[t])) for t in q if t in d)
        scores.append(s)
    return scores


def retrieve(session: Session, query: str, k: int = 5) -> list[Hit]:
    rows = session.exec(select(DocChunk, LegalDoc).join(LegalDoc, LegalDoc.id == DocChunk.doc_id)).all()
    if not rows:
        return []
    chunks = [c for c, _ in rows]
    scores: list[float] | None = None
    if all(c.embedding for c in chunks):
        try:
            qv = np.array(get_provider().embed([query])[0])
            m = np.array([c.embedding for c in chunks])
            sims = m @ qv / (np.linalg.norm(m, axis=1) * np.linalg.norm(qv) + 1e-9)
            lex = np.array(_lexical(query, chunks))
            if lex.max() > 0:
                lex = lex / lex.max()
            scores = list(0.8 * sims + 0.2 * lex)  # hybryda
        except LLMError:
            scores = None
    if scores is None:
        scores = _lexical(query, chunks)
    order = sorted(range(len(chunks)), key=lambda i: -scores[i])[:k]
    return [Hit(rows[i][0].ref, rows[i][0].text, rows[i][1].source, float(scores[i])) for i in order if scores[i] > 0]
