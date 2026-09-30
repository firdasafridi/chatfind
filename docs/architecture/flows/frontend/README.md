---
topic: frontend
status: ready
related: [api, testing]
code:
  - app/web/src/App.tsx
  - app/web/src/lib/api.ts
  - app/web/src/lib/format.ts
  - app/web/src/components/result-card.tsx
  - app/web/src/components/understood.tsx
  - app/web/src/components/preview-dialog.tsx
  - app/web/src/components/upload-panel.tsx
  - app/web/vite.config.ts
---

Classification: INTERNAL

# Frontend

## TL;DR

The frontend is a single page in `app/web/`, built with Vite, React 19, TypeScript, Tailwind v4 and shadcn/ui (base-nova style on Base UI primitives). `pnpm build` writes static files to `app/web/dist`, and FastAPI serves them at `/`. The page has a search box, filters, a results grid, a preview dialog and an upload drop zone. The UI text is in Indonesian. State lives in React state in `App.tsx`; nothing is stored in localStorage.

## Layout

| Path | What it holds |
|---|---|
| `src/App.tsx` | The page: tenant, filters, search state, results, preview, keyboard shortcut |
| `src/lib/api.ts` | Typed client for every route, `ApiError`, `fileUrl()` |
| `src/lib/format.ts` | Labels, `relDate()`, `highlight()`, `splitResults()`, `uploadMessage()` |
| `src/components/result-card.tsx` | One result: thumbnail, confidence badge, name, reason, snippet |
| `src/components/understood.tsx` | The "Dibaca sebagai" tokens |
| `src/components/preview-dialog.tsx` | Preview and delete |
| `src/components/upload-panel.tsx` | Drop zone, file picker, upload list |
| `src/components/ui/*` | shadcn generated: button, input, dialog, select, toggle, toggle-group, collapsible, skeleton, sonner |

## User flows

| Flow | Code | API call |
|---|---|---|
| Page load: fetch tenants, pick the first, load stats | `App.tsx:51-65` | `GET /api/tenants`, `GET /api/stats` |
| Switch tenant: reset the page and re-run the last search | `App.tsx:107` | `/api/stats`, `/api/search` |
| Search with `limit: 24`. Confident hits go in the grid. With no confident hit, the top results show with an "empty" notice. Weak hits sit in a collapsed section. | `App.tsx:67-90`, `format.ts:62` | `POST /api/search` |
| Type toggle and channel select | `App.tsx` | re-runs search |
| `/` focuses the search box unless an input already has focus | `App.tsx:94-100` | none |
| Pills showing what the parser understood | `understood.tsx` | none |
| Preview: image, PDF in an iframe opened at the matching page, or TXT in a `<pre>` | `preview-dialog.tsx:38-42` | `GET /api/file?company=&id=` |
| Delete from the preview: a delete button, then a second confirm button. Success and errors show as sonner toasts. | `preview-dialog.tsx:50-77`, `App.tsx:117-125` | `DELETE /api/file` |
| Upload: picker or drag and drop | `upload-panel.tsx:28` | `POST /api/upload` |

Stale responses are dropped. Each search takes a new id from `requestId` (`App.tsx:78`) and only the latest id may set the result (`App.tsx:86-88`), so a slow earlier search can't overwrite a newer one.

`request()` in `lib/api.ts` adds `X-Company-Id` to every call and turns a non-2xx response into an `ApiError` with FastAPI's `detail` string, or `HTTP <status>` when `detail` isn't a string. The one exception to the header is `fileUrl()` (`api.ts:97`): `<img src>` can't send headers, so it passes `company` as a query parameter.

## Rendering safety

There is no `innerHTML` or `dangerouslySetInnerHTML` in `app/web/src`. React escapes every value it renders. `highlight()` (`format.ts:42`) returns a list of plain and matched segments, and the card renders the matched ones as `<mark>` elements. URL parameters go through `encodeURIComponent`. Keep it that way: add fields as JSX text, never as HTML strings.

## Dev and build

- `pnpm dev` starts Vite and proxies `/api` to `http://127.0.0.1:8010`, or to `API_URL` when set (`vite.config.ts:11`).
- `pnpm build` runs `tsc -b` and `vite build` into `dist/`.
- `pnpm check` runs oxlint and `tsc -b --noEmit`.
- Components in `src/components/ui/` are generated. Change them with `pnpm dlx shadcn@latest add <name>` and delete unused ones.

## Test hooks

Elements use kebab-case `data-testid` attributes: `search-input`, `search-button`, `company-select`, `type-all`, `type-image`, `type-document`, `channel-select`, `examples`, `example-chip`, `understood`, `u-text`, `u-translated`, `u-date`, `u-type`, `u-channel`, `status`, `results`, `empty`, `error`, `weak-results`, `result-card`, `confidence`, `result-name`, `reason`, `snippet`, `stats`, `stat-image`, `stat-document`, `dropzone`, `file-input`, `upload-list`, `preview`, `preview-delete`, `preview-delete-confirm`. Vitest, Playwright (`app/web/e2e/`) and `app/e2e/search.sh` depend on these names, so rename them only together with those tests.

## See also

- [api](../api/README.md)
- [testing](../cross-cutting/testing/README.md) for Vitest and Playwright
