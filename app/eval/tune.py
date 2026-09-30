"""Tune cross-modal fusion calibration with a held-out split.

Candidates are computed once per golden query (models run once); fusion params are grid-searched
on the TUNE half (even rows per category) and reported on the HELD-OUT half (odd rows) to detect
overfitting. Usage: python -m eval.tune
"""
import itertools
import sys
import json
import os
from collections import defaultdict
from pathlib import Path

_seed = Path(__file__).resolve().parent.parent / "data" / "seeded_at.txt"
if _seed.exists():  # relative-date queries are evaluated against the corpus' seeding time
    os.environ.setdefault("QUERY_NOW", _seed.read_text().strip())
from backend.engine import Engine  # noqa: E402

HERE = Path(__file__).parent
GRID = {
    "t_temp": [0.5, 1.0, 1.5],
    "t_bias": [0.0],
    "i_temp": [0.5, 0.75, 1.0],
    "i_bias": [-1, 0, 1, 2, 3],
    "ocr_w": [0.6, 0.8, 1.0],
    "type_pen": [0.2, 0.35],
    "z_w": [0.0, 0.25, 0.5, 1.0],
    "vis_ocr_w": [0.3, 0.6, 1.0],
}


def metrics(e, cached, params):
    r1 = r10 = mrr = 0
    for row, (pq, tc, ic) in cached:
        got = [h.file_id for h in e.fuse(pq, tc, ic, params=params)[:10]]
        ranks = [got.index(x) + 1 for x in row["expected"] if x in got]
        b = min(ranks) if ranks else None
        r1 += b == 1
        r10 += b is not None
        mrr += 1 / b if b else 0
    n = len(cached)
    return {"mrr": mrr / n, "r1": r1 / n, "r10": r10 / n}


def main():
    e = Engine()
    rows = [json.loads(x) for x in (HERE / "golden.jsonl").read_text().splitlines() if x.strip()]
    seen = defaultdict(int)
    tune, held = [], []
    for r in rows:
        c = e.candidates("tenant_demo", r["query"])
        fold = seen[r["cat"]] % 2 == (1 if "--swap" in sys.argv else 0)
        (tune if fold else held).append((r, c))
        seen[r["cat"]] += 1
    keys = list(GRID)
    base = {k: v[0] for k, v in GRID.items()} | {"t_temp": 1.0, "i_temp": 1.0, "i_bias": 0, "ocr_w": 0.6, "type_pen": 0.2, "t_temp": 0.5, "i_temp": 0.5, "z_w": 0.0, "vis_ocr_w": 1.0}
    print("baseline  tune", metrics(e, tune, base), " held", metrics(e, held, base))
    best, best_p = None, None
    for combo in itertools.product(*GRID.values()):
        p = dict(zip(keys, combo))
        m = metrics(e, tune, p)
        score = (m["mrr"], m["r10"], m["r1"])
        if best is None or score > best:
            best, best_p = score, p
    print("best params", best_p)
    print("tuned     tune", metrics(e, tune, best_p), " held", metrics(e, held, best_p))
    print("tuned     ALL ", metrics(e, tune + held, best_p))
    if "--swap" not in sys.argv:
        (HERE / "tuned_params.json").write_text(json.dumps(best_p, indent=1))


if __name__ == "__main__":
    main()
