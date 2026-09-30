"""Eval scripts (evaluate / tune / index_all / seed_docs / fetch_images) run against fakes and tmp_path only."""
import io
import json
import sys
import types
from pathlib import Path

import pytest

from backend import config as C
from eval import evaluate, index_all, seed_docs, tune


def _hit(fid):
    return types.SimpleNamespace(file_id=fid)


class FakeEngine:
    """search(): tenant_demo -> hits in a fixed order; tenant_other -> only its own file."""

    def __init__(self, order):
        self.order = order

    def search(self, tenant, query, k=10, use_parser=True):
        if tenant == "tenant_other":
            return None, [_hit("docs/Refund_Invoice_Other_Company.pdf")], None
        return None, [_hit(f) for f in self.order][:k], None

    def candidates(self, tenant, query):
        return (query, None, None)

    def fuse(self, pq, tc, ic, params=None):
        return [_hit(f) for f in self.order]


def _golden(tmp_path, rows):
    here = tmp_path / "eval"
    here.mkdir()
    (here / "golden.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    other = tmp_path / "data" / "tenant_other"
    other.mkdir(parents=True)
    (other / "manifest.json").write_text(json.dumps({"docs/Refund_Invoice_Other_Company.pdf": {}}))
    return here


ROWS = [{"cat": "a", "query": "q1", "expected": ["x"]}, {"cat": "b", "query": "q2", "expected": ["y"]},
        {"cat": "b", "query": "q3", "expected": ["zz"]}, {"cat": "a", "query": "q4", "expected": ["x"]}]


def test_evaluate_run_writes_report_and_gates(tmp_path, monkeypatch, capsys):
    here = _golden(tmp_path, ROWS)
    monkeypatch.setattr(evaluate, "HERE", here)
    ok = evaluate.run(FakeEngine(["x", "y"]), verbose=True)
    out = json.loads((here / "last_eval_golden.json").read_text())
    assert ok is False  # "zz" never retrieved -> category b recall@10 < 0.8
    assert out["leaks"] == 0 and out["checks"]["zero cross-tenant leaks"]
    assert out["metrics"]["ALL"]["recall@10"] == 0.75
    assert "MISS" in capsys.readouterr().out


def test_evaluate_run_passes_on_perfect_ranking(tmp_path, monkeypatch):
    rows = [{"cat": "a", "query": f"q{i}", "expected": ["x"]} for i in range(3)]
    monkeypatch.setattr(evaluate, "HERE", _golden(tmp_path, rows))
    assert evaluate.run(FakeEngine(["x"])) is True


def test_tune_main_writes_params(tmp_path, monkeypatch, capsys):
    here = _golden(tmp_path, ROWS)
    monkeypatch.setattr(tune, "HERE", here)
    monkeypatch.setattr(tune, "Engine", lambda: FakeEngine(["x", "y"]))
    monkeypatch.setattr(tune, "GRID", {k: v[:1] for k, v in tune.GRID.items()} | {"z_w": [0.0, 1.0]})
    monkeypatch.setattr(sys, "argv", ["tune"])
    tune.main()
    assert json.loads((here / "tuned_params.json").read_text())["z_w"] == 0.0
    monkeypatch.setattr(sys, "argv", ["tune", "--swap"])
    (here / "tuned_params.json").unlink()
    tune.main()
    assert not (here / "tuned_params.json").exists()  # --swap is report-only
    assert "best params" in capsys.readouterr().out


def test_index_all_ingests_manifest_and_dead_letters(tmp_path, monkeypatch, capsys):
    calls = []

    class Eng:
        def reset(self):
            calls.append("reset")

        def ingest(self, tenant, path, fid, channel, created_at):
            if fid == "bad.pdf":
                raise ValueError("corrupt")
            return {"status": "indexed" if fid == "ok.pdf" else "skipped"}

        def stats(self, tenant):
            return {}

    d = tmp_path / "data" / "t1"
    d.mkdir(parents=True)
    meta = {"channel": "whatsapp", "created_at": "2026-01-01T00:00:00+07:00"}
    (d / "manifest.json").write_text(json.dumps({"ok.pdf": meta, "bad.pdf": meta, "dup.pdf": meta}))
    monkeypatch.setattr(C, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(C, "TENANTS", {"t1": "T1"})
    monkeypatch.setattr(index_all, "Engine", Eng)
    monkeypatch.setattr(sys, "argv", ["index_all", "--reset"])
    index_all.main()
    out = capsys.readouterr().out
    assert calls == ["reset"] and "FAILED t1 bad.pdf ValueError" in out and "2 files" in out


def test_seed_docs_main_writes_corpus(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(seed_docs, "ROOT", tmp_path)
    (tmp_path / "tenant_demo" / "photos").mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(tmp_path / "tenant_demo" / "photos" / "p1.jpg")
    seed_docs.main()
    for tenant in seed_docs.DOCS:
        man = json.loads((tmp_path / tenant / "manifest.json").read_text())
        assert all((tmp_path / tenant / f).exists() for f in man)
    assert "photos/p1.jpg" in json.loads((tmp_path / "tenant_demo" / "manifest.json").read_text())
    assert (tmp_path / "seeded_at.txt").read_text() == seed_docs.NOW.isoformat()


def test_seed_docs_receipt_font_fallback(tmp_path, monkeypatch):
    real = seed_docs.ImageFont.truetype

    def boom(font, *a, **k):
        if "Menlo" in str(font):
            raise OSError
        return real(font, *a, **k)
    monkeypatch.setattr(seed_docs.ImageFont, "truetype", boom)
    seed_docs.write_receipt(tmp_path / "r.png", ["TOTAL 1"])
    assert (tmp_path / "r.png").exists()


def test_fetch_images_script_offline(tmp_path, monkeypatch, capsys):
    """Runs the real script source (same line layout, so coverage counts) with its paths rooted in tmp_path."""
    import urllib.request
    src = Path(__file__).resolve().parent.parent / "eval" / "fetch_images.py"
    (tmp_path / "eval").mkdir()
    fake_file = tmp_path / "eval" / "fetch_images.py"
    photos = tmp_path / "data" / "tenant_demo" / "photos"
    photos.mkdir(parents=True)
    (photos / "photo_0000.jpg").write_bytes(b"x")  # already present -> not re-downloaded
    got = []

    def urlopen(url, timeout=None):
        off = int(url.split("offset=")[1].split("&")[0])
        n = int(url.split("length=")[1])
        rows = [{"row_idx": off + i, "row": {"caption": f"c{off + i}", "image": {"src": f"http://x/{off + i}"}}}
                for i in range(n)]
        return io.StringIO(json.dumps({"rows": rows}))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(urllib.request, "urlretrieve", lambda src_, dst: got.append(Path(dst).name))
    monkeypatch.setattr(sys, "argv", ["fetch_images", "27"])
    code = compile(src.read_text().replace("Path(__file__)", "Path(_FAKE_FILE)"), str(src), "exec")
    exec(code, {"__file__": str(src), "_FAKE_FILE": str(fake_file), "__name__": "fetch_images"})
    caps = json.loads((tmp_path / "eval" / "captions.json").read_text())
    assert len(caps) == 27 and "photo_0000.jpg" not in got and len(got) == 26
    assert "27 images" in capsys.readouterr().out
    # default N and resume from existing captions.json
    monkeypatch.setattr(sys, "argv", ["fetch_images"])
    exec(code, {"__file__": str(src), "_FAKE_FILE": str(fake_file), "__name__": "fetch_images"})
    assert len(json.loads((tmp_path / "eval" / "captions.json").read_text())) == 120
