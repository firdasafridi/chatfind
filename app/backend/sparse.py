"""BM25-style sparse vectors for Qdrant (IDF applied server-side via Modifier.IDF).

Doc side: BM25 TF saturation. Query side: 1.0 per unique term. Tokens hashed to stable ids.
Light Indonesian normalisation so 'pengembaliannya' ~ 'pengembalian', 'barangnya' ~ 'barang'.
"""
import hashlib
import re
from collections import Counter

from qdrant_client import models

K1, B, AVG_LEN = 1.2, 0.75, 60.0
STOP = set("""
yang dan di ke dari untuk dengan pada ini itu atau juga dalam tidak akan ada sudah bisa oleh sebagai karena
saya aku kami kita anda kak mohon tolong cari carikan the a an of to in on for and or is are was be with by at
from this that it as
""".split())
SUFFIXES = ("nya", "lah", "kah")


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if t in STOP or len(t) < 2:
            continue
        for s in SUFFIXES:
            if len(t) > 5 and t.endswith(s):
                t = t[: -len(s)]
                break
        out.append(t)
    return out


def _id(tok: str) -> int:
    return int(hashlib.blake2b(tok.encode(), digest_size=4).hexdigest(), 16)


def doc_vector(text: str) -> models.SparseVector:
    toks = tokens(text)
    tf, n = Counter(toks), max(1, len(toks))
    w = {}
    for t, f in tf.items():
        w[_id(t)] = f * (K1 + 1) / (f + K1 * (1 - B + B * n / AVG_LEN))
    return models.SparseVector(indices=list(w), values=list(w.values())) if w else models.SparseVector(indices=[0], values=[0.0])


def query_vector(text: str) -> models.SparseVector:
    ids = sorted({_id(t) for t in tokens(text)})
    return models.SparseVector(indices=ids or [0], values=[1.0] * len(ids) if ids else [0.0])
