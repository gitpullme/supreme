"""Local-embedding adapter for E4 (copy-paste investigation detection).

Contract: similarity_matrix(texts, method, threshold) -> cosine similarity matrix.
  - "tfidf-cosine" (default): sklearn TF-IDF, zero dependencies beyond sklearn,
    fully offline. Tuned to the seeded suite (clean CLEAR, gamer flagged).
  - "minilm-cosine": all-MiniLM-L6-v2 via sentence-transformers, CPU-only,
    loaded EXCLUSIVELY from a vendored local directory (SATSA_MINILM_DIR or
    ./models/minilm) — never downloads at runtime, so the air-gap holds.
    Falls back to TF-IDF with a warning if the model dir is absent.

Validation gate: whichever method is configured must keep the seeded suite at
precision 1.0 / clean-CLEAR, or run.py refuses to bless it (see run.py).

2026-09 experiment (logged): minilm-cosine scored dup_rate 1.00 on the CLEAN
control at every threshold 0.90–0.97 — sentence embeddings normalise away the
case-specific details that TF-IDF's rare tokens catch, so every note looks
alike. REJECTED by the gate; TF-IDF stays default. MiniLM may return via a
different formulation (cluster + template extraction), not cosine threshold.
"""
from __future__ import annotations

import os

import numpy as np

MODEL_ENV = "SATSA_MINILM_DIR"
MODEL_DIRS = [os.environ.get(MODEL_ENV, ""),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "models", "minilm")]

_minilm = None
_minilm_ok = None


def minilm_available() -> bool:
    global _minilm_ok
    if _minilm_ok is not None:
        return _minilm_ok
    try:
        from sentence_transformers import SentenceTransformer  # noqa
        _minilm_ok = any(d and os.path.isdir(d) for d in MODEL_DIRS)
    except Exception:
        _minilm_ok = False
    return _minilm_ok


def _minilm_model():
    global _minilm
    if _minilm is None:
        from sentence_transformers import SentenceTransformer
        d = next(dd for dd in MODEL_DIRS if dd and os.path.isdir(dd))
        _minilm = SentenceTransformer(d, device="cpu")
    return _minilm


def similarity_matrix(texts: list[str], method: str = "tfidf-cosine",
                      threshold: float = 0.85) -> np.ndarray:
    if method == "minilm-cosine" and minilm_available():
        m = _minilm_model()
        X = m.encode(texts, normalize_embeddings=True,
                     show_progress_bar=False)
        return np.asarray(X @ X.T)
    if method == "minilm-cosine":
        print("  [embeddings] MiniLM dir absent -> TF-IDF fallback (air-gap safe)")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    X = TfidfVectorizer(stop_words="english", min_df=1).fit_transform(texts)
    return cosine_similarity(X)
