import type { Channel, Confidence, MimeGroup, SearchResult } from "./api"

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  strong: "Sangat cocok",
  good: "Cocok",
  weak: "Mungkin",
}

export const CHANNEL_LABEL: Record<Channel, string> = {
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  email: "Email",
  crm: "CRM",
  upload: "Diunggah",
}

export const TYPE_LABEL: Record<MimeGroup, string> = {
  image: "foto & gambar",
  document: "dokumen",
}

export const channelLabel = (c: string) => CHANNEL_LABEL[c as Channel] ?? c

/** "hari ini · 30 Sep 2026", "kemarin · …", "3 hari lalu · …". Counts calendar days, not 24h periods. */
export function relDate(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ""
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((day(now) - day(d)) / 864e5)
  const abs = d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })
  if (days <= 0) return `hari ini · ${abs}`
  if (days === 1) return `kemarin · ${abs}`
  return `${days} hari lalu · ${abs}`
}

export interface Segment {
  text: string
  hit: boolean
}

/** Split text into plain and matched parts so React can render <mark> without innerHTML. */
export function highlight(text: string, query: string): Segment[] {
  const terms = [...new Set(query.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((t) => t.length > 2))]
  if (!text) return []
  if (!terms.length) return [{ text, hit: false }]
  const pattern = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "giu")
  return text
    .split(pattern)
    .filter(Boolean)
    .map((part) => ({ text: part, hit: terms.includes(part.toLowerCase()) }))
}

export const extension = (name: string) => {
  const i = name.lastIndexOf(".")
  return i > 0 ? name.slice(i + 1).toUpperCase() : "FILE"
}

/**
 * Ranking is always shown; the badge carries the uncertainty. When nothing is confident we still show
 * the best few (the right answer is often #1 with a modest score) under an honest notice.
 */
export function splitResults(results: SearchResult[]) {
  const confident = results.filter((r) => r.confidence !== "weak")
  const shown = confident.length ? confident : results.slice(0, 6)
  const rest = results.slice(shown.length).filter((r) => r.confidence === "weak")
  return { confident: confident.length > 0, shown, rest }
}

export function uploadMessage(
  r: { status: "indexed"; ocr: boolean } | { status: "duplicate"; duplicate_of: string } | { status: "skipped"; reason: string },
): string {
  if (r.status === "indexed") return r.ocr ? "Siap dicari, teks di gambar terbaca" : "Siap dicari"
  if (r.status === "duplicate") return `Sudah ada sebagai ${r.duplicate_of.split("/").pop()}`
  return `Dilewati: ${r.reason}`
}
