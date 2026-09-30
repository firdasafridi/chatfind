import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import App from "./App"
import type { SearchResponse, SearchResult } from "./lib/api"

const hit = (over: Partial<SearchResult>): SearchResult => ({
  file_id: "photos/a.jpg",
  name: "a.jpg",
  mime_group: "image",
  channel: "whatsapp",
  created_at: new Date().toISOString(),
  score: 0.8,
  confidence: "strong",
  match: "visual",
  reason: "Isi gambar cocok dengan deskripsi Anda",
  page: null,
  snippet: null,
  ...over,
})

const response = (results: SearchResult[], understood: Partial<SearchResponse["understood"]> = {}): SearchResponse => ({
  query: "q",
  took_ms: 42,
  understood: { search_text: "struk bensin", translated: null, date: null, type_hint: null, channel: null, date_from: null, ...understood },
  results,
})

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>
let handler: Handler
let calls: { url: string; init: RequestInit }[]
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

function backend(search: () => SearchResponse | Response, extra: Handler = () => json({})): Handler {
  return (url, init) => {
    if (url === "/api/tenants") return json([{ id: "tenant_a", name: "Toko A" }, { id: "tenant_b", name: "Toko B" }])
    if (url === "/api/stats") return json({ image: 12, document: 3 })
    if (url === "/api/search") {
      const r = search()
      return r instanceof Response ? r : json(r)
    }
    return extra(url, init)
  }
}

beforeEach(() => {
  calls = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init })
      return handler(url, init)
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

const searchBodies = () => calls.filter((c) => c.url === "/api/search").map((c) => JSON.parse(c.init.body as string))
const tenantOf = (c: { init: RequestInit }) => new Headers(c.init.headers).get("X-Company-Id")

async function boot() {
  render(<App />)
  await waitFor(() => expect(screen.getByTestId("stat-image")).toHaveTextContent("12"))
}

async function search(text = "struk bensin") {
  const input = screen.getByTestId("search-input")
  await userEvent.clear(input)
  await userEvent.type(input, `${text}{Enter}`)
}

describe("App", () => {
  it("loads tenants and library stats", async () => {
    handler = backend(() => response([]))
    await boot()
    expect(screen.getByTestId("stat-document")).toHaveTextContent("3")
    expect(tenantOf(calls.find((c) => c.url === "/api/stats")!)).toBe("tenant_a")
  })

  it("shows what the parser understood and confident results", async () => {
    handler = backend(() =>
      response(
        [
          hit({ file_id: "receipts/s.png", name: "s.png", match: "ocr", snippet: "SPBU struk bensin", confidence: "strong" }),
          hit({ file_id: "docs/k.pdf", name: "k.pdf", mime_group: "document", match: "text", page: 2, confidence: "good" }),
          hit({ file_id: "photos/w.jpg", name: "w.jpg", confidence: "weak" }),
        ],
        { translated: "gasoline receipt", date: "7 hari terakhir", type_hint: "image", channel: "whatsapp" },
      ),
    )
    await boot()
    await search()

    expect(await screen.findAllByTestId("result-card")).toHaveLength(2)
    expect(screen.getByTestId("u-translated")).toHaveTextContent("gasoline receipt")
    expect(screen.getByTestId("u-date")).toHaveTextContent("7 hari terakhir")
    expect(screen.getByTestId("u-type")).toHaveTextContent("foto & gambar")
    expect(screen.getByTestId("u-channel")).toHaveTextContent("WhatsApp")
    expect(screen.getByTestId("status")).toHaveTextContent("2 hasil cocok, 1 kemungkinan lain · 42 ms")
    expect(screen.getByText("PDF · hal. 2")).toBeInTheDocument()
    expect(screen.getByTestId("snippet").querySelectorAll("mark")).toHaveLength(2)
    expect(screen.queryByTestId("empty")).not.toBeInTheDocument()

    await userEvent.click(screen.getByText(/Hasil lain yang mungkin relevan/))
    await waitFor(() => expect(screen.getAllByTestId("result-card")).toHaveLength(3))
  })

  it("is honest when nothing is confident", async () => {
    handler = backend(() => response([hit({ confidence: "weak", mime_group: "document", name: "x.txt", match: "text" })]))
    await boot()
    await search("zzqx")
    expect(await screen.findByTestId("empty")).toHaveTextContent("Belum ada yang benar-benar cocok")
    expect(screen.getByTestId("status")).toHaveTextContent("1 hasil terdekat, keyakinan rendah")
  })

  it("explains an empty result set", async () => {
    handler = backend(() => response([]))
    await boot()
    await search("zzqx")
    expect(await screen.findByTestId("empty")).not.toHaveTextContent("Ini hasil terdekat")
  })

  it("shows the server's error", async () => {
    handler = backend(() => json({ detail: "unknown company" }, 401))
    await boot()
    await search()
    expect(await screen.findByTestId("error")).toHaveTextContent("unknown company")
  })

  it("reports an unreachable server on start", async () => {
    handler = () => {
      throw new TypeError("Failed to fetch")
    }
    render(<App />)
    await search()
    expect(await screen.findByTestId("error")).toHaveTextContent("Server tidak bisa dihubungi")
    expect(screen.getByTestId("stat-image")).toHaveTextContent("–")
  })

  it("ignores empty queries and focuses the input", async () => {
    handler = backend(() => response([]))
    await boot()
    await userEvent.click(screen.getByTestId("search-button"))
    expect(searchBodies()).toHaveLength(0)
    expect(screen.getByTestId("search-input")).toHaveFocus()
  })

  it("runs an example query", async () => {
    handler = backend(() => response([hit({})]))
    await boot()
    await userEvent.click(screen.getAllByTestId("example-chip")[0])
    await screen.findByTestId("result-card")
    expect(searchBodies()[0]).toMatchObject({ query: "struk bensin pertamax", limit: 24 })
    expect(screen.getByTestId("search-input")).toHaveValue("struk bensin pertamax")
  })

  it("re-runs the last search when the type filter changes, but not before any search", async () => {
    handler = backend(() => response([hit({})]))
    await boot()
    await userEvent.click(screen.getByTestId("type-document"))
    expect(searchBodies()).toHaveLength(0)

    await search()
    await userEvent.click(screen.getByTestId("type-image"))
    await waitFor(() => expect(searchBodies().at(-1)).toMatchObject({ type: "image" }))
    await userEvent.click(screen.getByTestId("type-all"))
    await waitFor(() => expect(searchBodies().at(-1)).toMatchObject({ type: null }))
  })

  it("filters by channel", async () => {
    handler = backend(() => response([hit({})]))
    await boot()
    await search()
    await userEvent.click(screen.getByTestId("channel-select"))
    await userEvent.click(await screen.findByRole("option", { name: "Instagram" }))
    await waitFor(() => expect(searchBodies().at(-1)).toMatchObject({ channel: "instagram" }))
    await userEvent.click(screen.getByTestId("channel-select"))
    await userEvent.click(await screen.findByRole("option", { name: "Semua kanal" }))
    await waitFor(() => expect(searchBodies().at(-1)).toMatchObject({ channel: null }))
  })

  it("switches tenant, clears results and scopes later calls", async () => {
    handler = backend(() => response([hit({})]))
    await boot()
    await search()
    await screen.findByTestId("result-card")

    await userEvent.click(screen.getByTestId("company-select"))
    await userEvent.click(await screen.findByRole("option", { name: "Toko B" }))
    await waitFor(() => expect(screen.queryByTestId("result-card")).not.toBeInTheDocument())
    await waitFor(() => expect(tenantOf(calls.filter((c) => c.url === "/api/stats").at(-1)!)).toBe("tenant_b"))
  })

  it("keeps only the newest response when searches overlap", async () => {
    let release!: () => void
    const slow = new Promise<void>((r) => (release = r))
    let n = 0
    handler = backend(() => response([]))
    const base = handler
    handler = async (url, init) => {
      if (url === "/api/search" && n++ === 0) {
        await slow
        return json(response([hit({ name: "old.jpg" })]))
      }
      if (url === "/api/search") return json(response([hit({ name: "new.jpg" })]))
      return base(url, init)
    }
    await boot()
    await search("first")
    await search("second")
    await screen.findByText("new.jpg")
    await act(async () => release())
    expect(screen.queryByText("old.jpg")).not.toBeInTheDocument()
  })

  it("focuses search on '/' unless typing in an input", async () => {
    handler = backend(() => response([]))
    await boot()
    const input = screen.getByTestId("search-input")
    input.blur()
    fireEvent.keyDown(window, { key: "/" })
    expect(input).toHaveFocus()
    fireEvent.keyDown(window, { key: "a" })
    expect(input).toHaveFocus()
  })

  it("previews an image, and deletes after confirming", async () => {
    let results = [hit({ file_id: "photos/a.jpg", name: "a.jpg" })]
    handler = backend(
      () => response(results),
      (url, init) => {
        if (url.startsWith("/api/file") && init.method === "DELETE") {
          results = []
          return json({ deleted: "photos/a.jpg" })
        }
        return json({})
      },
    )
    await boot()
    await search()
    await userEvent.click(await screen.findByTestId("result-card"))

    const dialog = await screen.findByTestId("preview")
    expect(within(dialog).getByRole("img", { name: "a.jpg" })).toHaveAttribute("src", "/api/file?company=tenant_a&id=photos%2Fa.jpg")

    await userEvent.click(within(dialog).getByTestId("preview-delete"))
    await userEvent.click(within(dialog).getByText("Batal"))
    await userEvent.click(within(dialog).getByTestId("preview-delete"))
    await userEvent.click(within(dialog).getByTestId("preview-delete-confirm"))

    await waitFor(() => expect(screen.queryByTestId("preview")).not.toBeInTheDocument())
    expect(calls.some((c) => c.url === "/api/file?id=photos%2Fa.jpg" && tenantOf(c) === "tenant_a")).toBe(true)
    await waitFor(() => expect(screen.queryByTestId("result-card")).not.toBeInTheDocument())
  })

  it("keeps the preview open when delete fails", async () => {
    handler = backend(
      () => response([hit({})]),
      () => json({ detail: "not found" }, 404),
    )
    await boot()
    await search()
    await userEvent.click(await screen.findByTestId("result-card"))
    const dialog = await screen.findByTestId("preview")
    await userEvent.click(within(dialog).getByTestId("preview-delete"))
    await userEvent.click(within(dialog).getByTestId("preview-delete-confirm"))
    expect(await screen.findByText("not found")).toBeInTheDocument()
    expect(screen.getByTestId("preview")).toBeInTheDocument()
  })

  it("previews a PDF at the matched page, and plain text inline", async () => {
    handler = backend(() =>
      response([
        hit({ file_id: "docs/k.pdf", name: "k.pdf", mime_group: "document", match: "text", page: 3, confidence: "strong" }),
        hit({ file_id: "docs/n.txt", name: "n.txt", mime_group: "document", match: "text", snippet: "catatan rapat", confidence: "good" }),
        hit({ file_id: "docs/e.txt", name: "e.txt", mime_group: "document", match: "text", snippet: null, confidence: "good" }),
      ]),
    )
    await boot()
    await search()
    const cards = await screen.findAllByTestId("result-card")

    await userEvent.click(cards[0])
    const frame = (await screen.findByTestId("preview")).querySelector("iframe")
    expect(frame).toHaveAttribute("src", expect.stringMatching(/#page=3$/))
    await userEvent.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByTestId("preview")).not.toBeInTheDocument())

    await userEvent.click(cards[1])
    expect(within(await screen.findByTestId("preview")).getByText("catatan rapat").tagName).toBe("PRE")
    await userEvent.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByTestId("preview")).not.toBeInTheDocument())

    await userEvent.click(cards[2])
    expect(await screen.findByTestId("preview")).toBeInTheDocument()
  })

  it("uploads files one at a time and refreshes stats", async () => {
    const outcomes = [
      json({ file_id: "uploads/a.jpg", status: "indexed", points: 2, mime_group: "image", ocr: true }),
      json({ file_id: "uploads/b.jpg", status: "duplicate", duplicate_of: "photos/b.jpg" }),
      json({ detail: "File lebih dari 20 MB" }, 413),
    ]
    handler = backend(() => response([]), (url) => (url === "/api/upload" ? outcomes.shift()! : json({})))
    await boot()
    const statsBefore = calls.filter((c) => c.url === "/api/stats").length

    const files = ["a.jpg", "b.jpg", "c.pdf"].map((n) => new File(["x"], n))
    await userEvent.upload(screen.getByTestId("file-input"), files)

    const list = await screen.findByTestId("upload-list")
    await waitFor(() => expect(within(list).getByText("File lebih dari 20 MB")).toBeInTheDocument())
    expect(within(list).getByText("Siap dicari, teks di gambar terbaca")).toBeInTheDocument()
    expect(within(list).getByText("Sudah ada sebagai b.jpg")).toBeInTheDocument()
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/stats").length).toBeGreaterThan(statsBefore))
  })

  it("accepts dropped files and shows drag state", async () => {
    handler = backend(() => response([]), () => json({ file_id: "uploads/a.pdf", status: "skipped", reason: "no text layer" }))
    await boot()
    const zone = screen.getByTestId("dropzone")
    fireEvent.dragEnter(zone)
    expect(zone.className).toContain("border-foreground")
    fireEvent.dragOver(zone)
    fireEvent.dragLeave(zone)
    expect(zone.className).not.toContain("bg-muted")
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "a.pdf")] } })
    expect(await screen.findByText("Dilewati: no text layer")).toBeInTheDocument()
  })

  it("ignores an empty file picker change", async () => {
    handler = backend(() => response([]))
    await boot()
    fireEvent.change(screen.getByTestId("file-input"), { target: { files: [] } })
    expect(screen.queryByTestId("upload-list")).not.toBeInTheDocument()
  })
})
