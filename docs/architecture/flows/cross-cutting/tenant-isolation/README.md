---
topic: tenant-isolation
status: ready
related: [api, ingest, search]
code:
  - app/backend/api.py
  - app/backend/engine.py
  - app/backend/config.py
---

Classification: INTERNAL

# Tenant isolation

## TL;DR

Every file belongs to one tenant (`company_id`). A tenant must never see another tenant's files, in results, snippets or previews. The engine enforces this in three places: the Qdrant filter, the SQLite queries and the file path check. Tenant identity is the weak spot. The demo trusts whatever the client sends, and production can't.

## Rule for anyone changing code

Any new Qdrant query must go through `Engine._filter(company_id, ...)`. Any new SQL that reads `files` or `chunks` must include `company_id=?`. Any new test that reads data must also assert that the other tenant gets nothing back. The golden-set eval checks this every run (`leaks=0`).

## Where it's enforced

| Layer | Location | What it does |
|---|---|---|
| API | `app/backend/api.py:29` `tenant()` | 401 unless the `X-Company-Id` header is a key in `config.TENANTS` |
| Qdrant search | `app/backend/engine.py:295` `_filter` | `company_id` is always the first `must` condition |
| Qdrant delete | `app/backend/engine.py:286-288` | Filter on `company_id` and `file_id` |
| SQLite | `engine.py:236` (dedup), `:357` (rerank text), `:420, 425, 429, 439` (files, stats, list), `:289-290` (delete) | `WHERE company_id=?` |
| Disk | `app/backend/api.py:109` | Uploads go under `DATA_DIR/<tenant>/` |
| Disk | `app/backend/api.py:119-127` `_resolve` | Looks up the file for this tenant, then rejects any path outside the tenant root (path traversal guard) |

Qdrant indexes `company_id` with `is_tenant=True` (`engine.py:189-206`), so the filter is cheap even with many tenants.

## Known gaps (access control)

These are fine for a demo but block production.

1. `X-Company-Id` comes from the client and isn't authenticated (`api.py:3-4`). Production must take the tenant from the authenticated session.
2. `GET /api/file` takes the tenant from a `company` query parameter (`api.py:131-134`), because `<img src>` can't send headers. Anyone who knows a tenant id and a file id can fetch the file. Replace this with short-lived signed URLs.
3. `GET /api/tenants` lists every tenant (`api.py:61-63`). It exists only for the demo tenant switcher.

`Engine.reset()` (`engine.py:208`) drops everything for all tenants. It's used only by `eval.index_all --reset` and isn't exposed over HTTP.

## Data minimisation

Qdrant payloads hold ids and filter fields only. Chunk text lives in SQLite and is read back only after the tenant filter. A Qdrant snapshot therefore contains no document text. Image EXIF, including GPS, is dropped at ingest.

## See also

- [api](../../api/README.md)
- [testing](../testing/README.md)
