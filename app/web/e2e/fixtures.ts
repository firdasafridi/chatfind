import { test as base, expect, type Page } from "@playwright/test"

export type Hit = Record<string, unknown>

export const hit = (over: Hit = {}): Hit => ({
  file_id: "photos/dog.jpg",
  name: "dog.jpg",
  mime_group: "image",
  channel: "whatsapp",
  created_at: new Date().toISOString(),
  score: 0.82,
  confidence: "strong",
  match: "visual",
  reason: "Isi gambar cocok dengan deskripsi Anda",
  page: null,
  snippet: null,
  ...over,
})

// 1x1 PNG so <img> thumbnails load without a backend.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64")

export class FakeApi {
  searches: { body: Record<string, unknown>; tenant: string | null }[] = []
  deleted: string[] = []
  results: Hit[] = [hit()]
  understood: Record<string, unknown> = {}
  uploadStatus: Record<string, unknown> = { status: "indexed", points: 1, mime_group: "document", ocr: false }

  async install(page: Page) {
    await page.route("**/api/**", async (route) => {
      const req = route.request()
      const url = new URL(req.url())
      const tenant = req.headers()["x-company-id"] ?? null
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
      switch (`${req.method()} ${url.pathname}`) {
        case "GET /api/tenants":
          return json([
            { id: "tenant_demo", name: "Toko Lari Cepat (demo)" },
            { id: "tenant_other", name: "PT Lain Sejahtera" },
          ])
        case "GET /api/stats":
          return json(tenant === "tenant_other" ? { image: 0, document: 2 } : { image: 120, document: 21 })
        case "POST /api/search": {
          const body = req.postDataJSON()
          this.searches.push({ body, tenant })
          return json({
            query: body.query,
            took_ms: 37,
            understood: { search_text: body.query, translated: null, date: null, type_hint: null, channel: null, date_from: null, ...this.understood },
            results: tenant === "tenant_other" ? [] : this.results,
          })
        }
        case "POST /api/upload":
          return json({ file_id: "uploads/x", ...this.uploadStatus })
        case "DELETE /api/file":
          this.deleted.push(url.searchParams.get("id")!)
          this.results = this.results.filter((r) => r.file_id !== url.searchParams.get("id"))
          return json({ deleted: url.searchParams.get("id") })
        case "GET /api/file":
          return route.fulfill({ status: 200, contentType: "image/png", body: PNG })
      }
      return json({ detail: "not found" }, 404)
    })
  }
}

export const test = base.extend<{ api: FakeApi }>({
  api: async ({ page }, provide) => {
    const api = new FakeApi()
    await api.install(page)
    const errors: string[] = []
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()))
    page.on("pageerror", (e) => errors.push(e.message))
    await provide(api)
    expect(errors, "browser console errors").toEqual([])
  },
})

export { expect }
