Classification: INTERNAL. POC with synthetic or anonymised data only. Never load real customer media.

# POC: semantic media search

```bash
brew install tesseract tesseract-lang          # OCR incl. Indonesian (ind)
docker compose up -d                           # Qdrant on 127.0.0.1:6333
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python poc.py init
python poc.py ingest tenant_a samples/
python poc.py ingest tenant_b other_samples/   # to prove tenant isolation
python poc.py search tenant_a "struk belanja minggu lalu"
python poc.py search tenant_b "struk belanja"  # must NOT return tenant_a files
python poc.py eval   tenant_a golden.jsonl
```

Each line of `golden.jsonl` is one query and the files it should return:

```json
{"query": "foto sepatu merah", "expected": ["shoe_red.jpg"]}
{"query": "invoice refund bulan lalu", "expected": ["INV_refund.pdf"]}
```

The POC exit criteria were: golden-set Recall@10 >= 0.80 and MRR@10 >= 0.60, zero cross-tenant leaks, and a duplicate upload producing one set of points.
