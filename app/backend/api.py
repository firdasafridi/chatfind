"""FastAPI service: search, upload, preview, delete. Serves the built web UI (web/dist) at /.

Tenant = X-Company-Id header. DEMO ONLY: in prod the company comes from the authenticated
session (SSO/JWT) and is never trusted from the client.
"""
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config as C
from .engine import Engine

engine: Engine | None = None
_engine_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app):
    if C.WARMUP:  # background thread: /api/health answers while models load
        threading.Thread(target=lambda: eng().warmup(), daemon=True).start()
    yield


app = FastAPI(title="chatfind", lifespan=lifespan)


def eng() -> Engine:
    global engine
    # The warmup thread and the first request can race; embedded Qdrant allows one client per directory.
    with _engine_lock:
        if engine is None:
            engine = Engine()
    return engine


def tenant(x_company_id: str | None) -> str:
    if x_company_id not in C.TENANTS:
        raise HTTPException(401, "unknown company")
    return x_company_id


class SearchReq(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    type: str | None = Field(default=None, pattern="^(image|document)$")
    channel: str | None = Field(default=None, pattern="^(whatsapp|instagram|email|crm|upload)$")
    limit: int = Field(default=12, ge=1, le=50)


def confidence(score):
    if score >= C.STRONG_CONFIDENT:
        return "strong"
    if score >= C.MIN_CONFIDENT:
        return "good"
    return "weak"


def reason(h):
    return {"visual": "Isi gambar cocok dengan deskripsi Anda",
            "ocr": "Teks di dalam gambar cocok",
            "text": f"Isi dokumen cocok (halaman {h.page})"}[h.kind]


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/tenants")
def tenants():
    return [{"id": k, "name": v} for k, v in C.TENANTS.items()]


@app.get("/api/stats")
def stats(x_company_id: str | None = Header(default=None)):
    return eng().stats(tenant(x_company_id))


@app.get("/api/files")
def files(x_company_id: str | None = Header(default=None)):
    return eng().list_files(tenant(x_company_id))


@app.post("/api/search")
def search(req: SearchReq, x_company_id: str | None = Header(default=None)):
    cid = tenant(x_company_id)
    t0 = time.perf_counter()
    pq, hits, files = eng().search(cid, req.query, k=req.limit, type_filter=req.type, channel=req.channel)
    understood = {"search_text": pq.text, "translated": pq.translated, "date": pq.date_label, "type_hint": pq.type_hint, "channel": pq.channel,
                  "date_from": pq.date_from.isoformat() if pq.date_from else None}
    results = []
    for h in hits:
        f = files[h.file_id]
        results.append({
            "file_id": h.file_id, "name": f["name"], "mime_group": f["mime_group"], "channel": f["channel"],
            "created_at": f["created_at"], "score": round(h.score, 4), "confidence": confidence(h.conf),
            "match": h.kind, "reason": reason(h), "page": h.page,
            "snippet": (h.snippet[:280] if h.snippet else None),
        })
    return {"query": req.query, "understood": understood, "took_ms": int((time.perf_counter() - t0) * 1000),
            "results": results}


SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), x_company_id: str | None = Header(default=None)):
    cid = tenant(x_company_id)
    name = SAFE.sub("_", Path(file.filename or "upload").name)[:120]
    ext = Path(name).suffix.lower()
    if ext not in C.IMG_EXT | C.DOC_EXT:
        raise HTTPException(415, f"Tipe file {ext or '?'} belum didukung. Gunakan JPG, PNG, WEBP, PDF, atau TXT.")
    data = await file.read(C.MAX_UPLOAD_BYTES + 1)
    if len(data) > C.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File lebih dari 20 MB")
    dest = C.DATA_DIR / cid / "uploads" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        return eng().ingest(cid, dest, f"uploads/{name}", channel="upload")
    except Exception as e:  # corrupt files etc.
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"File tidak dapat diproses: {type(e).__name__}")


def _resolve(cid, file_id):
    f = eng().file(cid, file_id)  # tenant-scoped lookup: other company's file_id -> 404
    if not f:
        raise HTTPException(404, "not found")
    p = Path(f["path"]).resolve()
    root = (C.DATA_DIR / cid).resolve()
    if root not in p.parents:  # path traversal guard
        raise HTTPException(404, "not found")
    return p


@app.get("/api/file")
def get_file(id: str, company: str):
    # <img>/<a> tags can't send headers, so the demo passes company as a query param.
    # Prod: signed short-lived URL from object storage after authz.
    return FileResponse(_resolve(tenant(company), id))


@app.delete("/api/file")
def delete_file(id: str, x_company_id: str | None = Header(default=None)):
    cid = tenant(x_company_id)
    _resolve(cid, id)
    eng().delete(cid, id)
    return {"deleted": id}


# check_dir=False: the API (and its tests) must start before `pnpm build` has produced web/dist.
app.mount("/", StaticFiles(directory=C.APP_DIR / "web" / "dist", html=True, check_dir=False), name="ui")
