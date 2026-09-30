"""(Re)build the index from data/<tenant>/manifest.json. Usage: python -m eval.index_all [--reset]"""
import json
import sys
import time

from backend import config as C
from backend.engine import Engine


def main():
    e = Engine()
    if "--reset" in sys.argv:
        e.reset()
    t0, n = time.time(), 0
    for tenant in C.TENANTS:
        man = json.loads((C.DATA_DIR / tenant / "manifest.json").read_text())
        for fid, meta in man.items():
            try:
                r = e.ingest(tenant, C.DATA_DIR / tenant / fid, fid, channel=meta["channel"], created_at=meta["created_at"])
            except Exception as ex:  # dead-letter: log and continue
                print("FAILED", tenant, fid, type(ex).__name__, ex)
                continue
            n += 1
            if r["status"] != "indexed":
                print(tenant, fid, r)
        print(tenant, e.stats(tenant))
    print(f"{n} files in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
