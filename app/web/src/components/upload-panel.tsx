import { Upload } from "lucide-react"
import { useRef, useState } from "react"

import { api } from "@/lib/api"
import { uploadMessage } from "@/lib/format"
import { cn } from "@/lib/utils"

type Item = { id: number; name: string; state: "busy" | "ok" | "info" | "error"; message: string }

const ACCEPT = ".jpg,.jpeg,.png,.webp,.pdf,.txt"
let seq = 0

export function UploadPanel({ company, onUploaded }: { company: string; onUploaded: () => void }) {
  const [items, setItems] = useState<Item[]>([])
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const update = (id: number, patch: Partial<Item>) =>
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x)))

  async function send(files: FileList | File[]) {
    // One at a time: ingest is synchronous on the server and runs the models per file.
    for (const f of Array.from(files)) {
      const id = ++seq
      const item: Item = { id, name: f.name, state: "busy", message: "Memproses…" }
      setItems((xs) => [item, ...xs].slice(0, 8))
      try {
        const r = await api.upload(company, f)
        update(id, { state: r.status === "indexed" ? "ok" : "info", message: uploadMessage(r) })
      } catch (e) {
        update(id, { state: "error", message: (e as Error).message })
      }
    }
    onUploaded()
  }

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium">Tambahkan file</h2>
      <label
        data-testid="dropzone"
        onDragEnter={(e) => (e.preventDefault(), setOver(true))}
        onDragOver={(e) => (e.preventDefault(), setOver(true))}
        onDragLeave={(e) => (e.preventDefault(), setOver(false))}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          void send(e.dataTransfer.files)
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed px-4 py-6 text-center text-sm transition-colors hover:border-foreground/40",
          over && "border-foreground bg-muted",
        )}
      >
        <Upload className="size-5 text-muted-foreground" aria-hidden />
        <span>
          Tarik file ke sini, atau <span className="underline underline-offset-4">pilih file</span>
        </span>
        <span className="text-xs text-muted-foreground">
          JPG, PNG, WEBP, PDF, TXT. <span className="whitespace-nowrap">Maks. 20 MB</span>
        </span>
        <input
          ref={input}
          data-testid="file-input"
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) void send(e.target.files)
            e.target.value = ""
          }}
        />
      </label>

      {items.length > 0 && (
        <ul data-testid="upload-list" className="space-y-1.5 text-xs">
          {items.map((it) => (
            <li key={it.id} className="flex items-start justify-between gap-3">
              <span className="truncate">{it.name}</span>
              <span
                className={cn(
                  "shrink-0 text-right",
                  it.state === "ok" && "text-emerald-700 dark:text-emerald-400",
                  it.state === "error" && "text-destructive",
                  (it.state === "busy" || it.state === "info") && "text-muted-foreground",
                )}
              >
                {it.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
