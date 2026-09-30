// Typed client for the FastAPI backend (app/backend/api.py). Keep the shapes in sync with that file.

export type Confidence = "strong" | "good" | "weak"
export type MimeGroup = "image" | "document"
export type Channel = "whatsapp" | "instagram" | "email" | "crm" | "upload"

export interface Tenant {
  id: string
  name: string
}

export interface Stats {
  image: number
  document: number
  skipped?: number
  total?: number
}

export interface Understood {
  search_text: string
  translated: string | null
  date: string | null
  type_hint: MimeGroup | null
  channel: Channel | null
  date_from: string | null
}

export interface SearchResult {
  file_id: string
  name: string
  mime_group: MimeGroup
  channel: Channel
  created_at: string
  score: number
  confidence: Confidence
  match: "visual" | "text" | "ocr"
  reason: string
  page: number | null
  snippet: string | null
}

export interface SearchResponse {
  query: string
  understood: Understood
  took_ms: number
  results: SearchResult[]
}

export type UploadResult =
  | { file_id: string; status: "indexed"; points: number; mime_group: MimeGroup; ocr: boolean }
  | { file_id: string; status: "duplicate"; duplicate_of: string }
  | { file_id: string; status: "skipped"; reason: string }

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, company: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (company) headers.set("X-Company-Id", company)
  const res = await fetch(path, { ...init, headers })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    // FastAPI puts messages in `detail`; validation errors send a list there instead of a string.
    const detail = typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`
    throw new ApiError(detail, res.status)
  }
  return body as T
}

export const api = {
  tenants: () => request<Tenant[]>("/api/tenants", null),
  stats: (company: string) => request<Stats>("/api/stats", company),
  search: (
    company: string,
    body: { query: string; type: MimeGroup | null; channel: Channel | null; limit: number },
  ) =>
    request<SearchResponse>("/api/search", company, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  upload: (company: string, file: File) => {
    const fd = new FormData()
    fd.append("file", file)
    return request<UploadResult>("/api/upload", company, { method: "POST", body: fd })
  },
  remove: (company: string, fileId: string) =>
    request<{ deleted: string }>(`/api/file?id=${encodeURIComponent(fileId)}`, company, { method: "DELETE" }),
}

// <img src> can't send headers, so the file route takes the tenant as a query param (demo only).
export const fileUrl = (company: string, fileId: string) =>
  `/api/file?company=${encodeURIComponent(company)}&id=${encodeURIComponent(fileId)}`
