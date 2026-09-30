Classification: INTERNAL

# Glossary

Use these terms as written here. Add a term here before you use it in a spoke.

## Domain

| Term | Meaning |
|---|---|
| **tenant** | One customer company. In code it's `company_id` (for example `tenant_demo`). The registry is `config.TENANTS`. |
| **file_id** | A file's id within a tenant: `<folder>/<name>`, for example `uploads/receipt.jpg` |
| **point** | One vector record in Qdrant. An image has one `visual` point, plus one `ocr` point if it has text. A document has one `text` point per chunk. |
| **chunk** | A slice of 1,200 characters of document or OCR text. The text lives in SQLite `chunks`, never in Qdrant. |
| **kind** | Which evidence a point or hit came from: `visual`, `text` or `ocr` |
| **mime_group** | `image` or `document` |
| **channel** | Where a file came from: `whatsapp`, `instagram`, `email`, `crm`, `upload` |
| **type hint** | A soft preference for images or documents taken from words in the query ("foto", "invoice"). Unlike a type filter, it only down-weights the other kind. |
| **candidates** | The top 40 hits for each path before fusion (`CANDIDATES`) |
| **fusion** | Putting text and visual scores on one scale and ranking them together (`Engine.fuse`) |
| **conf** | The calibrated match probability of a hit. The badge is based on it. |
| **score** | The value results are sorted by: `conf` after ranking-only multipliers |
| **badge** | `strong` (conf ≥ 0.65), `good` (≥ 0.45) or `weak` |
| **golden set** | Queries with known right answers. **Dev** is `golden.jsonl`, used for tuning. **Blind** (holdout) is `golden_holdout.jsonl`, never tuned on. |
| **gate** | The pass/fail thresholds in `eval/evaluate.py` and `eval/STANDARD.md` |
| **leak** | A search result that belongs to another tenant. The target is always 0. |

## Status values

| Field | Values | Seen in |
|---|---|---|
| `files.status` / `ingest()` result | `indexed`, `duplicate`, `skipped` | ingest |
| doc frontmatter `status` | `ready`, `stale` | all spokes |

## Retrieval terms

| Term | Meaning |
|---|---|
| **dense vector** | An embedding of meaning (e5 or BGE-M3 for text, SigLIP for images) |
| **sparse vector** | Weights for exact words: BM25 with e5, lexical weights with BGE-M3 |
| **RRF** | Reciprocal Rank Fusion. Qdrant uses it to merge the dense and sparse text lists. |
| **reranker** | A cross-encoder that reads the query and a chunk together and scores relevance |
| **noisy-OR** | Combining two independent confidences: `1 - (1-a)(1-b)` |
| **Recall@k / MRR@10** | Whether the right file is in the top k, and 1/rank of the first right file averaged over queries |

## Models and services

| Name | Role | License |
|---|---|---|
| **Qdrant** | Vector database, embedded (`STATE_DIR/qdrant`) or a server (`QDRANT_URL`) | Apache-2.0 (client verified) |
| **SQLite** | Files table and chunk text | public domain |
| **multilingual-e5-small** | Demo text embeddings | MIT |
| **BGE-M3** | Production text embeddings (dense + sparse) | MIT |
| **mmarco-mMiniLMv2** | Demo reranker | Apache-2.0 |
| **bge-reranker-v2-m3** | Production reranker | Apache-2.0 |
| **SigLIP 2** | Image and text-to-image embeddings | Apache-2.0 |
| **opus-mt-id-en** | Indonesian to English query translation for the image path | CC-BY-4.0 (unverified locally) |
| **Tesseract** | OCR, `ind+eng` | Apache-2.0 |

## Env and config

`STATE_DIR`, `DATA_DIR`, `MODELS_DIR`, `TEXT_BACKEND`, `QDRANT_URL`, `QDRANT_API_KEY`, `QUERY_NOW` and `QUERY_TRANSLATE` are all described in [config-and-models](flows/cross-cutting/config-and-models/README.md).
