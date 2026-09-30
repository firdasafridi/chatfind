Classification: INTERNAL. 2026-09-30

# Accuracy iteration log

Each change was measured on the dev set (`golden.jsonl`, 73 queries) and then on the blind set (`golden_holdout.jsonl`, 30 queries, never used for tuning). Dev hitting 1.000 is overfit by construction. Quote the blind numbers.

| Step | Change | Dev MRR / R@1 | Blind MRR / R@1 / R@10 |
|---|---|---|---|
| 0 | Baseline: e5 dense + BM25 → RRF; mMiniLM rerank; SigLIP 2; raw probabilities | 0.900 / 0.849 | n/a |
| 1 | Parser: a channel needs a preposition ("kontrak whatsapp api" was filtered to the WA channel) | | |
| 2 | Fusion calibration (temperatures, OCR weight, type-hint penalty), tuned with 2-fold CV | 0.939 / 0.904 | |
| 3 | `has_ocr` flag: down-weight SigLIP "reading" rendered text (it duplicates OCR); distinctiveness z-score; 2 relabels where the photo genuinely matched (subway `photo_0117`) | 0.993 / 0.986 | 0.849 / 0.800 / 0.933 |
| 4 | Holdout label fix: the shipping label is from yesterday, so the query "hari ini" was mislabeled (changed to "kemarin") | | |
| 5 | ID→EN query translation blended into the SigLIP query (w = 0.3, chosen on dev) | 1.000 / 1.000 | 0.884 / 0.833 / 0.967 |
| 6 | Badge confidence separated from ranking score; OCR + visual combined with noisy-OR (ranking unchanged) | same | same |

## Blind misses that are still open

"anak-anak main dam" fails because the translation drops "dam" (checkers). It's rare vocabulary.

"wanita baju biru melihat isi dompet" lands at rank 5. SigLIP-base is weak on fine-grained Indonesian descriptions.

"orang latihan tendang samsak" is at rank 2, and the photo above it, `photo_0029` (a martial-arts scene), is arguably relevant too.

"notice period to terminate the subscription contract" is at rank 2. It's an English query against an Indonesian document.

"belanja roti tawar" is at rank 3 because the OCR weight favours documents with similar vocabulary.

## What to try next

1. BGE-M3 plus bge-reranker-v2-m3 (`TEXT_BACKEND=bge-m3`), the prod target. It wasn't run here because of download bandwidth.
2. VLM captions (A4) for Indonesian and fine-grained image queries.
3. A larger golden set (target 1,000) built from real, anonymised queries approved by the DPO.
