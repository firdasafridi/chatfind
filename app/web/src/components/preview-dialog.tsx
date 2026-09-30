import { ExternalLink, Trash2 } from "lucide-react"
import { useState } from "react"

import { Button, buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { SearchResult } from "@/lib/api"
import { channelLabel, relDate } from "@/lib/format"

interface Props {
  result: SearchResult | null
  url: string
  onClose: () => void
  onDelete: (r: SearchResult) => Promise<void>
}

export function PreviewDialog({ result: r, url, onClose, onDelete }: Props) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  const close = () => {
    setConfirming(false)
    onClose()
  }

  return (
    <Dialog open={r !== null} onOpenChange={(open) => !open && close()}>
      {r && (
        <DialogContent data-testid="preview" className="max-h-[92vh] gap-0 overflow-hidden p-0 sm:max-w-3xl">
          <DialogHeader className="border-b px-5 py-4 text-left">
            <DialogTitle className="truncate pr-8">{r.name}</DialogTitle>
            <DialogDescription>
              {channelLabel(r.channel)} · {relDate(r.created_at)} · {r.reason}
            </DialogDescription>
          </DialogHeader>

          <div className="flex min-h-64 items-center justify-center bg-muted/50">
            {r.mime_group === "image" ? (
              <img src={url} alt={r.name} className="max-h-[62vh] w-auto object-contain" />
            ) : r.name.toLowerCase().endsWith(".pdf") ? (
              <iframe title={r.name} src={`${url}#page=${r.page ?? 1}`} className="h-[62vh] w-full bg-white" />
            ) : (
              <pre className="max-h-[62vh] w-full overflow-auto whitespace-pre-wrap p-5 text-sm">{r.snippet ?? ""}</pre>
            )}
          </div>

          <DialogFooter className="flex-row items-center justify-between gap-2 border-t px-5 py-3 sm:justify-between">
            <a href={url} target="_blank" rel="noopener" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              <ExternalLink aria-hidden /> Buka file
            </a>
            {confirming ? (
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-muted-foreground sm:inline">Hapus dari indeks pencarian?</span>
                <Button variant="ghost" size="sm" onClick={() => setConfirming(false)} disabled={busy}>
                  Batal
                </Button>
                <Button
                  data-testid="preview-delete-confirm"
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      await onDelete(r)
                      close()
                    } catch {
                      // onDelete already told the user; keep the dialog open so they can retry.
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Ya, hapus
                </Button>
              </div>
            ) : (
              <Button data-testid="preview-delete" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
                <Trash2 aria-hidden /> Hapus dari pencarian
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  )
}
