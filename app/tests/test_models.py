"""Model loader / wrapper logic in backend.engine.Models, exercised with tiny fake model classes (no downloads)."""
import importlib
import sys
import types

import numpy as np
import pytest
import torch

from backend import config as C
from backend import engine as E


class _ST:
    def __init__(self, name, device=None, **kw):
        self.name, self.device = name, device

    def encode(self, texts, **kw):
        return np.ones((len(texts), 3), dtype=np.float32)


class _CE:
    def __init__(self, name, device=None, max_length=None):
        self.name = name

    def predict(self, pairs, **kw):
        return [0.25] * len(pairs)


class _BGE:
    def __init__(self, name, **kw):
        self.name = name

    def encode(self, texts, **kw):
        return {"dense_vecs": np.ones((len(texts), 3)), "lexical_weights": [{"7": 0.5, "3": 1.0} for _ in texts]}


class _FR:
    def __init__(self, name, **kw):
        self.name = name

    def compute_score(self, pairs, **kw):
        return 0.9 if len(pairs) == 1 else [0.9] * len(pairs)


class _Proc:
    def __call__(self, **kw):
        return types.SimpleNamespace(to=lambda dev: {})


class _Sig:
    device = "cpu"
    logit_scale = torch.tensor(0.0)  # exp -> 1.0
    logit_bias = torch.tensor(-1.0)

    def eval(self):
        return self

    def to(self, dev):
        return self

    def get_image_features(self, **kw):
        return torch.tensor([[3.0, 4.0]])  # tensor output (transformers<5)

    def get_text_features(self, **kw):
        return types.SimpleNamespace(pooler_output=torch.tensor([[0.0, 2.0]]))  # ModelOutput (transformers>=5)


class _Tok:
    def __init__(self, out):
        self.out = out

    def __call__(self, texts, **kw):
        return {}

    def decode(self, ids, **kw):
        return self.out


class _MT:
    calls = 0

    def eval(self):
        return self

    def generate(self, **kw):
        _MT.calls += 1
        return [[1]]


@pytest.fixture()
def fake_libs(monkeypatch):
    tok = _Tok("red shoes.")
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        types.SimpleNamespace(SentenceTransformer=_ST, CrossEncoder=_CE))
    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=_BGE, FlagReranker=_FR))
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(
        AutoModel=types.SimpleNamespace(from_pretrained=lambda n: _Sig()),
        AutoProcessor=types.SimpleNamespace(from_pretrained=lambda n: _Proc()),
        MarianTokenizer=types.SimpleNamespace(from_pretrained=lambda n: tok),
        MarianMTModel=types.SimpleNamespace(from_pretrained=lambda n: _MT()),
    ))
    return tok


def test_device_is_known():
    assert E._device() in ("mps", "cuda", "cpu")


def test_e5_backend_text_and_rerank(fake_libs, monkeypatch):
    monkeypatch.setattr(C, "TEXT_BACKEND", "e5")
    m = E.Models()
    dense, sparse = m.text(["sepatu merah"], is_query=True)
    assert dense == [[1.0, 1.0, 1.0]] and len(sparse) == 1
    _, sp_doc = m.text(["sepatu merah"])
    assert sp_doc[0].indices
    assert m.txt is m.txt  # cached after first load
    assert m.rerank("q", ["a", "b"]) == [0.25, 0.25]
    assert m.rerank("q", []) == []
    assert isinstance(m.reranker, _CE)


def test_bge_backend_text_and_rerank(fake_libs, monkeypatch):
    monkeypatch.setattr(C, "TEXT_BACKEND", "bge-m3")
    m = E.Models()
    dense, sparse = m.text(["a", "b"])
    assert len(dense) == 2 and sorted(sparse[0].indices) == [3, 7]
    assert m.rerank("q", ["a"]) == [0.9]      # scalar score -> wrapped into a list
    assert m.rerank("q", ["a", "b"]) == [0.9, 0.9]
    assert isinstance(m.txt, _BGE) and isinstance(m.reranker, _FR)


def test_siglip_embeddings_normalised_and_logit(fake_libs):
    m = E.Models()
    assert m.image(object()) == pytest.approx([0.6, 0.8])
    assert m.image_query("Foto Merah") == pytest.approx([0.0, 1.0])
    assert m.siglip_logit(0.5) == pytest.approx(-0.5)
    assert m.siglip_logit(1.0) == pytest.approx(0.0)  # scale/bias cached


def test_translate_caches_and_detects_unchanged(fake_libs):
    m = E.Models()
    _MT.calls = 0
    assert m.translate("sepatu merah") == "red shoes"
    assert m.translate("sepatu merah") == "red shoes" and _MT.calls == 1  # cache hit
    fake_libs.out = "Red Shoes"
    assert m.translate("red shoes") is None  # unchanged -> None
    m._tr_cache = {str(i): None for i in range(5001)}
    m.translate("baru")
    assert list(m._tr_cache) == ["baru"]  # cache is bounded


def test_config_bge_backend_dims(monkeypatch):
    monkeypatch.setenv("TEXT_BACKEND", "bge-m3")
    try:
        importlib.reload(C)
        assert C.TEXT_DIM == 1024
    finally:
        monkeypatch.delenv("TEXT_BACKEND")
        importlib.reload(C)
    assert C.TEXT_DIM == 384
