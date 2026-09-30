import type { Understood as U } from "@/lib/api"
import { CHANNEL_LABEL, TYPE_LABEL } from "@/lib/format"

function Token({ testId, label, value, title }: { testId: string; label: string; value: string; title?: string }) {
  return (
    <span data-testid={testId} title={title} className="inline-flex items-baseline gap-1.5 rounded-md bg-muted px-2 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </span>
  )
}

/** Shows how the parser read the query, so people can see why a date or channel filter kicked in. */
export function Understood({ u }: { u: U }) {
  return (
    <div data-testid="understood" className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">Dibaca sebagai</span>
      <Token testId="u-text" label="cari" value={`"${u.search_text}"`} />
      {u.translated && (
        <Token testId="u-translated" label="EN" value={`"${u.translated}"`} title="Terjemahan dipakai untuk mencocokkan isi gambar" />
      )}
      {u.date && <Token testId="u-date" label="waktu" value={u.date} />}
      {u.type_hint && <Token testId="u-type" label="utamakan" value={TYPE_LABEL[u.type_hint]} />}
      {u.channel && <Token testId="u-channel" label="kanal" value={CHANNEL_LABEL[u.channel]} />}
    </div>
  )
}
