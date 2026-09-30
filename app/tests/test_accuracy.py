"""Accuracy gate with REAL models on the built index (slow). Run: pytest -m accuracy
Requires: python -m eval.index_all --reset (once)."""
import os

import pytest

from backend import config as C

pytestmark = pytest.mark.accuracy


@pytest.mark.skipif(not (C.STATE_DIR / "store.db").exists(), reason="index not built")
@pytest.mark.parametrize("golden", ["golden.jsonl", "golden_holdout.jsonl"])  # dev (tuned) + blind (never tuned on)
def test_accuracy_standard_met(golden):
    from backend.engine import Engine
    from eval.evaluate import run
    assert run(Engine(), verbose=True, golden=golden), f"accuracy standard not met on {golden}"
