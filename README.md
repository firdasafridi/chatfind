Classification: INTERNAL

# chatfind

chatfind lets you find a file from a chat by describing it. Type "struk belanja minggu lalu" or "photo of a red shoe" and it searches the images, PDFs and receipt photos that people sent, in Indonesian or English. You don't need to remember a filename or scroll back through a conversation. It is self-hosted, so the files and the index stay on your own servers, and every model it uses has a permissive license.

## Quick start

```bash
cd app
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
brew install tesseract tesseract-lang                 # OCR, including Indonesian
../.venv/bin/python eval/fetch_images.py 120          # eval photos + captions (research use only)
../.venv/bin/python eval/seed_docs.py                 # synthetic PDFs, receipts and manifests
../.venv/bin/python -m eval.index_all --reset         # build the index (embedded Qdrant, no Docker)
```

The UI is a Vite, React and TypeScript app in `app/web`. It builds to static files that FastAPI serves at `/`:

```bash
cd app/web && pnpm install && pnpm build
cd .. && ../.venv/bin/uvicorn backend.api:app --port 8000   # open http://127.0.0.1:8000
```

For UI work, run the API on port 8010 and the Vite dev server next to it. The dev server proxies `/api` to `http://127.0.0.1:8010` (set `API_URL` to change it):

```bash
cd app && ../.venv/bin/uvicorn backend.api:app --port 8010
cd app/web && pnpm dev
```

To run every check CI runs (backend tests, web lint and typecheck, web unit tests, Playwright e2e):

```bash
scripts/check.sh                      # SKIP_E2E=1 skips the browser tests
git config core.hooksPath .githooks   # run it before every push
```

More detail is in [app/README.md](app/README.md).

## How it works

1. Each upload is hashed per tenant, so the same file is indexed once.
2. PDFs are split into text chunks, receipt photos go through Tesseract OCR, and photos get an image embedding from SigLIP 2.
3. Text gets a dense vector and a sparse BM25 vector. Vectors and filter fields go to Qdrant; the text itself stays in SQLite.
4. A query is parsed for dates, file type and channel, then searched across all vectors with a tenant filter on every lookup.
5. Results are fused, reranked with a cross-encoder, and returned with a snippet.

## Results

Blind set of 30 queries that were never used for tuning, run on 2026-09-30 on a laptop CPU.

| Text backend | Recall@10 | MRR@10 | Recall@1 | Search p95 |
|---|---|---|---|---|
| multilingual-e5-small (default) | 0.967 | 0.884 | 0.833 | 352 ms |
| bge-m3 | 0.967 | 0.923 | 0.900 | 2256 ms |

bge-m3 ranks better but is too slow on CPU for the 1,500 ms gate, so e5 is the default. The gate is described in [app/eval/STANDARD.md](app/eval/STANDARD.md).

## Licensing

The code in this repository is under the Apache License 2.0 (see [LICENSE](LICENSE)). The models are downloaded separately and are MIT or Apache-2.0, except opus-mt-id-en, which is CC-BY-4.0 and needs attribution. Credits are in [NOTICE](NOTICE).

The evaluation photos come from the Flickr-1k test split. They are for research use only and are not included in this repository.

## More

- [docs/architecture/architecture.md](docs/architecture/architecture.md) explains how the code fits together.
- [AGENTS.md](AGENTS.md) has the working rules for contributors and coding agents.
