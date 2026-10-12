"""جستجوی ترکیبی: معنایی (برداری) + کلیدواژه‌ای (BM25)، ادغام‌شده با Reciprocal Rank Fusion."""
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from core import db, llm
from core.text import tokenize

RRF_K = 60
CANDIDATES = 30


@dataclass
class Hit:
    chunk_id: int
    source_id: int
    source_name: str
    location: str
    content: str
    score: float


@dataclass
class _Index:
    signature: tuple
    chunks: list[dict]
    matrix: np.ndarray | None
    bm25: BM25Okapi | None


_cache: dict[tuple, _Index] = {}


def _get_index(org_id: int, assistant_id: int) -> _Index:
    key = (str(db.DB_PATH), org_id, assistant_id)
    sig = db.chunks_signature(org_id, assistant_id)
    idx = _cache.get(key)
    if idx and idx.signature == sig:
        return idx

    chunks = db.load_chunks(org_id, assistant_id)
    matrix = bm25 = None
    if chunks:
        # اگر مدل Embedding عوض شده باشد ابعاد بردارها فرق می‌کند؛ فقط ابعاد غالب نگه داشته می‌شود
        dims = [c["embedding"].shape[0] for c in chunks]
        main_dim = max(set(dims), key=dims.count)
        chunks = [c for c in chunks if c["embedding"].shape[0] == main_dim]
        matrix = np.vstack([c["embedding"] for c in chunks])
        bm25 = BM25Okapi([tokenize(c["content"]) or ["_"] for c in chunks])
    idx = _Index(sig, chunks, matrix, bm25)
    _cache[key] = idx
    return idx


def _rank(scores: np.ndarray, n: int) -> list[int]:
    order = np.argsort(-scores)[:n]
    return [int(i) for i in order]


def _memory_candidates(org_id: int, assistant_id: int, query: str) -> tuple[list[dict], list[dict]]:
    """SQLite: جستجوی معنایی و BM25 روی تکه‌های بارگذاری‌شده در حافظه."""
    idx = _get_index(org_id, assistant_id)
    if not idx.chunks:
        return [], []

    by_vector: list[dict] = []
    qvec = llm.embed([query])[0]
    if qvec.shape[0] == idx.matrix.shape[1]:
        by_vector = [idx.chunks[i] for i in _rank(idx.matrix @ qvec, CANDIDATES)]

    by_keyword: list[dict] = []
    q_tokens = tokenize(query)
    if q_tokens:
        bm = np.asarray(idx.bm25.get_scores(q_tokens))
        by_keyword = [idx.chunks[i] for i in _rank(bm, CANDIDATES) if bm[i] > 0]
    return by_vector, by_keyword


def _database_candidates(org_id: int, assistant_id: int, query: str) -> tuple[list[dict], list[dict]]:
    """Postgres: pgvector و جستجوی تمام‌متن، هر دو داخل دیتابیس."""
    qvec = llm.embed([query])[0]
    return (
        db.vector_search(org_id, assistant_id, qvec, CANDIDATES),
        db.keyword_search(org_id, assistant_id, tokenize(query), CANDIDATES),
    )


def search(org_id: int, assistant_id: int, query: str, k: int) -> list[Hit]:
    candidates = _database_candidates if db.is_postgres() else _memory_candidates
    by_vector, by_keyword = candidates(org_id, assistant_id, query)

    # Reciprocal Rank Fusion: هر فهرست بر اساس رتبه امتیاز می‌دهد، نه مقدار خام امتیاز
    fused: dict[int, float] = {}
    chunks: dict[int, dict] = {}
    for ranked in (by_vector, by_keyword):
        for rank, ch in enumerate(ranked):
            fused[ch["id"]] = fused.get(ch["id"], 0) + 1 / (RRF_K + rank)
            chunks[ch["id"]] = ch

    best = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    return [
        Hit(
            chunk_id=chunk_id,
            source_id=chunks[chunk_id]["source_id"],
            source_name=chunks[chunk_id]["source_name"],
            location=chunks[chunk_id]["location"],
            content=chunks[chunk_id]["content"],
            score=score,
        )
        for chunk_id, score in best
    ]
