import hashlib
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from qdrant_client import models as qm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _tok(s):
    return [t for t in re.findall(r"\w+", s.lower()) if len(t) > 1]


def _bow(tokens, dim):
    v = np.zeros(dim, dtype=np.float32)
    for t in tokens:
        v[int(hashlib.md5(t.encode()).hexdigest(), 16) % dim] += 1
    n = np.linalg.norm(v)
    return (v / n if n else v + 1e-3).tolist()


class FakeModels:
    """Deterministic stand-in for BGE-M3 / SigLIP / reranker: bag-of-words hashing.
    Lets us unit-test engine logic (filters, isolation, dedup, fusion) without downloading models."""

    def text(self, texts, is_query=False):
        from backend import config as C
        dense = [_bow(_tok(t), C.TEXT_DIM) for t in texts]
        sparse = []
        for t in texts:
            ids = sorted({int(hashlib.md5(w.encode()).hexdigest(), 16) % 250000 for w in _tok(t)}) or [0]
            sparse.append(qm.SparseVector(indices=ids, values=[1.0] * len(ids)))
        return dense, sparse

    def image(self, img):
        # images in tests are generated with a known colour name in their filename -> encoded via pixel colour
        r, g, b = img.resize((1, 1)).getpixel((0, 0))
        name = "red" if r > 150 and g < 100 else "blue" if b > 150 and r < 100 else "green"
        return _bow([name, "photo"], 768)

    def image_query(self, text):
        return _bow(_tok(text) + ["photo"], 768)

    def siglip_logit(self, cos):
        c = min(max(cos, 1e-6), 1 - 1e-6)
        return math.log(c / (1 - c))  # sigmoid(logit) == cos -> simple to reason about in tests

    def rerank(self, query, texts):
        q = set(_tok(query))
        return [len(q & set(_tok(t))) / max(1, len(q)) for t in texts]


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    from backend import config as C
    monkeypatch.setattr(C, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(C, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(C, "QDRANT_URL", None)
    from backend.engine import Engine
    e = Engine()
    e.m = FakeModels()
    yield e
    e.q.close()


@pytest.fixture()
def make_files(tmp_path):
    from PIL import Image
    from reportlab.pdfgen import canvas

    def _make(tenant, spec):
        root = tmp_path / "data" / tenant
        root.mkdir(parents=True, exist_ok=True)
        out = {}
        for name, content in spec.items():
            p = root / name
            if name.endswith(".png"):
                Image.new("RGB", (64, 64), content).save(p)
            elif name.endswith(".pdf"):
                c = canvas.Canvas(str(p))
                for i, line in enumerate(content.split("\n")):
                    c.drawString(50, 800 - 20 * i, line)
                c.save()
            else:
                p.write_text(content)
            out[name] = p
        return out

    return _make
