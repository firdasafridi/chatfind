"""Rule-based query understanding (ID/EN): time range, file-type hint, channel hint.

Deterministic on purpose: cheap, testable, and easy to explain in the UI.
"""
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

TYPE_WORDS = {
    "image": ["foto", "gambar", "photo", "picture", "pic", "image", "screenshot", "tangkapan layar", "struk", "nota", "receipt", "bukti transfer"],
    "document": ["dokumen", "document", "pdf", "file", "berkas", "surat", "kontrak", "invoice", "faktur", "sop", "laporan", "report", "katalog", "catalog", "form", "formulir", "notulen", "menu"],
}
# words that only say what type of file is wanted; we strip them from the semantic query
TYPE_STOPWORDS = {"foto", "gambar", "photo", "picture", "pic", "image", "dokumen", "document", "pdf", "file", "berkas"}

CHANNEL_WORDS = {
    "whatsapp": ["whatsapp", "wa"],
    "instagram": ["instagram", "ig"],
    "email": ["email", "e-mail", "surel"],
    "crm": ["crm"],
}

FILLER = r"\b(yang|dari|di|ke|tentang|about|from|the|a|an|of|cari|carikan|tolong|please|find|show|me|saya|aku|dikirim|kirim|sent|pernah)\b"


@dataclass
class ParsedQuery:
    raw: str
    text: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    date_label: str | None = None
    type_hint: str | None = None
    channel: str | None = None
    translated: str | None = None
    notes: list[str] = field(default_factory=list)


def _range(now, label):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if label == "today":
        return today, None
    if label == "yesterday":
        return today - timedelta(days=1), today
    if label == "this_week":
        return today - timedelta(days=today.weekday()), None
    if label == "last_week":
        return today - timedelta(days=7), None
    if label == "this_month":
        return today.replace(day=1), None
    if label == "last_month":
        return today - timedelta(days=31), None
    raise ValueError(label)


DATE_PATTERNS = [
    (r"\bhari ini\b|\btoday\b", "today", "Hari ini"),
    (r"\bkemarin\b|\byesterday\b", "yesterday", "Kemarin"),
    (r"\bminggu ini\b|\bpekan ini\b|\bthis week\b", "this_week", "Minggu ini"),
    (r"\bminggu lalu\b|\bpekan lalu\b|\bseminggu (terakhir|lalu)\b|\blast week\b|\bpast week\b", "last_week", "7 hari terakhir"),
    (r"\bbulan ini\b|\bthis month\b", "this_month", "Bulan ini"),
    (r"\bbulan lalu\b|\bsebulan (terakhir|lalu)\b|\blast month\b|\bpast month\b", "last_month", "31 hari terakhir"),
]
N_DAYS = r"\b(\d{1,3})\s*(hari|days?)\s*(terakhir|lalu|ago|last)?\b|\b(last|past)\s*(\d{1,3})\s*days?\b"


def parse(q: str, now: datetime | None = None) -> ParsedQuery:
    fixed = os.getenv("QUERY_NOW")  # pin "now" for reproducible evals, e.g. 2026-09-29T18:00:00+07:00
    now = now or (datetime.fromisoformat(fixed) if fixed else datetime.now(WIB))
    raw = q.strip()
    s = " " + raw.lower() + " "
    pq = ParsedQuery(raw=raw, text=raw)

    m = re.search(N_DAYS, s)
    if m:
        n = int(m.group(1) or m.group(5))
        pq.date_from = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=n)
        pq.date_label = f"{n} hari terakhir"
        s = s.replace(m.group(0), " ")
    else:
        for pat, key, label in DATE_PATTERNS:
            m = re.search(pat, s)
            if m:
                pq.date_from, pq.date_to = _range(now, key)
                pq.date_label = label
                s = s.replace(m.group(0), " ")
                break

    for ch, words in CHANNEL_WORDS.items():
        for w in words:
            # needs a preposition: "via wa", "dari email". Bare "kontrak whatsapp api" is content, not a filter.
            m = re.search(rf"\b(via|lewat|di|dari|from|on|through|by) {re.escape(w)}\b", s)
            if m:
                pq.channel = ch
                s = s.replace(m.group(0), " ")
                break
        if pq.channel:
            break

    for t, words in TYPE_WORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", s) for w in words):
            pq.type_hint = t
            break
    for w in TYPE_STOPWORDS:
        s = re.sub(rf"\b{w}\b", " ", s)

    s = re.sub(FILLER, " ", s)
    text = " ".join(s.split())
    pq.text = text if len(text) >= 2 else raw
    return pq
