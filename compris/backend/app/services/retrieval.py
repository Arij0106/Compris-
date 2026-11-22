"""RAG léger : index TF-IDF par cours (sans téléchargement de modèle, fonctionne en FR/EN/AR).

Pour passer à des embeddings (sentence-transformers + Chroma), remplacez uniquement `_build` et `search`.
"""
import threading

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, Chunk
from app.services.text import STOPWORDS

_CACHE: dict[int, dict | None] = {}
_LOCK = threading.Lock()


def invalidate(course_id: int) -> None:
    with _LOCK:
        _CACHE.pop(course_id, None)


def _build(db: Session, course_id: int) -> dict | None:
    rows = db.execute(
        select(Chunk.id, Chunk.text, Chunk.page, Chunk.chapter_id).where(Chunk.course_id == course_id)
    ).all()
    if not rows:
        return None
    chapters = {c.id: c.title for c in db.scalars(select(Chapter).where(Chapter.course_id == course_id))}
    vec = TfidfVectorizer(
        stop_words=sorted(STOPWORDS), ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode", lowercase=True
    )
    try:
        X = vec.fit_transform([r.text for r in rows])
    except ValueError:
        return None
    meta = [
        {"chunk_id": r.id, "text": r.text, "page": r.page, "chapter": chapters.get(r.chapter_id, "")} for r in rows
    ]
    return {"vec": vec, "X": X, "meta": meta}


def search(db: Session, course_id: int, query: str, k: int = 4) -> list[dict]:
    with _LOCK:
        if course_id not in _CACHE:
            _CACHE[course_id] = _build(db, course_id)
        idx = _CACHE[course_id]
    if idx is None or not query.strip():
        return []
    try:
        q = idx["vec"].transform([query])
        scores = linear_kernel(q, idx["X"]).ravel()
        order = scores.argsort()[::-1][:k]
        return [dict(idx["meta"][i], score=float(scores[i])) for i in order if scores[i] > 0]
    except Exception:
        return []
