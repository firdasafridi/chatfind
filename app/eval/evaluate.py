"""Accuracy + isolation gate. Usage: python -m eval.evaluate [--verbose] [--no-parser]

Standard (must all pass, see eval/STANDARD.md):
  overall Recall@10 >= 0.90, MRR@10 >= 0.75, Recall@1 >= 0.65, every category Recall@10 >= 0.80,
  0 cross-tenant leaks.
"""
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

_seed = Path(__file__).resolve().parent.parent / "data" / "seeded_at.txt"
if _seed.exists():  # relative-date queries are evaluated against the corpus' seeding time
    os.environ.setdefault("QUERY_NOW", _seed.read_text().strip())
from backend.engine import Engine  # noqa: E402

GATE = {"recall@10": 0.90, "mrr@10": 0.75, "recall@1": 0.65, "cat_recall@10": 0.80}
HERE = Path(__file__).parent


def run(e, verbose=False, use_parser=True, golden="golden.jsonl"):
    rows = [json.loads(line) for line in (HERE / golden).read_text().splitlines() if line.strip()]
    per = defaultdict(lambda: {"n": 0, "r1": 0, "r10": 0, "mrr": 0.0})
    misses, lat = [], []
    for r in rows:
        t0 = time.perf_counter()
        _, hits, _ = e.search("tenant_demo", r["query"], k=10, use_parser=use_parser)
        lat.append(time.perf_counter() - t0)
        got = [h.file_id for h in hits]
        ranks = [got.index(x) + 1 for x in r["expected"] if x in got]
        best = min(ranks) if ranks else None
        for key in (r["cat"], "ALL"):
            p = per[key]
            p["n"] += 1
            p["r1"] += best == 1
            p["r10"] += best is not None
            p["mrr"] += 1 / best if best else 0
        if best != 1:
            misses.append((r["cat"], r["query"], best, got[:3]))
    # isolation: tenant_other must never see tenant_demo files and vice-versa
    leaks = 0
    other_files = set(json.loads((HERE.parent / "data" / "tenant_other" / "manifest.json").read_text()))
    for r in rows:
        _, hits, _ = e.search("tenant_other", r["query"], k=10, use_parser=use_parser)
        leaks += sum(h.file_id not in other_files for h in hits)
    _, own, _ = e.search("tenant_other", "refund sepatu merah", k=5)
    own_ok = bool(own) and own[0].file_id == "docs/Refund_Invoice_Other_Company.pdf"

    print(f"{'category':10} {'n':>3} {'R@1':>6} {'R@10':>6} {'MRR':>6}")
    res = {}
    for k in sorted(per, key=lambda x: (x == "ALL", x)):
        p = per[k]
        res[k] = {"recall@1": p["r1"] / p["n"], "recall@10": p["r10"] / p["n"], "mrr@10": p["mrr"] / p["n"], "n": p["n"]}
        print(f"{k:10} {p['n']:>3} {res[k]['recall@1']:>6.3f} {res[k]['recall@10']:>6.3f} {res[k]['mrr@10']:>6.3f}")
    lat.sort()
    p95 = lat[int(len(lat) * 0.95) - 1]
    print(f"latency p50={lat[len(lat) // 2] * 1000:.0f}ms p95={p95 * 1000:.0f}ms   leaks={leaks}  own_tenant_ok={own_ok}")
    if verbose:
        for m in misses:
            print("  MISS", m)
    a = res["ALL"]
    checks = {
        "recall@10": a["recall@10"] >= GATE["recall@10"],
        "mrr@10": a["mrr@10"] >= GATE["mrr@10"],
        "recall@1": a["recall@1"] >= GATE["recall@1"],
        "every category recall@10": all(v["recall@10"] >= GATE["cat_recall@10"] for k, v in res.items() if k != "ALL"),
        "zero cross-tenant leaks": leaks == 0 and own_ok,
    }
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    out = {"metrics": res, "latency_p95_ms": round(p95 * 1000), "leaks": leaks, "checks": checks,
           "misses": [list(m) for m in misses]}
    (HERE / f"last_eval_{Path(golden).stem}.json").write_text(json.dumps(out, indent=1))
    return all(checks.values())


if __name__ == "__main__":
    g = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--golden=")), "golden.jsonl")
    ok = run(Engine(), verbose="--verbose" in sys.argv, use_parser="--no-parser" not in sys.argv, golden=g)
    sys.exit(0 if ok else 1)
