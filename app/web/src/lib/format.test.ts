import { describe, expect, it } from "vitest"

import type { SearchResult } from "./api"
import { channelLabel, extension, highlight, relDate, splitResults, uploadMessage } from "./format"

const now = new Date(2026, 8, 30, 14, 0)

describe("relDate", () => {
  it("counts calendar days, not 24h periods", () => {
    expect(relDate(new Date(2026, 8, 30, 1, 0).toISOString(), now)).toMatch(/^hari ini · /)
    expect(relDate(new Date(2026, 8, 29, 23, 59).toISOString(), now)).toMatch(/^kemarin · /)
    expect(relDate(new Date(2026, 8, 25, 12, 0).toISOString(), now)).toMatch(/^5 hari lalu · /)
  })

  it("treats future dates as today and bad input as empty", () => {
    expect(relDate(new Date(2026, 9, 2).toISOString(), now)).toMatch(/^hari ini/)
    expect(relDate("not a date", now)).toBe("")
  })

  it("defaults to the current time", () => {
    expect(relDate(new Date().toISOString())).toMatch(/^hari ini/)
  })
})

describe("highlight", () => {
  it("marks query terms of 3+ letters, case-insensitive", () => {
    expect(highlight("Struk bensin Pertamax", "struk pertamax di")).toEqual([
      { text: "Struk", hit: true },
      { text: " bensin ", hit: false },
      { text: "Pertamax", hit: true },
    ])
  })

  it("never turns text into markup", () => {
    const parts = highlight("<img src=x onerror=alert(1)> invoice", "invoice")
    expect(parts[0]).toEqual({ text: "<img src=x onerror=alert(1)> ", hit: false })
    expect(parts[1]).toEqual({ text: "invoice", hit: true })
  })

  it("escapes regex characters in the query", () => {
    expect(highlight("harga (promo) 10.000", "promo) 10.000")).toContainEqual({ text: "promo", hit: true })
  })

  it("handles empty text and queries without usable terms", () => {
    expect(highlight("", "struk")).toEqual([])
    expect(highlight("abc", "di ke")).toEqual([{ text: "abc", hit: false }])
  })
})

describe("small helpers", () => {
  it("labels known channels and passes unknown ones through", () => {
    expect(channelLabel("whatsapp")).toBe("WhatsApp")
    expect(channelLabel("telegram")).toBe("telegram")
  })

  it("reads the extension", () => {
    expect(extension("Kontrak.Final.pdf")).toBe("PDF")
    expect(extension("README")).toBe("FILE")
    expect(extension(".env")).toBe("FILE")
  })

  it("describes every upload outcome", () => {
    expect(uploadMessage({ status: "indexed", ocr: true })).toBe("Siap dicari, teks di gambar terbaca")
    expect(uploadMessage({ status: "indexed", ocr: false })).toBe("Siap dicari")
    expect(uploadMessage({ status: "duplicate", duplicate_of: "photos/a.jpg" })).toBe("Sudah ada sebagai a.jpg")
    expect(uploadMessage({ status: "skipped", reason: "no text layer" })).toBe("Dilewati: no text layer")
  })
})

const hit = (id: string, confidence: SearchResult["confidence"]): SearchResult => ({
  file_id: id,
  name: id,
  mime_group: "image",
  channel: "whatsapp",
  created_at: "2026-09-30T00:00:00Z",
  score: 0.5,
  confidence,
  match: "visual",
  reason: "",
  page: null,
  snippet: null,
})

describe("splitResults", () => {
  it("shows confident hits and folds the weak rest", () => {
    const r = splitResults([hit("a", "strong"), hit("b", "good"), hit("c", "weak")])
    expect(r.confident).toBe(true)
    expect(r.shown.map((x) => x.file_id)).toEqual(["a", "b"])
    expect(r.rest.map((x) => x.file_id)).toEqual(["c"])
  })

  it("still shows the best six when nothing is confident", () => {
    const r = splitResults(Array.from({ length: 9 }, (_, i) => hit(`w${i}`, "weak")))
    expect(r.confident).toBe(false)
    expect(r.shown).toHaveLength(6)
    expect(r.rest).toHaveLength(3)
  })
})
