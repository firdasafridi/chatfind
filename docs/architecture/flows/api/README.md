---
topic: api
status: ready
related: [search, ingest, tenant-isolation, frontend]
code:
  - app/backend/api.py
  - app/backend/engine.py
---

Classification: INTERNAL

# API

## TL;DR

`app/backend/api.py` is one FastAPI app. It exposes 8 JSON routes under `/api` and serves the built React app from `app/web/dist` at `/`. Every tenant-scoped route resolves the tenant with `tenant()` before touching the engine. The engine is a singleton created by `eng()` (`api.py:34-40`), and a startup hook warms the models in the background.

## Routes

| Method | Path | Line | Input | Returns | Errors |
|---|---|---|---|---|---|
| GET | `/api/health` | 70 | nothing | `{"ok": true}` | none |
| GET | `/api/tenants` | 75 | nothing | `[{id, name}]` | none |
| GET | `/api/stats` | 80 | `X-Company-Id` | counts per type | 401 |
| GET | `/api/files` | 85 | `X-Company-Id` | file list | 401 |
| POST | `/api/search` | 90 | `X-Company-Id` + JSON body | see [search](../search/README.md#data) | 401, 422 |
| POST | `/api/upload` | 113 | `X-Company-Id` + multipart `file` | `ingest()` result | 401, 413, 415, 422 |
| GET | `/api/file` | 144 | query `id`, `company` | the file itself | 401, 404 |
| DELETE | `/api/file` | 151 | query `id` + `X-Company-Id` | `{"deleted": id}` | 401, 404 |

The search body (`SearchReq`, `api.py:49`) is `query` (1 to 300 chars), `type` (`image` or `document`), `channel` (`whatsapp`, `instagram`, `email`, `crm` or `upload`) and `limit` (1 to 50, default 12).

## Startup and static files

- `lifespan()` (`api.py:24-28`) starts a daemon thread that calls `eng().warmup()` when `WARMUP` is on (the default). `/api/health` answers while the models load. `Engine.warmup()` (`engine.py:308`) runs one text embed, one image query and one rerank, which takes the first search from about 12.7 s to under 1 s.
- `eng()` holds `_engine_lock` (`api.py:21`) while it creates the engine. The warmup thread and the first request can race, and embedded Qdrant allows only one client per directory.
- The UI is mounted last, at `api.py:160`, with `StaticFiles(directory=APP_DIR/"web"/"dist", html=True, check_dir=False)`. Because of `check_dir=False` the API and its tests start without a web build; `/` then returns 404 until `pnpm build` has run. Routes under `/api` are registered first, so the mount never shadows them.

## Upload validation

| Check | Line | Result on failure |
|---|---|---|
| Filename: take the base name, replace anything outside `A-Za-z0-9._-` with `_`, cut to 120 chars | 110, 116 | no failure, the name is cleaned |
| Extension must be jpg, jpeg, png, webp, pdf or txt | 118 | 415 "Tipe file … belum didukung…" |
| Size: read at most 20 MB + 1 byte | 120-122 | 413 "File lebih dari 20 MB" |
| Ingest raises | 126-130 | file deleted from disk, 422 "File tidak dapat diproses: <ExceptionType>" |

Error messages are in Indonesian because they're shown to end users as-is. Only the exception type is exposed, never its message, so no internal paths leak.

## File serving and delete

`_resolve(cid, id)` (`api.py:133-141`) looks the file up for that tenant and then checks that the resolved path is inside `DATA_DIR/<tenant>`. Both failures return 404, not 403, so the API doesn't reveal whether a file exists for another tenant.

`DELETE /api/file` removes the Qdrant points and the SQLite rows (`engine.py:285-291`). **The file stays on disk.** Before any real data goes in, delete has to remove the file as well (right to erasure).

## Known gaps

The tenant header and the `company` query parameter are trusted as sent. See [tenant-isolation](../cross-cutting/tenant-isolation/README.md#known-gaps-access-control).

## See also

- [frontend](../frontend/README.md)
- [testing](../cross-cutting/testing/README.md): `tests/test_api.py` covers every row above.
