import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, api, fileUrl } from "./api"

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

afterEach(() => vi.unstubAllGlobals())

describe("api client", () => {
  it("sends the tenant header on tenant-scoped calls only", async () => {
    const fetch = vi.fn().mockResolvedValue(ok([]))
    vi.stubGlobal("fetch", fetch)

    await api.tenants()
    expect(new Headers(fetch.mock.calls[0][1].headers).has("X-Company-Id")).toBe(false)

    await api.stats("tenant_a")
    expect(new Headers(fetch.mock.calls[1][1].headers).get("X-Company-Id")).toBe("tenant_a")
  })

  it("posts search as JSON", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ results: [] }))
    vi.stubGlobal("fetch", fetch)
    await api.search("t", { query: "struk", type: "image", channel: null, limit: 24 })
    const [path, init] = fetch.mock.calls[0]
    expect(path).toBe("/api/search")
    expect(init.method).toBe("POST")
    expect(JSON.parse(init.body)).toEqual({ query: "struk", type: "image", channel: null, limit: 24 })
  })

  it("uploads multipart and deletes by encoded id", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({}))
    vi.stubGlobal("fetch", fetch)
    await api.upload("t", new File(["x"], "a.txt"))
    expect(fetch.mock.calls[0][1].body).toBeInstanceOf(FormData)
    await api.remove("t", "uploads/a b.pdf")
    expect(fetch.mock.calls[1][0]).toBe("/api/file?id=uploads%2Fa%20b.pdf")
    expect(fetch.mock.calls[1][1].method).toBe("DELETE")
  })

  it("surfaces FastAPI's detail message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "File lebih dari 20 MB" }), { status: 413 })))
    await expect(api.stats("t")).rejects.toMatchObject({ message: "File lebih dari 20 MB", status: 413 })
  })

  it("falls back to the status code for validation lists and non-JSON bodies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: "x" }] }), { status: 422 })))
    await expect(api.stats("t")).rejects.toThrow("HTTP 422")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502 })))
    const err = await api.stats("t").catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe("HTTP 502")
  })

  it("builds file urls with both params encoded", () => {
    expect(fileUrl("a&b", "x/y z.png")).toBe("/api/file?company=a%26b&id=x%2Fy%20z.png")
  })
})
