"""Engine behaviour with fake models: tenant isolation, dedup, delete, filters, storage split."""
from datetime import datetime, timedelta, timezone

from backend import config as C

NOW = datetime(2026, 9, 29, 10, tzinfo=timezone.utc)
ago = lambda d: (NOW - timedelta(days=d)).isoformat()  # noqa: E731


def seed(engine, make_files):
    a = make_files("tenant_demo", {
        "refund.pdf": "INVOICE REFUND sepatu lari merah\nJumlah refund Rp 899.000",
        "policy.txt": "Kebijakan retur barang maksimal tujuh hari",
        "red.png": (220, 20, 20),
        "blue.png": (20, 20, 220),
    })
    b = make_files("tenant_other", {"other_refund.pdf": "INVOICE REFUND sepatu lari merah perusahaan lain"})
    engine.ingest("tenant_demo", a["refund.pdf"], "refund.pdf", channel="whatsapp", created_at=ago(2))
    engine.ingest("tenant_demo", a["policy.txt"], "policy.txt", channel="crm", created_at=ago(40))
    engine.ingest("tenant_demo", a["red.png"], "red.png", channel="whatsapp", created_at=ago(1))
    engine.ingest("tenant_demo", a["blue.png"], "blue.png", channel="instagram", created_at=ago(20))
    engine.ingest("tenant_other", b["other_refund.pdf"], "other_refund.pdf", channel="whatsapp", created_at=ago(2))
    return a, b


def ids(hits):
    return [h.file_id for h in hits]


def test_ingest_counts_and_stats(engine, make_files):
    seed(engine, make_files)
    assert engine.stats("tenant_demo") == {"image": 2, "document": 2, "skipped": 0, "total": 4}
    assert engine.stats("tenant_other")["document"] == 1


def test_document_search_ranks_relevant_first(engine, make_files):
    seed(engine, make_files)
    _, hits, _ = engine.search("tenant_demo", "refund sepatu")
    assert ids(hits)[0] == "refund.pdf"
    assert hits[0].kind == "text" and hits[0].page == 1 and "REFUND" in hits[0].snippet


def test_image_search(engine, make_files):
    seed(engine, make_files)
    _, hits, _ = engine.search("tenant_demo", "red", type_filter="image")
    assert ids(hits)[0] == "red.png" and hits[0].kind == "visual"
    assert all(f.endswith(".png") for f in ids(hits))


def test_tenant_isolation_both_directions(engine, make_files):
    seed(engine, make_files)
    for q in ["refund sepatu lari merah", "red", "retur", "invoice"]:
        _, demo, _ = engine.search("tenant_demo", q)
        _, other, _ = engine.search("tenant_other", q)
        assert "other_refund.pdf" not in ids(demo)
        assert set(ids(other)) <= {"other_refund.pdf"}


def test_unknown_tenant_sees_nothing(engine, make_files):
    seed(engine, make_files)
    _, hits, _ = engine.search("tenant_nobody", "refund")
    assert hits == []


def test_date_filter_from_query(engine, make_files, monkeypatch):
    monkeypatch.setenv("QUERY_NOW", "2026-09-29T17:00:00+07:00")
    seed(engine, make_files)
    pq, hits, _ = engine.search("tenant_demo", "retur barang minggu lalu")
    assert pq.date_label == "7 hari terakhir"
    assert "policy.txt" not in ids(hits)  # 40 days old -> filtered out
    _, hits, _ = engine.search("tenant_demo", "retur barang")
    assert ids(hits)[0] == "policy.txt"


def test_channel_filter(engine, make_files):
    seed(engine, make_files)
    _, hits, _ = engine.search("tenant_demo", "photo", channel="instagram")
    assert ids(hits) == ["blue.png"]


def test_type_hint_penalises_other_modality(engine, make_files):
    seed(engine, make_files)
    _, hits, _ = engine.search("tenant_demo", "foto red refund")
    assert ids(hits)[0] == "red.png"


def test_exact_duplicate_is_not_reindexed(engine, make_files, tmp_path):
    a, _ = seed(engine, make_files)
    copy = tmp_path / "data" / "tenant_demo" / "refund_copy.pdf"
    copy.write_bytes(a["refund.pdf"].read_bytes())
    r = engine.ingest("tenant_demo", copy, "refund_copy.pdf")
    assert r == {"file_id": "refund_copy.pdf", "status": "duplicate", "duplicate_of": "refund.pdf"}
    assert engine.stats("tenant_demo")["document"] == 2


def test_same_file_in_other_tenant_is_not_a_duplicate(engine, make_files):
    a, _ = seed(engine, make_files)
    r = engine.ingest("tenant_other", a["refund.pdf"], "copied.pdf")
    assert r["status"] == "indexed"


def test_reingest_same_id_is_idempotent(engine, make_files):
    a, _ = seed(engine, make_files)
    before = engine.q.count(C.COLLECTION).count
    engine.ingest("tenant_demo", a["refund.pdf"], "refund.pdf", channel="whatsapp", created_at=ago(2))
    assert engine.q.count(C.COLLECTION).count == before


def test_delete_removes_vectors_and_text(engine, make_files):
    seed(engine, make_files)
    engine.delete("tenant_demo", "refund.pdf")
    _, hits, _ = engine.search("tenant_demo", "refund sepatu")
    assert "refund.pdf" not in ids(hits)
    assert engine.db.execute("SELECT COUNT(*) FROM chunks WHERE file_id='refund.pdf'").fetchone()[0] == 0
    assert engine.file("tenant_demo", "refund.pdf") is None


def test_delete_is_tenant_scoped(engine, make_files):
    seed(engine, make_files)
    engine.delete("tenant_other", "refund.pdf")  # same id, wrong tenant -> no effect
    assert engine.file("tenant_demo", "refund.pdf") is not None


def test_qdrant_payload_has_no_text(engine, make_files):
    """Data minimisation: chunk text lives in the store, never in the vector DB payload."""
    seed(engine, make_files)
    pts, _ = engine.q.scroll(C.COLLECTION, limit=100, with_payload=True)
    allowed = {"company_id", "file_id", "channel", "created_at", "mime_group", "kind", "page", "has_ocr"}
    for p in pts:
        assert set(p.payload) <= allowed, p.payload


def test_unsupported_extension_rejected(engine, tmp_path):
    p = tmp_path / "x.exe"
    p.write_bytes(b"MZ")
    try:
        engine.ingest("tenant_demo", p, "x.exe")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_pdf_without_text_is_skipped(engine, tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p))
    c.showPage()
    c.save()
    r = engine.ingest("tenant_demo", p, "blank.pdf")
    assert r["status"] == "skipped"
    assert engine.stats("tenant_demo")["skipped"] == 1


def test_ocr_text_indexed_for_receipt_image(engine, tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (700, 200), "white")
    font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
    ImageDraw.Draw(img).text((20, 60), "STRUK PERTAMAX TOTAL 278000", fill="black", font=font)
    p = tmp_path / "receipt.png"
    img.save(p)
    r = engine.ingest("tenant_demo", p, "receipt.png")
    assert r["ocr"] is True
    _, hits, _ = engine.search("tenant_demo", "pertamax")
    assert hits[0].file_id == "receipt.png" and hits[0].kind == "ocr"


def test_ocr_and_visual_evidence_combined(engine, tmp_path):
    """A receipt matched by both OCR text and visual similarity is explained by its text, and the
    badge confidence is at least as high as either signal alone (noisy-OR)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (700, 200), (220, 20, 20))  # FakeModels maps this colour to "red"
    font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
    ImageDraw.Draw(img).text((20, 60), "STRUK RED PERTAMAX TOTAL 278000", fill="white", font=font)
    p = tmp_path / "red_receipt.png"
    img.save(p)
    engine.ingest("tenant_demo", p, "red_receipt.png")
    pq, text_c, img_c = engine.candidates("tenant_demo", "red pertamax")
    hits = engine.fuse(pq, text_c, img_c)
    h = hits[0]
    assert h.file_id == "red_receipt.png"
    assert h.kind == "ocr" and "PERTAMAX" in h.snippet
    solo = max(x.conf for x in engine.fuse(pq, text_c, []) + engine.fuse(pq, [], img_c))
    assert h.conf >= solo


def test_reset_and_idempotent_collection_init(engine, make_files):
    f = make_files("tenant_demo", {"a.txt": "sepatu lari merah"})
    engine.ingest("tenant_demo", f["a.txt"], "a.txt", channel="whatsapp")
    engine._init_collection()  # already exists -> no-op
    assert engine.list_files("tenant_demo")
    engine.reset()
    assert engine.list_files("tenant_demo") == [] and engine.stats("tenant_demo")["total"] == 0


def test_image_query_mixes_translation(engine, make_files, monkeypatch):
    from backend import config as C
    monkeypatch.setattr(C, "QUERY_TRANSLATE", True)
    f = make_files("tenant_demo", {"red.png": (220, 20, 20), "blue.png": (20, 20, 220)})
    for n in f:
        engine.ingest("tenant_demo", f[n], n, channel="whatsapp")
    seen = []
    engine.m.translate = lambda t: seen.append(t) or "red"
    pq, hits, _ = engine.search("tenant_demo", "foto merah")
    assert seen and pq.translated == "red" and hits[0].file_id == "red.png"
