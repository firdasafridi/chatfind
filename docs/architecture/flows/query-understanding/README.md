---
topic: query-understanding
status: ready
related: [search]
code:
  - app/backend/query.py
  - app/tests/test_query.py
---

Classification: INTERNAL

# Query understanding

## TL;DR

`parse()` takes a query such as "foto struk bensin via wa minggu lalu" and splits it into what to search for ("struk bensin") and filters: the last 7 days, channel WhatsApp, prefer images. It uses plain rules and regexes, calls no model, and understands both Indonesian and English.

## Entry points

- `app/backend/query.py:70` `parse(q, now=None) -> ParsedQuery`
- Called from `Engine.candidates` (`app/backend/engine.py:316`), unless `use_parser=False` (the eval's `--no-parser` flag).

## Sequence

1. Work out "now". The `now` argument wins, then the `QUERY_NOW` env var (ISO string), then the current time in WIB, UTC+7 (`query.py:71-72`). Evals pin `QUERY_NOW` to the corpus seeding time, so "last week" always means the same week.
2. Match a date phrase. Only the first match counts, and "N days" is checked first.
3. Match a channel. This needs a preposition in front ("via wa", "dari instagram").
4. Match a type hint. Image words are checked before document words.
5. Remove the matched phrases, file-type words and filler words. If fewer than 2 characters are left, fall back to the raw query (`query.py:112`).

## Rules

Dates:

| Phrase (ID / EN) | Range | Label |
|---|---|---|
| `N hari terakhir/lalu`, `N days ago`, `last/past N days` | today − N days onward | "N hari terakhir" |
| hari ini / today | today onward | Hari ini |
| kemarin / yesterday | yesterday 00:00 up to today 00:00 | Kemarin |
| minggu ini, pekan ini / this week | Monday onward | Minggu ini |
| minggu lalu, pekan lalu, seminggu terakhir / last week, past week | today − 7 days onward | 7 hari terakhir |
| bulan ini / this month | 1st of the month onward | Bulan ini |
| bulan lalu, sebulan terakhir / last month, past month | today − 31 days onward | 31 hari terakhir |

"Last week" and "last month" are rolling windows (7 and 31 days), not calendar periods (`query.py:50-55`). This is on purpose, because people say "minggu lalu" loosely. Only "kemarin" has an end date.

Channels (`query.py:19-24`): `whatsapp`/`wa`, `instagram`/`ig`, `email`/`e-mail`/`surel`, `crm`. They count only after `via|lewat|di|dari|from|on|through|by`. Without a preposition, "kontrak whatsapp api" is about WhatsApp rather than from it, so the word stays in the search text.

Type hints (`query.py:12-15`): struk, nota, receipt and bukti transfer count as image, because receipts arrive as photos. Invoice, kontrak and laporan count as document. Plain file words (foto, gambar, pdf, dokumen, file, berkas) are removed from the search text. Content words like "struk" stay.

## Data

```json
{"raw": "foto struk bensin via wa minggu lalu", "text": "struk bensin",
 "date_from": "2026-09-23T00:00:00+07:00", "date_to": null, "date_label": "7 hari terakhir",
 "type_hint": "image", "channel": "whatsapp", "translated": null}
```

`translated` is filled in later by the search path, not by `parse`. `notes` exists on the dataclass but nothing sets it.

## Edge cases covered by tests

`app/tests/test_query.py` covers these cases: "kemarin" has both bounds (23-26); no preposition means no channel (44-46); "wa" inside "jawaban" isn't a channel (49-50); a query that is only "foto" falls back to the raw text (70-72); `QUERY_NOW` pinning (75-77).

## See also

- [search](../search/README.md)
