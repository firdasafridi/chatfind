---
topic: testing
status: ready
related: [tenant-isolation, evaluation, api, frontend]
code:
  - app/tests/conftest.py
  - app/tests/test_api.py
  - app/tests/test_engine.py
  - app/tests/test_query.py
  - app/tests/test_sparse.py
  - app/tests/test_models.py
  - app/tests/test_eval.py
  - app/pytest.ini
  - app/web/vite.config.ts
  - app/web/playwright.config.ts
  - app/web/e2e/fixtures.ts
  - app/web/e2e/search.spec.ts
  - app/e2e/search.sh
  - scripts/check.sh
  - .github/workflows/ci.yml
---

Classification: INTERNAL

# Testing

## TL;DR

Backend unit and API tests run on fake models against a real embedded Qdrant in a temp dir: 83 tests with a 90% coverage gate (98.8% on the last run). The web app has Vitest unit tests (37, about 97% lines) and Playwright e2e (14, desktop and mobile) with the API mocked. The accuracy gate uses real models (see [evaluation](../../evaluation/README.md)). `scripts/check.sh` runs everything except the accuracy gate, and CI runs the same steps.

## Fixtures

`app/tests/conftest.py`:

| Fixture | What it gives you |
|---|---|
| `FakeModels` (26-54) | Deterministic stand-ins. Text vectors are a hashed bag of words. An image vector is its dominant colour (red, blue or green), so "red shoe" finds the red image. Rerank scores by word overlap. |
| `engine` (57-67) | An `Engine` with `STATE_DIR` and `DATA_DIR` in `tmp_path`, embedded Qdrant and `FakeModels` injected |
| `make_files` (70-93) | Writes a coloured PNG, a PDF with the given lines, or a TXT file for a tenant |

We fake the models and nothing else. Real models take minutes to load and need the network. Qdrant and SQLite are real, because the tenant filters and payload shapes are exactly what these tests exist to catch.

## What's covered

| File | Tests | Covers |
|---|---|---|
| `test_api.py` | 18 | health, 401 without a known tenant, response shape, 422 validation, cross-tenant search, fetch and delete, path traversal, filename cleaning, 415/413, corrupt upload, duplicate, delete, badge thresholds |
| `test_engine.py` | 20 | ranking, isolation both ways (50-56), unknown tenant, date, channel and type filters, dedup, tenant-scoped delete, Qdrant payload has no text (124), skip and OCR paths |
| `test_query.py` | 10 | relative dates, channel rules, type hints, fallback, `QUERY_NOW` |
| `test_sparse.py` | 6 | tokens, stopwords, TF saturation, empty input |
| `test_models.py` | 6 | model loading and backend selection, with the heavy libraries faked |
| `test_eval.py` | 7 | eval helpers and the gate logic |
| `test_accuracy.py` | 1 × 2 sets | the real-model gate, marked `accuracy`, deselected by default |

## Coverage

Backend: `pytest-cov` over `backend` and `eval`, with `--cov-fail-under=90` in `app/pytest.ini` and exclusions in `app/.coveragerc`. The function counts above are lower than the 83 collected tests because some tests are parametrized.

Web: Vitest with Testing Library in jsdom. Tests sit next to the source as `src/**/*.test.ts(x)` (`App.test.tsx`, `lib/api.test.ts`, `lib/format.test.ts`). Thresholds in `app/web/vite.config.ts:20` are 90% for lines, statements and functions and 85% for branches. Run with `pnpm coverage`.

## E2E

Playwright lives in `app/web/e2e/`. `app/web/playwright.config.ts` runs `pnpm build` and `vite preview` on port 4173 and has two projects, desktop and mobile (Pixel 7). `e2e/fixtures.ts` mocks every `/api` call with `page.route`, so no backend or models are needed, and fails a test on any browser console error. The flows are in `e2e/search.spec.ts`: 14 tests in total. Run with `pnpm e2e`.

`app/e2e/search.sh` is a separate smoke check against the real stack. It drives the running UI with playwright-cli, types a query and prints the pills, the top 5 cards and the empty or error state as JSON. `app/e2e/fixtures/malware.exe` is a 2-byte dummy for the "unsupported type" case.

## Gate and CI

`scripts/check.sh` runs, in order: backend pytest, `pnpm check` (oxlint and `tsc -b --noEmit`), `pnpm coverage`, and `pnpm e2e`. `SKIP_E2E=1` skips the last step. `.githooks/pre-push` calls it; enable the hook with `git config core.hooksPath .githooks`.

`.github/workflows/ci.yml` has two jobs. `backend` uses Python 3.13, installs `tesseract-ocr` from apt and CPU-only torch, then runs pytest. `web` uses pnpm 11 and Node 22, runs check, coverage, installs Playwright Chromium, runs e2e, and uploads the Playwright report when it fails.

## Rules

- Every test that reads data also asserts that the other tenant sees nothing.
- A new route needs a wrong-tenant case and a bad-input case in `test_api.py`.
- `scripts/check.sh` exiting 0 is the definition of done. Don't lower a coverage threshold to get there.
- A new UI flow needs a Playwright case, and any new test id goes in the frontend spoke.

## See also

- [tenant-isolation](../tenant-isolation/README.md)
- [evaluation](../../evaluation/README.md)
- [frontend](../../frontend/README.md)
