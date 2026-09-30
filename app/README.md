Classification: INTERNAL. POC with synthetic data only. Never load real customer media.

# chatfind app: backend + UI

The goal is semantic search over the media and attachments in chat conversations. An agent finds a photo or document by describing it in Indonesian or English instead of remembering a filename. Every search is scoped to one tenant and the whole stack is self-hosted. This is a research demo, not a production service.

## Run

```bash
cd app
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
brew install tesseract tesseract-lang                 # OCR incl. Indonesian
../.venv/bin/python eval/fetch_images.py 120          # eval photos + captions (Flickr-1k test, research use)
../.venv/bin/python eval/seed_docs.py                 # synthetic PDFs + receipts + manifests
../.venv/bin/python -m eval.index_all --reset         # build index (embedded Qdrant, no Docker)
(cd web && pnpm install && pnpm build)               # UI build into web/dist
../.venv/bin/uvicorn backend.api:app --port 8000      # UI at http://127.0.0.1:8000
```

The API loads the models in a background thread at startup (`WARMUP=1`, the default), so the first search takes under 1 s instead of about 12.7 s. Set `WARMUP=0` to skip that.

For UI work, run uvicorn on `--port 8010` and `cd web && pnpm dev`. Vite proxies `/api` to `http://127.0.0.1:8010`; set `API_URL` to point it somewhere else.

If port 8000 is already taken, pick another one, for example `--port 8010`, and open http://127.0.0.1:8010 instead.

The Flickr-1k photos that `eval/fetch_images.py` downloads are for research use only. Don't redistribute them or commit them anywhere public.

To run against a Qdrant server or cluster instead of the embedded one, set `QDRANT_URL` (and `QDRANT_API_KEY`, taken from the secret manager).

## Tests

| Layer | Command | What it proves |
|---|---|---|
| Backend unit + API (fast, fake models) | `../.venv/bin/python -m pytest` | 83 tests, coverage gate 90% (98.8% on the last run). Query parser (dates, channel, type), BM25, engine (tenant isolation, dedup, idempotency, delete, filters, OCR, no text in vector payload), API (auth header, validation, upload limits, path traversal, cross-tenant 404) |
| Accuracy gate (real models) | `../.venv/bin/python -m pytest -m accuracy` or `python -m eval.evaluate --verbose` | The standard in [eval/STANDARD.md](eval/STANDARD.md) |
| Web unit | `cd web && pnpm coverage` | 37 Vitest + Testing Library tests, thresholds 90% lines/statements/functions and 85% branches |
| Web E2E | `cd web && pnpm e2e` | 14 Playwright tests (desktop and Pixel 7) against a production build with `/api` mocked, failing on any console error |
| Real-stack smoke | `e2e/search.sh` with playwright-cli | Types a query into the running app and prints the results as JSON |

`../scripts/check.sh` runs backend pytest, `pnpm check`, `pnpm coverage` and `pnpm e2e` in order, as CI does.

Heads up: `eval/evaluate.py` overwrites `eval/last_eval_*.json` every time it runs. Copy those files somewhere else first if you want to keep an earlier result.

## Layout

```
backend/  config.py  query.py (ID/EN query understanding)  sparse.py (BM25)  engine.py (index, hybrid search, fusion)  api.py (FastAPI)
web/      Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui; src/ (App.tsx, lib/, components/), e2e/ (Playwright)
eval/     fetch_images.py  seed_docs.py  index_all.py  golden.jsonl  golden_holdout.jsonl  evaluate.py  tune.py  STANDARD.md  TUNING.md
tests/    unit + API + accuracy gate
e2e/      search.sh (playwright-cli smoke against the real stack) + fixtures
```

## Models (demo vs prod)

| | Demo default (`TEXT_BACKEND=e5`) | Prod target (`TEXT_BACKEND=bge-m3`) |
|---|---|---|
| Text dense | multilingual-e5-small (MIT) | BGE-M3 (MIT) |
| Sparse | BM25 with IDF applied by Qdrant | BGE-M3 learned sparse |
| Reranker | mmarco-mMiniLMv2-L12 (Apache-2.0) | bge-reranker-v2-m3 (Apache-2.0) |
| Image | SigLIP 2 base-256 (Apache-2.0) | SigLIP 2 |
| Query translation (image tower) | opus-mt-id-en (CC-BY-4.0) | same, or a VLM caption index |
| OCR | Tesseract ind+eng | PaddleOCR |

The demo defaults to the smaller models because of a download-bandwidth limit (about 1 GB instead of 4.5 GB). Both backends run the same pipeline code. Weights load from `../models/<name>` when that folder exists (offline installs) and from the Hugging Face Hub otherwise.

The embedded Qdrant locks `.state/`, so stop the API server before running `eval.*` or `pytest -m accuracy`.

### Prod backend

Set `TEXT_BACKEND=bge-m3` with the weights in `../models/bge-m3` and `../models/bge-reranker-v2-m3`. Give it its own `STATE_DIR`. BGE-M3 vectors are 1024-dimensional and e5 vectors are 384, so the two indexes can't share a state directory.

On the blind set (eval run on 2026-09-30), bge-m3 scored R@10 0.967, MRR 0.923 and R@1 0.900. The e5 numbers on the same set were 0.967, 0.884 and 0.833. Ranking gets better, but search p95 was 2256 ms on laptop CPU against 352 ms for e5. That is over the 1,500 ms p95 gate in [eval/STANDARD.md](eval/STANDARD.md), which is why e5 is still the demo default.

## Results (2026-09-30, laptop CPU, e5): standard in `eval/STANDARD.md` met

| Gate | Dev (73 q, tuned) | Blind (30 q, never tuned) |
|---|---|---|
| Recall@10 (≥ 0.90) | 1.000 | 0.967 |
| MRR@10 (≥ 0.75) | 1.000 | 0.884 |
| Recall@1 (≥ 0.65) | 1.000 | 0.833 |
| Every category Recall@10 (≥ 0.80) | ✅ | ✅ (image_id 0.875 is the weakest) |
| Cross-tenant leaks | 0 | 0 |
| Search p95 | 318 ms | 352 ms |

83 backend tests, 37 web unit tests and 14 Playwright tests pass. The iteration log and the remaining misses are in [eval/TUNING.md](eval/TUNING.md).

Quote the blind numbers. The dev set was used for tuning, so its scores are optimistic.
