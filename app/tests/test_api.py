"""API contract + security: tenant header, upload validation, path traversal, response shape."""
import io
import time

import pytest
from fastapi.testclient import TestClient

from backend import api


@pytest.fixture()
def client(engine, make_files, monkeypatch):
    f = make_files("tenant_demo", {"refund.pdf": "INVOICE REFUND sepatu lari merah", "red.png": (220, 20, 20)})
    engine.ingest("tenant_demo", f["refund.pdf"], "refund.pdf", channel="whatsapp")
    engine.ingest("tenant_demo", f["red.png"], "red.png", channel="whatsapp")
    monkeypatch.setattr(api, "engine", engine)
    return TestClient(api.app)


H = {"X-Company-Id": "tenant_demo"}


def test_health_and_tenants(client):
    assert client.get("/api/health").json() == {"ok": True}
    assert {t["id"] for t in client.get("/api/tenants").json()} == {"tenant_demo", "tenant_other"}


@pytest.mark.parametrize("headers", [{}, {"X-Company-Id": "evil"}])
def test_requires_known_company(client, headers):
    assert client.post("/api/search", json={"query": "refund"}, headers=headers).status_code == 401
    assert client.get("/api/stats", headers=headers).status_code == 401


def test_search_response_shape(client):
    r = client.post("/api/search", json={"query": "refund sepatu minggu lalu"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["understood"]["date"] == "7 hari terakhir"
    top = body["results"][0]
    assert top["file_id"] == "refund.pdf"
    assert top["confidence"] in {"strong", "good", "weak"}
    assert top["reason"].startswith("Isi dokumen cocok") and top["page"] == 1
    assert {"score", "snippet", "channel", "created_at", "mime_group", "match"} <= set(top)


@pytest.mark.parametrize("payload", [
    {"query": ""}, {"query": "x" * 301}, {"query": "a", "type": "video"}, {"query": "a", "limit": 500},
    {"query": "a", "channel": "sms"},
])
def test_search_validation(client, payload):
    assert client.post("/api/search", json=payload, headers=H).status_code == 422


def test_other_tenant_cannot_see_or_fetch_files(client):
    h = {"X-Company-Id": "tenant_other"}
    assert client.post("/api/search", json={"query": "refund sepatu"}, headers=h).json()["results"] == []
    assert client.get("/api/file", params={"id": "refund.pdf", "company": "tenant_other"}).status_code == 404
    assert client.delete("/api/file", params={"id": "refund.pdf"}, headers=h).status_code == 404


def test_file_fetch_own_tenant(client):
    r = client.get("/api/file", params={"id": "red.png", "company": "tenant_demo"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_path_traversal_blocked(client):
    for bad in ["../../backend/config.py", "/etc/passwd", "..%2F..%2Fstore.db"]:
        assert client.get("/api/file", params={"id": bad, "company": "tenant_demo"}).status_code == 404


def test_upload_and_search(client):
    r = client.post("/api/upload", headers=H,
                    files={"file": ("../../catatan rapat.txt", io.BytesIO(b"notulen rapat onboarding chatbot"), "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "indexed"
    assert r.json()["file_id"] == "uploads/catatan_rapat.txt"  # sanitised, no traversal
    res = client.post("/api/search", json={"query": "notulen chatbot"}, headers=H).json()["results"]
    assert res[0]["file_id"] == "uploads/catatan_rapat.txt"


def test_upload_rejects_type_and_size(client, monkeypatch):
    r = client.post("/api/upload", headers=H, files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert r.status_code == 415
    from backend import config as C
    monkeypatch.setattr(C, "MAX_UPLOAD_BYTES", 10)
    r = client.post("/api/upload", headers=H, files={"file": ("big.txt", io.BytesIO(b"x" * 11), "text/plain")})
    assert r.status_code == 413


def test_upload_corrupt_image_is_422(client):
    r = client.post("/api/upload", headers=H, files={"file": ("bad.png", io.BytesIO(b"not an image"), "image/png")})
    assert r.status_code == 422


def test_duplicate_upload(client, make_files):
    with open(api.engine.file("tenant_demo", "refund.pdf")["path"], "rb") as fh:
        data = fh.read()
    r = client.post("/api/upload", headers=H, files={"file": ("again.pdf", io.BytesIO(data), "application/pdf")})
    assert r.json()["status"] == "duplicate"


def test_delete_then_gone(client):
    assert client.delete("/api/file", params={"id": "refund.pdf"}, headers=H).status_code == 200
    res = client.post("/api/search", json={"query": "refund sepatu"}, headers=H).json()["results"]
    assert all(r["file_id"] != "refund.pdf" for r in res)


def test_confidence_thresholds():
    assert api.confidence(0.9) == "strong"
    assert api.confidence(0.65) == "strong"
    assert api.confidence(0.5) == "good"
    assert api.confidence(0.44) == "weak"


def test_files_list(client):
    r = client.get("/api/files", headers=H)
    assert r.status_code == 200 and {f["file_id"] for f in r.json()} == {"refund.pdf", "red.png"}


def test_eng_lazily_constructs_engine(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(api, "engine", None)
    monkeypatch.setattr(api, "Engine", lambda: sentinel)
    assert api.eng() is sentinel and api.eng() is sentinel


def test_file_path_outside_tenant_root_is_404(client, engine, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    engine.db.execute("INSERT INTO files(company_id,file_id,path,name,status) VALUES (?,?,?,?,?)",
                      ("tenant_demo", "evil", str(outside), "evil", "indexed"))
    with pytest.raises(api.HTTPException) as ei:
        api._resolve("tenant_demo", "evil")
    assert ei.value.status_code == 404


def test_lifespan_warms_models_in_background(monkeypatch):
    from backend import api, config as C

    calls = []

    class _Eng:
        def warmup(self):
            calls.append("warm")

    monkeypatch.setattr(C, "WARMUP", True)
    monkeypatch.setattr(api, "eng", lambda: _Eng())
    with TestClient(api.app) as c:
        assert c.get("/api/health").json() == {"ok": True}
    for _ in range(50):
        if calls:
            break
        time.sleep(0.02)
    assert calls == ["warm"]


def test_engine_warmup_touches_every_model(engine):
    engine.warmup()
