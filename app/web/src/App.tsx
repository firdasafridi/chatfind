import { ChevronDown, Search } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { PreviewDialog } from "@/components/preview-dialog"
import { ResultCard } from "@/components/result-card"
import { Understood } from "@/components/understood"
import { UploadPanel } from "@/components/upload-panel"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, fileUrl, type Channel, type MimeGroup, type SearchResponse, type SearchResult, type Stats, type Tenant } from "@/lib/api"
import { CHANNEL_LABEL, splitResults } from "@/lib/format"

const EXAMPLES = [
  "struk bensin pertamax",
  "foto anjing lari di rumput",
  "invoice refund minggu lalu",
  "berapa hari batas retur barang",
  "bukti transfer via wa kemarin",
  "woman playing a harp",
]

const ALL = "all"
const CHANNELS = Object.entries(CHANNEL_LABEL) as [Channel, string][]
const CHANNEL_ITEMS = [{ value: ALL, label: "Semua kanal" }, ...CHANNELS.map(([value, label]) => ({ value, label }))]

type Phase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; data: SearchResponse }
  | { kind: "error"; message: string }

export default function App() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [company, setCompany] = useState<string | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [query, setQuery] = useState("")
  const [type, setType] = useState<MimeGroup | null>(null)
  const [channel, setChannel] = useState<Channel | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: "idle" })
  const [preview, setPreview] = useState<SearchResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const lastQuery = useRef("")
  const requestId = useRef(0)

  useEffect(() => {
    api
      .tenants()
      .then((ts) => {
        setTenants(ts)
        setCompany(ts[0]?.id ?? null)
      })
      .catch(() => setPhase({ kind: "error", message: "Server tidak bisa dihubungi." }))
  }, [])

  const loadStats = useCallback(() => {
    if (company) api.stats(company).then(setStats).catch(() => setStats(null))
  }, [company])

  useEffect(loadStats, [loadStats])

  const run = useCallback(
    async (q: string, opts: { type?: MimeGroup | null; channel?: Channel | null } = {}) => {
      const text = q.trim()
      if (!text || !company) {
        inputRef.current?.focus()
        return
      }
      lastQuery.current = text
      setQuery(text)
      setPhase({ kind: "loading" })
      // Filters change faster than search returns; only the newest request may update the page.
      const id = ++requestId.current
      try {
        const data = await api.search(company, {
          query: text,
          type: opts.type !== undefined ? opts.type : type,
          channel: opts.channel !== undefined ? opts.channel : channel,
          limit: 24,
        })
        if (id === requestId.current) setPhase({ kind: "done", data })
      } catch (e) {
        if (id === requestId.current) setPhase({ kind: "error", message: (e as Error).message })
      }
    },
    [company, type, channel],
  )

  // "/" focuses search, like most search-first tools.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const switchCompany = (id: string) => {
    setCompany(id)
    setPhase({ kind: "idle" })
    setPreview(null)
    lastQuery.current = ""
  }

  const rerunWith = (opts: { type?: MimeGroup | null; channel?: Channel | null }) => {
    if (lastQuery.current) void run(lastQuery.current, opts)
  }

  const onDelete = async (r: SearchResult) => {
    if (!company) return
    try {
      await api.remove(company, r.file_id)
      toast.success(`${r.name} dihapus dari pencarian`)
      loadStats()
      if (lastQuery.current) void run(lastQuery.current)
    } catch (e) {
      toast.error((e as Error).message)
      throw e
    }
  }

  const tenantItems = tenants.map((t) => ({ value: t.id, label: t.name }))

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <a href="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="grid size-6 place-items-center rounded bg-foreground text-[13px] text-background" aria-hidden>
              c
            </span>
            chatfind
          </a>
          {company && (
            <Select items={tenantItems} value={company} onValueChange={(v) => v && switchCompany(v as string)}>
              <SelectTrigger data-testid="company-select" aria-label="Pilih perusahaan" size="sm" className="max-w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {tenantItems.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1fr_280px]">
        <div className="min-w-0 space-y-6">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Cari file dengan menjelaskan isinya</h1>
            <p className="max-w-prose text-sm text-muted-foreground">
              Tidak perlu ingat nama file. Tulis seperti bercerita ke rekan kerja: apa yang ada di gambar, isi dokumen,
              kapan dikirim, atau lewat kanal apa.
            </p>
          </div>

          <form
            role="search"
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void run(query)
            }}
          >
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                ref={inputRef}
                data-testid="search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                maxLength={300}
                autoFocus
                autoComplete="off"
                placeholder="Contoh: struk bensin minggu lalu"
                aria-label="Kata kunci pencarian"
                className="h-11 pl-9 pr-10 text-base"
              />
              <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border px-1.5 font-mono text-[11px] text-muted-foreground sm:block">
                /
              </kbd>
            </div>
            <Button type="submit" data-testid="search-button" className="h-11 px-5">
              Cari
            </Button>
          </form>

          <div className="flex flex-wrap items-center gap-3">
            <ToggleGroup
              variant="outline"
              size="sm"
              aria-label="Jenis file"
              value={[type ?? ALL]}
              onValueChange={(v: string[]) => {
                const next = (v[0] && v[0] !== ALL ? v[0] : null) as MimeGroup | null
                setType(next)
                rerunWith({ type: next })
              }}
            >
              <ToggleGroupItem value={ALL} data-testid="type-all">
                Semua
              </ToggleGroupItem>
              <ToggleGroupItem value="image" data-testid="type-image">
                Foto & gambar
              </ToggleGroupItem>
              <ToggleGroupItem value="document" data-testid="type-document">
                Dokumen
              </ToggleGroupItem>
            </ToggleGroup>

            <Select
              items={CHANNEL_ITEMS}
              value={channel ?? ALL}
              onValueChange={(v) => {
                const next = (v && v !== ALL ? v : null) as Channel | null
                setChannel(next)
                rerunWith({ channel: next })
              }}
            >
              <SelectTrigger data-testid="channel-select" aria-label="Kanal" size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CHANNEL_ITEMS.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div data-testid="examples" className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
            <span className="text-muted-foreground">Coba:</span>
            {EXAMPLES.map((x) => (
              <button
                key={x}
                type="button"
                data-testid="example-chip"
                onClick={() => void run(x)}
                className="text-foreground/80 underline decoration-foreground/20 underline-offset-4 hover:text-foreground hover:decoration-foreground"
              >
                {x}
              </button>
            ))}
          </div>

          <Results phase={phase} company={company} onOpen={setPreview} />
        </div>

        <aside className="space-y-8 lg:border-l lg:pl-8">
          <section className="space-y-3">
            <h2 className="text-sm font-medium">Isi pustaka</h2>
            <dl data-testid="stats" className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Foto</dt>
                <dd data-testid="stat-image" className="text-2xl font-semibold tabular-nums">
                  {stats?.image ?? "–"}
                </dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Dokumen</dt>
                <dd data-testid="stat-document" className="text-2xl font-semibold tabular-nums">
                  {stats?.document ?? "–"}
                </dd>
              </div>
            </dl>
          </section>

          {company && <UploadPanel company={company} onUploaded={loadStats} />}

          <section className="space-y-2 text-sm">
            <h2 className="font-medium">Cara kerjanya</h2>
            <p className="text-muted-foreground">
              Setiap file dibaca: teks dokumen, tulisan di dalam foto seperti struk, dan isi visual gambar. Pertanyaan
              Anda dipahami dalam bahasa Indonesia atau Inggris, termasuk "minggu lalu" atau "via WA".
            </p>
            <p className="text-muted-foreground">Hanya file milik perusahaan Anda yang bisa muncul.</p>
          </section>
        </aside>
      </main>

      <PreviewDialog
        result={preview}
        url={preview && company ? fileUrl(company, preview.file_id) : ""}
        onClose={() => setPreview(null)}
        onDelete={onDelete}
      />
      <Toaster position="bottom-right" />
    </div>
  )
}

function Results({
  phase,
  company,
  onOpen,
}: {
  phase: Phase
  company: string | null
  onOpen: (r: SearchResult) => void
}) {
  if (phase.kind === "idle") return null

  if (phase.kind === "loading") {
    return (
      <div data-testid="results" aria-busy="true" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="aspect-[4/5] rounded-lg" />
        ))}
      </div>
    )
  }

  if (phase.kind === "error") {
    return (
      <div data-testid="error" role="alert" className="rounded-lg border border-destructive/40 p-4 text-sm">
        <p className="font-medium">Pencarian gagal.</p>
        <p className="text-muted-foreground">{phase.message}</p>
      </div>
    )
  }

  const { data } = phase
  const { confident, shown, rest } = splitResults(data.results)
  const q = data.understood.search_text
  const url = (id: string) => (company ? fileUrl(company, id) : "")

  return (
    <div className="space-y-4">
      <Understood u={data.understood} />
      <p data-testid="status" aria-live="polite" className="text-xs text-muted-foreground">
        {confident
          ? `${shown.length} hasil cocok${rest.length ? `, ${rest.length} kemungkinan lain` : ""} · ${data.took_ms} ms`
          : `${shown.length} hasil terdekat, keyakinan rendah · ${data.took_ms} ms`}
      </p>

      {!confident && (
        <div data-testid="empty" className="rounded-lg bg-muted/60 p-4 text-sm">
          <p className="font-medium">Belum ada yang benar-benar cocok.</p>
          <p className="text-muted-foreground">
            {shown.length > 0 && "Ini hasil terdekat, urut dari yang paling mungkin. "}
            Coba jelaskan dengan kata lain, sebut isi gambarnya (warna, benda, orang), atau hapus filter waktu dan kanal.
          </p>
        </div>
      )}

      <div data-testid="results" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((r, i) => (
          <ResultCard key={r.file_id} result={r} rank={i + 1} query={q} thumbUrl={url(r.file_id)} onOpen={onOpen} />
        ))}
      </div>

      {rest.length > 0 && (
        <Collapsible data-testid="weak-results">
          <CollapsibleTrigger className="group flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDown className="size-4 transition-transform group-data-[panel-open]:rotate-180" aria-hidden />
            Hasil lain yang mungkin relevan ({rest.length})
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-4">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {rest.map((r, i) => (
                <ResultCard
                  key={r.file_id}
                  result={r}
                  rank={shown.length + i + 1}
                  query={q}
                  thumbUrl={url(r.file_id)}
                  onOpen={onOpen}
                />
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
