"""Fetch N Flickr-1k test images + captions (research/eval use only) for the demo tenant. Resumable."""
import json, sys, urllib.request
from pathlib import Path
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
out = Path(__file__).parent.parent / "data" / "tenant_demo" / "photos"
out.mkdir(parents=True, exist_ok=True)
cap_file = Path(__file__).parent / "captions.json"
caps = json.loads(cap_file.read_text()) if cap_file.exists() else {}
for off in range(0, N, 25):
    url = ("https://datasets-server.huggingface.co/rows?dataset=nlphuji/flickr_1k_test_image_text_retrieval"
           f"&config=TEST&split=test&offset={off}&length={min(25, N - off)}")
    rows = json.load(urllib.request.urlopen(url, timeout=60))["rows"]
    for r in rows:
        name = f"photo_{r['row_idx']:04d}.jpg"
        caps[name] = r["row"]["caption"]
        if not (out / name).exists() or (out / name).stat().st_size == 0:
            urllib.request.urlretrieve(r["row"]["image"]["src"], out / name)
    cap_file.write_text(json.dumps(caps, indent=1))
    print(off + len(rows), flush=True)
print(len(caps), "images")
