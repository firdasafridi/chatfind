Classification: INTERNAL

# Quality standard: Cari Media POC

A build is accepted only when every check below holds.

## A. Retrieval accuracy

Both sets have to pass:

- dev, `golden.jsonl`: 73 queries, used for tuning
- blind, `golden_holdout.jsonl`: 30 new queries on photos that were not used in tuning. Never tune on it.

Run `python -m eval.evaluate [--golden=golden_holdout.jsonl]`. The tenant has 148 files, with queries in Indonesian and English.

| Metric | Gate |
|---|---|
| Overall Recall@10 | ≥ 0.90 |
| Overall MRR@10 | ≥ 0.75 |
| Overall Recall@1 | ≥ 0.65 |
| Recall@10 in every category (image_en, image_id, doc, ocr, filter) | ≥ 0.80 |

## B. Security and privacy

| Check | Gate |
|---|---|
| Cross-tenant leaks across all golden queries, both directions | 0 |
| Cross-tenant file fetch / delete | 404 |
| Path traversal on file endpoint | 404 |
| Vector payload contains no text | enforced by unit test |
| Upload type allow-list + 20 MB cap | 415 / 413 |

## C. Engineering

| Check | Gate |
|---|---|
| Unit + API tests | 100% pass |
| Playwright e2e in `web/e2e/` (`pnpm e2e`) | 100% pass, 0 console errors |
| Browser console errors during E2E | 0 |
| Search latency p95 (laptop CPU, warm) | < 1,500 ms (prod target 400 ms on GPU) |

## D. Usability

Every result explains in plain Indonesian why it matched (visual, text in the image, or a document page) and how sure the match is. The UI also shows the user how it read the query: date, type and channel.

Empty and error states tell the user what to try next. The page works at 390 px width without horizontal scrolling.
