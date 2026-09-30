---
topic: config-and-models
status: ready
related: [search, ingest, evaluation]
code:
  - app/backend/config.py
  - app/backend/engine.py
---

Classification: INTERNAL

# Config and models

## TL;DR

All settings live in `app/backend/config.py`. There are environment variables for things that change per deployment, and constants for tuned retrieval knobs. `TEXT_BACKEND` picks between the small demo models (e5) and the production models (BGE-M3). Models load lazily on first use, from `../models/<name>` when the weights are there and from the Hugging Face Hub otherwise.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `DATA_DIR` | `app/data` | Tenant files |
| `STATE_DIR` | `app/.state` | Embedded Qdrant + SQLite. Use a separate one for each backend. |
| `QDRANT_URL` | unset | Unset means embedded mode, set means server or cluster |
| `QDRANT_API_KEY` | unset | From the secret manager. Never commit it. |
| `COLLECTION` | `media_v1` | |
| `TEXT_BACKEND` | `e5` | `e5` or `bge-m3` |
| `IMAGE_MODEL` | `google/siglip2-base-patch16-256` | |
| `MODELS_DIR` | `../models` | Local weights folder |
| `TRANSLATE_MODEL` | `Helsinki-NLP/opus-mt-id-en` | CC-BY-4.0, needs attribution |
| `QUERY_TRANSLATE` | `1` | `0` turns off the translation blend |
| `QUERY_NOW` | unset | Pins "now" for relative dates (read in `query.py`) |
| `WARMUP` | `1` | `1` loads every model in a background thread when the API starts (`config.py:38`). `0` goes back to loading on the first search. |

## Backends

| | `e5` (demo default) | `bge-m3` (production target) |
|---|---|---|
| Dense | multilingual-e5-small, 384 dims, `query:`/`passage:` prefixes | BGE-M3, 1024 dims |
| Sparse | BM25 from `sparse.py`, IDF applied by Qdrant | BGE-M3 lexical weights |
| Reranker | mmarco-mMiniLMv2-L12 cross-encoder | bge-reranker-v2-m3 |
| Loader | sentence-transformers | FlagEmbedding |
| Blind-set R@10 / MRR / R@1 (2026-09-30) | 0.967 / 0.884 / 0.833 | 0.967 / 0.923 / 0.900 |
| Search p95, laptop CPU | 352 ms | 2,256 ms |

Both backends use SigLIP 2 for images and opus-mt for translation. The branch is at `config.py:17-22` and `engine.py:62-78`.

## Loading

- `_local()` (`config.py:30-32`) uses `MODELS_DIR/<last part of repo id>` when that folder has a `config.json`, and otherwise falls back to the hub id.
- `Models.txt`, `.reranker` and `.siglip` are lazy properties (`engine.py:59-87`), so the API starts fast. With `WARMUP=1` the API calls `Engine.warmup()` (`engine.py:308`) in a background thread at startup, so the first search takes under 1 s instead of about 12.7 s. With `WARMUP=0` the first search pays the load cost.
- `_device()` (`engine.py:32`) picks mps, then cuda, then cpu, but only SigLIP uses it. The text and rerank models are pinned to CPU (`engine.py:64, 67, 75, 78`). ASSUMPTION: this is part of why BGE-M3 is slow on a laptop. It hasn't been profiled.

## Tuned knobs

`config.py:47-62`: `CANDIDATES` 40, `CHUNK_CHARS` 1200 / `CHUNK_OVERLAP` 150, `OCR_MIN_CHARS` 20, the fusion weights (see [search](../../search/README.md#fusion)), and the badge thresholds 0.65 / 0.45. Change them only through `eval/tune.py` on the dev set, and record the change in `app/eval/TUNING.md`.

## See also

- [search](../../search/README.md)
- [evaluation](../../evaluation/README.md)
