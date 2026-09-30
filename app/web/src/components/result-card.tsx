import { FileText, ImageIcon } from "lucide-react"

import type { SearchResult } from "@/lib/api"
import { CONFIDENCE_LABEL, channelLabel, extension, highlight, relDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const badgeTone = {
  strong: "bg-foreground text-background",
  good: "border border-foreground/30 text-foreground",
  weak: "border border-dashed border-muted-foreground/50 text-muted-foreground",
} as const

interface Props {
  result: SearchResult
  rank: number
  query: string
  thumbUrl: string
  onOpen: (r: SearchResult) => void
}

export function ResultCard({ result: r, rank, query, thumbUrl, onOpen }: Props) {
  const isImage = r.mime_group === "image"
  return (
    <button
      type="button"
      data-testid="result-card"
      data-file-id={r.file_id}
      aria-label={`${r.name}, ${CONFIDENCE_LABEL[r.confidence]}`}
      onClick={() => onOpen(r)}
      className="group flex w-full flex-col overflow-hidden rounded-lg border bg-card text-left transition-colors hover:border-foreground/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted">
        {isImage ? (
          <img
            src={thumbUrl}
            alt=""
            loading="lazy"
            // Receipts and screenshots are read for their text; cropping them hides exactly that.
            className={cn(
              "size-full transition-transform duration-300 group-hover:scale-[1.02]",
              r.match === "ocr" ? "bg-white object-contain p-2" : "object-cover",
            )}
          />
        ) : (
          <div className="flex size-full items-center justify-center">
            {/* A small page instead of a big icon: reads as "document" and hints at the matched page. */}
            <div className="relative flex aspect-[3/4] h-[78%] flex-col gap-1.5 rounded-sm border bg-white p-3 shadow-sm dark:bg-card">
              {[100, 92, 96, 70, 88, 60].map((w, i) => (
                <span key={i} className="h-1 rounded-full bg-muted-foreground/15" style={{ width: `${w}%` }} />
              ))}
              <span className="absolute bottom-2 left-3 font-mono text-[10px] tracking-wider text-muted-foreground">
                {extension(r.name)}
                {r.page ? ` · hal. ${r.page}` : ""}
              </span>
            </div>
          </div>
        )}
        <span className="absolute left-2 top-2 rounded bg-background/90 shadow-sm px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-foreground">
          {rank}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span
            data-testid="confidence"
            className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", badgeTone[r.confidence])}
          >
            {CONFIDENCE_LABEL[r.confidence]}
          </span>
          <span
            className="h-1 w-14 overflow-hidden rounded-full bg-muted"
            title={`Skor peringkat ${Math.round(r.score * 100)}%`}
            aria-hidden
          >
            <span className="block h-full rounded-full bg-foreground/60" style={{ width: `${Math.max(4, Math.round(r.score * 100))}%` }} />
          </span>
        </div>

        <p data-testid="result-name" className="truncate text-sm font-medium" title={r.name}>
          {r.name}
        </p>
        <p data-testid="reason" className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {isImage ? <ImageIcon className="size-3.5 shrink-0" aria-hidden /> : <FileText className="size-3.5 shrink-0" aria-hidden />}
          {r.reason}
        </p>

        {r.snippet && (
          <p data-testid="snippet" className="line-clamp-3 text-xs leading-relaxed text-foreground/80">
            {highlight(r.snippet, query).map((s, i) =>
              s.hit ? (
                <mark key={i} className="rounded-sm bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-400/30">
                  {s.text}
                </mark>
              ) : (
                <span key={i}>{s.text}</span>
              ),
            )}
          </p>
        )}

        <p className="mt-auto flex justify-between gap-2 pt-1 text-[11px] text-muted-foreground">
          <span>{channelLabel(r.channel)}</span>
          <span>{relDate(r.created_at)}</span>
        </p>
      </div>
    </button>
  )
}
