Classification: INTERNAL

# AGENTS.md: chatfind

> This is the single source of truth for every AI agent (Claude, Cursor, Copilot). Edit only this file. The other agent config files point here.

## Before you start

1. Read `docs/architecture/architecture.md` and the spoke for your change. If your change contradicts a documented rule, stop and ask.
2. Run the baseline: `scripts/check.sh` from the repo root (or `SKIP_E2E=1 scripts/check.sh` for a quicker pass). It must end with `all checks passed`.
3. If the baseline is red, stop and report it. Don't build on a failing tree.

## Definition of done

- [ ] `scripts/check.sh` exits 0. It runs backend pytest (coverage at least 90%), web lint and typecheck, web unit tests (coverage gate) and Playwright e2e, the same steps as CI.
- [ ] New behaviour has a test (see the trigger table in "Testing").
- [ ] Changes to retrieval, fusion, query parsing or models: `python -m eval.evaluate` passes on **both** `golden.jsonl` and `golden_holdout.jsonl`, and holdout Recall@10 / MRR@10 do not drop compared with the previous `eval/last_eval_golden_holdout.json`.
- [ ] Cross-tenant leaks stay at 0.
- [ ] The docs in the trigger table below are updated.
- [ ] Only the files the task needs were touched.

## Project overview

Open-source, self-hosted semantic search for chat media. You describe a file in Indonesian or English ("struk belanja minggu lalu", "photo of a red shoe") and it finds images, PDFs and receipts. Every tenant's data stays isolated. The stack is Python 3.13, FastAPI, Qdrant (embedded, or a server via `QDRANT_URL`), SQLite, sentence-transformers / FlagEmbedding, SigLIP 2, Tesseract OCR. The UI in `app/web/` is Vite, React 19, TypeScript, Tailwind v4 and shadcn/ui (base-nova style on Base UI primitives). FastAPI serves its build output.

## Safe commands

```bash
# Run everything from app/ with the repo venv
cd app

# Tests (unit + API; accuracy tests are deselected by pytest.ini)
../.venv/bin/python -m pytest
../.venv/bin/python -m pytest -m accuracy          # slow, real models, needs a built index

# Build the demo corpus and index
../.venv/bin/python eval/fetch_images.py 120      # Flickr-1k test photos, research use only
../.venv/bin/python eval/seed_docs.py             # synthetic PDFs + receipts + manifests
../.venv/bin/python -m eval.index_all --reset

# Accuracy gate
../.venv/bin/python -m eval.evaluate --verbose
../.venv/bin/python -m eval.evaluate --verbose --golden=golden_holdout.jsonl
../.venv/bin/python -m eval.tune                  # fusion params, dev set only

# Run the service (UI + API)
../.venv/bin/uvicorn backend.api:app --port 8000

# Prod text backend: use a separate state dir (1024-dim vectors vs 384 for e5)
TEXT_BACKEND=bge-m3 STATE_DIR=/tmp/state_bge ../.venv/bin/python -m eval.index_all --reset
```

Web UI, from `app/web/`:

```bash
pnpm install
pnpm dev          # Vite dev server, proxies /api to http://127.0.0.1:8010 (override with API_URL)
pnpm build        # tsc + vite build into app/web/dist, which FastAPI serves at /
pnpm check        # oxlint src e2e && tsc -b --noEmit
pnpm test         # Vitest once
pnpm coverage     # Vitest with coverage thresholds
pnpm e2e          # Playwright, builds and runs vite preview on :4173
```

Whole gate, from the repo root:

```bash
scripts/check.sh                 # everything CI runs
SKIP_E2E=1 scripts/check.sh      # skip the browser tests
git config core.hooksPath .githooks   # run the gate on every git push
```

The backend has no linter configured; match the surrounding style. The web code is linted with oxlint and typechecked with `tsc`.

## Naming conventions

| Concept | Pattern | Example |
|---|---|---|
| Backend module | `snake_case.py` in `app/backend/` | `backend/query.py` |
| Class | `PascalCase` | `Engine`, `Models`, `Hit`, `ParsedQuery` |
| Config knob | `UPPER_SNAKE` in `backend/config.py`, env override when it varies per deploy | `TEXT_BACKEND`, `CANDIDATES`, `OCR_WEIGHT` |
| API route | `/api/<noun>`, tenant from the `x-company-id` header | `POST /api/search`, `DELETE /api/file` |
| API error | `HTTPException(<status>, "<message>")`; user-facing messages are in Indonesian | `HTTPException(413, "File lebih dari 20 MB")` |
| Test file | `tests/test_<module>.py` | `tests/test_sparse.py` |
| React component | kebab-case `.tsx` in `app/web/src/components/`, exported as `PascalCase` | `result-card.tsx` exports `ResultCard` |
| Web unit test | next to the source as `*.test.ts(x)` | `src/lib/format.test.ts` |
| E2E spec | `app/web/e2e/<flow>.spec.ts` | `e2e/search.spec.ts` |
| Test id | kebab-case `data-testid` | `result-card`, `preview-delete-confirm` |
| Test fixture | in `tests/conftest.py` | `engine`, `make_files`, `FakeModels` |
| Golden query | JSONL row `{"query", "expected": [file_id], "cat"}`; cat ∈ `doc, filter, image_en, image_id, ocr` | `eval/golden.jsonl` |
| file_id | `<folder>/<filename>` relative to the tenant dir | `photos/photo_0006.jpg`, `uploads/x.pdf` |
| Tenant id | `tenant_<name>`, registered in `config.TENANTS` | `tenant_demo` |

## Architecture

| Layer | Folder | Responsibility | Hard constraint |
|---|---|---|---|
| API | `app/backend/api.py` | HTTP routes, upload validation, serves `web/dist` at `/` | Resolve the tenant with `tenant()` on every route. Never take `company_id` from the body or query string. |
| Engine | `app/backend/engine.py` | Ingest, embed, Qdrant queries, rerank, fusion, dedup, delete | Every Qdrant query goes through `_filter(company_id, ...)`. Every SQLite chunk read includes `company_id=?`. |
| Query understanding | `app/backend/query.py` | Dates, type hints and channel from ID/EN text | Pure functions. Pass `now` for tests; `QUERY_NOW` pins time in evals. |
| Sparse | `app/backend/sparse.py` | BM25 tokens → Qdrant sparse vectors (IDF applied by Qdrant) | Keep `doc_vector` and `query_vector` tokenisation identical. |
| Config | `app/backend/config.py` | Env vars, model choice, tuned fusion knobs | Secrets come from env only (`QDRANT_API_KEY`). Never hard-code them. |
| Web | `app/web/src/` | React single page: `App.tsx`, `lib/api.ts` (typed client), `lib/format.ts`, `components/` | Never use `innerHTML` or `dangerouslySetInnerHTML`. `highlight()` returns segments and React renders the `<mark>`. All calls go through `lib/api.ts`, which adds `X-Company-Id`. |
| Eval | `app/eval/` | Corpus seeding, golden sets, gate, tuning | Tune only on `golden.jsonl`. `golden_holdout.jsonl` is blind: never tune on it and never add its misses to the dev set. |
| POC | `poc/` | Original single-file CLI prototype | Frozen reference. Don't extend it; new work goes in `app/`. |

Chunk text lives in SQLite, not in the Qdrant payload (a Qdrant snapshot must contain no personal data).

## Architecture documentation

Start at `docs/architecture/architecture.md`, then load only the spoke for your task (`docs/architecture/flows/<topic>/README.md`). Each spoke is self-contained. The rules are in `docs/architecture/CONVENTIONS.md` and the terms in `docs/architecture/GLOSSARY.md`.

When you change code listed in a spoke's `code:` frontmatter, ask three questions:

1. Did the flow change? Update the spoke and keep `status: ready`.
2. Did you add or rename something the docs name? Add it to the glossary first, then update or add a spoke.
3. Is it cosmetic only? Leave the docs alone.

Don't fork a spoke, invent synonyms for glossary terms, or link to files that don't exist. Check with `python3 ~/.claude/skills/repo-docs/verify.py`.

## Doc updates are part of the task

A change is not done until the matching doc is updated.

| What changed | Update |
|---|---|
| Model, fusion knob, or anything that moves eval numbers | Results table in `app/README.md` + a row in `app/eval/TUNING.md` |
| Gate thresholds | `app/eval/STANDARD.md` and `GATE` in `app/eval/evaluate.py` together |
| Architecture rule or flow | `docs/architecture/architecture.md` and the matching spoke |
| New command, env var or setup step | "Safe commands" here + `app/README.md` |
| New API route or UI flow | `docs/architecture/flows/frontend/README.md` and a case in `app/web/e2e/search.spec.ts` |

## How to add a new feature

1. Check that it fits the rules in `docs/architecture/architecture.md` and this file. If it doesn't, ask first.
2. Add knobs to `app/backend/config.py`, with a comment saying why and the tuning date.
3. Implement in `app/backend/engine.py` (retrieval/ingest) or `app/backend/query.py` (parsing). Keep the tenant filter on every new query path.
4. Expose it in `app/backend/api.py` behind `tenant(x_company_id)`.
5. Add the UI in `app/web/src/` if it's user-facing: a client function in `lib/api.ts`, a component in `components/`, wiring in `App.tsx`.
6. Add tests: unit in `app/tests/test_engine.py` or `test_query.py`, API in `test_api.py`, with an isolation case when the feature reads data. UI changes get a Vitest test and, for a new flow, a Playwright case.
7. If it affects ranking, add golden rows to `app/eval/golden.jsonl` only, then run the gate on both sets.
8. Update the docs per the table above.

## Testing and CI

| What changed | Required test | Location | Isolation |
|---|---|---|---|
| Query parsing | Unit test with a fixed `now` | `tests/test_query.py` | Pure |
| Tokeniser / sparse | Unit test | `tests/test_sparse.py` | Pure |
| Ingest, dedup, delete, fusion | Unit test with the `engine` fixture | `tests/test_engine.py` | `FakeModels` + `tmp_path` state |
| API route / validation | TestClient test incl. wrong-tenant and bad-input cases | `tests/test_api.py` | `tmp_path` state |
| Models, fusion params, retrieval | `eval.evaluate` on both golden sets | `app/eval/` | Built index in `STATE_DIR` |
| Web logic or component | Vitest + Testing Library | `app/web/src/**/*.test.ts(x)` | jsdom, `fetch` mocked |
| UI flow | Playwright spec | `app/web/e2e/search.spec.ts` | `/api` mocked with `page.route` in `e2e/fixtures.ts` |
| Real stack smoke (optional) | `app/e2e/search.sh` with playwright-cli | `app/e2e/` | Running server + built index |

Rules that are always in force:

- Unit and API tests use `FakeModels` (`tests/conftest.py`) instead of real models. Real models take minutes to load and would make the suite slow and network-dependent. Accuracy is checked separately with real models via `pytest -m accuracy` and `eval.evaluate`.
- Don't mock Qdrant or SQLite. Tests run against the real embedded Qdrant in `tmp_path`, because tenant filters and fusion behaviour are exactly what they need to catch.
- Every test that reads data must also assert that another tenant can't see it.
- Coverage gates: backend 90% (`--cov-fail-under=90` in `app/pytest.ini`), web 90% lines, statements and functions and 85% branches (`app/web/vite.config.ts`). Don't lower them to get green.
- The Playwright fixture fails a test on any browser console error.
- CI is `.github/workflows/ci.yml`: a backend job (Python 3.13, apt tesseract-ocr, CPU torch) and a web job (pnpm 11, Node 22, check, coverage, e2e, report uploaded on failure). `scripts/check.sh` runs the same steps locally.

## Things to watch out for

- The embedded Qdrant locks `STATE_DIR`. Stop uvicorn before running `eval.*` or `pytest -m accuracy` against `app/.state`, or you'll get a lock error.
- `eval.evaluate` overwrites `eval/last_eval_*.json`. Copy the old file first if you need it for comparison.
- Switching `TEXT_BACKEND` changes the vector size (e5 384, bge-m3 1024). Reusing the same `STATE_DIR` without `--reset` breaks. Use a separate state dir.
- Relative-date queries are evaluated against `data/seeded_at.txt` (`QUERY_NOW`). If you re-seed the corpus without re-indexing, "last week" results drift.
- Dedup is sha256 per tenant. Re-uploading an indexed file returns `status: duplicate`; that's not a bug.
- Fusion knobs in `config.py` were tuned for e5 on 2026-09-30. After a model swap, re-run `eval.tune` on the dev set before claiming a regression.
- `api.py` trusts the `x-company-id` header. That's demo-only; production must derive the tenant from the authenticated session.
- Flickr-1k photos (`app/data/tenant_demo/photos/`, `eval/captions.json`) are research-use only. Never commit or redistribute them. `.gitignore` already excludes them.
- `app/e2e/fixtures/malware.exe` is a 2-byte dummy for the upload-rejection test, not real malware. Keep it.
- Never put real customer data, PII or secrets in fixtures, golden sets or logs.
- `pnpm lint` doesn't reach the package script under pnpm 11, so the lint and typecheck script is named `check`. Use `pnpm check`.
- `WARMUP=1` (the default) loads all models in a background thread when the API starts. Set `WARMUP=0` for quick restarts or when another process holds the embedded Qdrant lock. `eng()` is guarded by a lock because embedded Qdrant allows one client per directory.
- The static mount uses `check_dir=False`, so the API and its tests start without `app/web/dist`. Without a build, `/` returns 404; run `pnpm build` first.
- `app/web/src/components/ui/*` is generated by shadcn. Add or update a component with `pnpm dlx shadcn@latest add <name>` instead of hand-editing it, and delete components nothing imports.
