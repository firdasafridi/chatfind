"""Indexing + retrieval engine.

Storage split (a Qdrant snapshot must contain no document text):
  Qdrant  -> vectors + filter payload only (ids, company_id, mime_group, channel, created_at)
  SQLite  -> chunk text / OCR text (stands in for the encrypted Postgres store), read after tenant check
"""
import hashlib
import math
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import imagehash
import pytesseract
import torch
from PIL import Image, ImageOps
from pypdf import PdfReader
from qdrant_client import QdrantClient, models

from . import config as C
from . import sparse as bm25
from .query import ParsedQuery, parse

MODEL_VER = "v1"
_lock = threading.Lock()


def _device():
    return "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")


def _z(xs):
    """Positive-only distinctiveness of each candidate vs the rest of its modality's candidate list."""
    if len(xs) < 3:
        return [0.0] * len(xs)
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [max(0.0, (x - mu) / sd) for x in xs]


def _sig(x):
    return 1 / (1 + math.exp(-max(-60.0, min(60.0, x))))


def _feat(out):
    # transformers>=5 returns a ModelOutput; <5 returns the projected tensor
    return out if torch.is_tensor(out) else out.pooler_output


class Models:
    def __init__(self):
        self._txt = self._rr = self._sig = self._mt = None
        self._tr_cache = {}

    @property
    def txt(self):
        if self._txt is None:
            if C.TEXT_BACKEND == "bge-m3":
                from FlagEmbedding import BGEM3FlagModel
                self._txt = BGEM3FlagModel(C.TEXT_MODEL, use_fp16=False, devices="cpu")
            else:
                from sentence_transformers import SentenceTransformer
                self._txt = SentenceTransformer(C.TEXT_MODEL, device="cpu")
        return self._txt

    @property
    def reranker(self):
        if self._rr is None:
            if C.TEXT_BACKEND == "bge-m3":
                from FlagEmbedding import FlagReranker
                self._rr = FlagReranker(C.RERANK_MODEL, use_fp16=False, devices="cpu")
            else:
                from sentence_transformers import CrossEncoder
                self._rr = CrossEncoder(C.RERANK_MODEL, device="cpu", max_length=512)
        return self._rr

    @property
    def siglip(self):
        if self._sig is None:
            from transformers import AutoModel, AutoProcessor
            m = AutoModel.from_pretrained(C.IMAGE_MODEL).eval().to(_device())
            self._sig = (m, AutoProcessor.from_pretrained(C.IMAGE_MODEL))
        return self._sig

    # Embeddings
    def text(self, texts, is_query=False):
        if C.TEXT_BACKEND == "bge-m3":
            out = self.txt.encode(texts, return_dense=True, return_sparse=True, max_length=1024)
            sparse = [models.SparseVector(indices=[int(k) for k in w], values=[float(v) for v in w.values()])
                      for w in out["lexical_weights"]]
            return out["dense_vecs"].tolist(), sparse
        prefix = "query: " if is_query else "passage: "  # e5 is trained with these prefixes
        dense = self.txt.encode([prefix + t for t in texts], normalize_embeddings=True, batch_size=32).tolist()
        sparse = [(bm25.query_vector if is_query else bm25.doc_vector)(t) for t in texts]
        return dense, sparse

    @torch.no_grad()
    def image(self, img):
        m, p = self.siglip
        inputs = p(images=[img], return_tensors="pt").to(m.device)
        f = _feat(m.get_image_features(**inputs))
        return torch.nn.functional.normalize(f, dim=-1)[0].cpu().tolist()

    @torch.no_grad()
    def image_query(self, text):
        m, p = self.siglip
        inputs = p(text=[text.lower()], padding="max_length", max_length=64, truncation=True,
                   return_tensors="pt").to(m.device)
        f = _feat(m.get_text_features(**inputs))
        return torch.nn.functional.normalize(f, dim=-1)[0].cpu().tolist()

    @torch.no_grad()
    def translate(self, text):
        """ID->EN for the image tower (SigLIP-base is stronger in English). Returns None if unchanged."""
        if text in self._tr_cache:
            return self._tr_cache[text]
        if self._mt is None:
            from transformers import MarianMTModel, MarianTokenizer
            self._mt = (MarianTokenizer.from_pretrained(C.TRANSLATE_MODEL),
                        MarianMTModel.from_pretrained(C.TRANSLATE_MODEL).eval())
        tok, mt = self._mt
        out = mt.generate(**tok([text], return_tensors="pt", truncation=True, max_length=64),
                          max_new_tokens=48, num_beams=3)
        tr = tok.decode(out[0], skip_special_tokens=True).strip().rstrip(".")
        tr = None if tr.lower() == text.lower() else tr
        if len(self._tr_cache) > 5000:
            self._tr_cache.clear()
        self._tr_cache[text] = tr
        return tr

    def siglip_logit(self, cos):
        """SigLIP is trained with a sigmoid loss -> logit_scale*cos + logit_bias is a calibrated match logit."""
        if not hasattr(self, "_sig_ab"):
            m, _ = self.siglip
            self._sig_ab = (m.logit_scale.exp().item(), m.logit_bias.item())
        a, b = self._sig_ab
        return a * cos + b

    def rerank(self, query, texts):
        if not texts:
            return []
        pairs = [[query, t] for t in texts]
        if C.TEXT_BACKEND == "bge-m3":
            s = self.reranker.compute_score(pairs, normalize=True, max_length=512)
            return s if isinstance(s, list) else [s]
        probs = self.reranker.predict(pairs, batch_size=32, activation_fn=torch.nn.Sigmoid())
        return [float(x) for x in probs]


@dataclass
class Hit:
    file_id: str
    score: float
    kind: str        # visual | text | ocr
    page: int | None
    snippet: str | None
    meta: dict
    conf: float = 0.0  # calibrated match probability BEFORE ranking-only multipliers -> drives the UI badge


class Engine:
    def __init__(self):
        C.STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.q = (QdrantClient(url=C.QDRANT_URL, api_key=C.QDRANT_API_KEY) if C.QDRANT_URL
                  else QdrantClient(path=str(C.STATE_DIR / "qdrant")))
        self.db = sqlite3.connect(C.STATE_DIR / "store.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.m = Models()
        self._init_db()
        self._init_collection()

    # Setup
    def _init_db(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS files(
          company_id TEXT, file_id TEXT, path TEXT, name TEXT, mime_group TEXT, channel TEXT,
          created_at TEXT, sha256 TEXT, phash TEXT, n_points INT, status TEXT, error TEXT,
          PRIMARY KEY(company_id, file_id));
        CREATE TABLE IF NOT EXISTS chunks(
          point_id TEXT PRIMARY KEY, company_id TEXT, file_id TEXT, page INT, kind TEXT, text TEXT);
        CREATE INDEX IF NOT EXISTS ix_chunks_file ON chunks(company_id, file_id);
        CREATE INDEX IF NOT EXISTS ix_files_sha ON files(company_id, sha256);
        """)

    def _init_collection(self):
        if self.q.collection_exists(C.COLLECTION):
            return
        self.q.create_collection(
            C.COLLECTION,
            vectors_config={
                "text": models.VectorParams(size=C.TEXT_DIM, distance=models.Distance.COSINE),
                "image": models.VectorParams(size=C.IMAGE_DIM, distance=models.Distance.COSINE),
            },
            sparse_vectors_config={"text_sparse": models.SparseVectorParams(
                modifier=None if C.TEXT_BACKEND == "bge-m3" else models.Modifier.IDF)},
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)),
        )
        self.q.create_payload_index(C.COLLECTION, "company_id",
                                    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True))
        for f, t in [("file_id", "keyword"), ("mime_group", "keyword"), ("channel", "keyword"), ("created_at", "datetime")]:
            self.q.create_payload_index(C.COLLECTION, f, t)

    def reset(self):
        if self.q.collection_exists(C.COLLECTION):
            self.q.delete_collection(C.COLLECTION)
        self.db.executescript("DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS chunks;")
        self._init_db()
        self._init_collection()

    # Pre-processing
    @staticmethod
    def _chunks(text):
        text = " ".join(text.split())
        if not text:
            return []
        step = C.CHUNK_CHARS - C.CHUNK_OVERLAP
        return [text[i:i + C.CHUNK_CHARS] for i in range(0, len(text), step)]

    @staticmethod
    def _pid(company_id, sha, idx):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{company_id}|{sha}|{idx}|{MODEL_VER}"))

    def ingest(self, company_id: str, path: Path, file_id: str, channel="upload", created_at=None):
        ext = path.suffix.lower()
        if ext not in C.IMG_EXT | C.DOC_EXT:
            raise ValueError(f"unsupported type {ext}")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        with _lock:
            dup = self.db.execute("SELECT file_id FROM files WHERE company_id=? AND sha256=? AND status='indexed'",
                                  (company_id, sha)).fetchone()
            if dup and dup["file_id"] != file_id:
                return {"file_id": file_id, "status": "duplicate", "duplicate_of": dup["file_id"]}
            self.delete(company_id, file_id)
        base = {"company_id": company_id, "file_id": file_id, "channel": channel, "created_at": created_at}
        points, chunks, phash = [], [], None

        if ext in C.IMG_EXT:
            mime = "image"
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # rotate, then drop EXIF (PII)
            img.thumbnail((1024, 1024))
            phash = str(imagehash.phash(img))
            ocr = pytesseract.image_to_string(img, lang="ind+eng").strip()
            has_ocr = len(re.sub(r"\W", "", ocr)) >= C.OCR_MIN_CHARS
            if has_ocr:
                chunks.append((1, "ocr", " ".join(ocr.split())))
            points.append(models.PointStruct(id=self._pid(company_id, sha, 0), vector={"image": self.m.image(img)},
                                             payload=base | {"mime_group": mime, "kind": "visual", "has_ocr": has_ocr}))
        else:
            mime = "document"
            if ext == ".txt":
                chunks = [(1, "text", c) for c in self._chunks(path.read_text(errors="ignore"))]
            else:
                for pno, page in enumerate(PdfReader(path).pages, 1):
                    chunks += [(pno, "text", c) for c in self._chunks(page.extract_text() or "")]
            if not chunks:
                self._save_file(company_id, file_id, path, mime, channel, created_at, sha, phash, 0, "skipped",
                                "no text layer (scanned PDF OCR is v1.1)")
                return {"file_id": file_id, "status": "skipped", "reason": "no text layer"}

        if chunks:
            dense, sparse = self.m.text([c for _, _, c in chunks])
            for i, ((pno, kind, text), d, s) in enumerate(zip(chunks, dense, sparse), start=1):
                pid = self._pid(company_id, sha, i)
                points.append(models.PointStruct(id=pid, vector={"text": d, "text_sparse": s},
                                                 payload=base | {"mime_group": mime, "kind": kind, "page": pno}))
                self.db.execute("INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?,?)",
                                (pid, company_id, file_id, pno, kind, text))
        self.q.upsert(C.COLLECTION, points)
        self._save_file(company_id, file_id, path, mime, channel, created_at, sha, phash, len(points), "indexed", None)
        return {"file_id": file_id, "status": "indexed", "points": len(points), "mime_group": mime,
                "ocr": any(k == "ocr" for _, k, _ in chunks)}

    def _save_file(self, *row):
        self.db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (row[0], row[1], str(row[2]), Path(row[1]).name, *row[3:]))
        self.db.commit()

    def delete(self, company_id, file_id):
        self.q.delete(C.COLLECTION, points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="company_id", match=models.MatchValue(value=company_id)),
            models.FieldCondition(key="file_id", match=models.MatchValue(value=file_id))])))
        self.db.execute("DELETE FROM chunks WHERE company_id=? AND file_id=?", (company_id, file_id))
        self.db.execute("DELETE FROM files WHERE company_id=? AND file_id=?", (company_id, file_id))
        self.db.commit()

    # Retrieval
    def _filter(self, company_id, pq: ParsedQuery, mime=None, extra=None):
        must = [models.FieldCondition(key="company_id", match=models.MatchValue(value=company_id))]
        if mime:
            must.append(models.FieldCondition(key="mime_group", match=models.MatchValue(value=mime)))
        if pq.channel:
            must.append(models.FieldCondition(key="channel", match=models.MatchValue(value=pq.channel)))
        if pq.date_from or pq.date_to:
            must.append(models.FieldCondition(key="created_at", range=models.DatetimeRange(
                gte=pq.date_from, lt=pq.date_to)))
        for k, v in (extra or {}).items():
            if v:
                must.append(models.FieldCondition(key=k, match=models.MatchValue(value=v)))
        return models.Filter(must=must)

    def warmup(self):
        """Load every model once so the first real search is not the slow one."""
        self.m.text(["warmup"], is_query=True)
        self.m.image_query("warmup")
        self.m.rerank("warmup", ["warmup"])

    def search(self, company_id: str, query: str, k=12, type_filter=None, channel=None, use_parser=True, params=None):
        pq, text_c, img_c = self.candidates(company_id, query, type_filter, channel, use_parser)
        hits = self.fuse(pq, text_c, img_c, type_filter, params)[:k]
        files = self._files(company_id, [h.file_id for h in hits])
        return pq, [h for h in hits if h.file_id in files], files

    def candidates(self, company_id: str, query: str, type_filter=None, channel=None, use_parser=True):
        """Retrieve + rerank. Returns raw per-modality evidence so fusion can be tuned offline."""
        pq = parse(query) if use_parser else ParsedQuery(raw=query, text=query)
        if channel:
            pq.channel = channel
        text_q = pq.text
        want_text = type_filter in (None, "document", "image")
        want_img = type_filter in (None, "image")

        # 1) text candidates (docs + OCR): dense + sparse, fused server-side with RRF
        text_hits = []
        if want_text:
            flt = self._filter(company_id, pq, mime=type_filter)
            dense, sparse = self.m.text([text_q], is_query=True)
            text_hits = self.q.query_points(
                C.COLLECTION,
                prefetch=[models.Prefetch(query=dense[0], using="text", limit=C.CANDIDATES, filter=flt),
                          models.Prefetch(query=sparse[0], using="text_sparse", limit=C.CANDIDATES, filter=flt)],
                query=models.FusionQuery(fusion=models.Fusion.RRF), limit=C.CANDIDATES, with_payload=True,
            ).points

        # 2) visual candidates: SigLIP text tower vs image vectors
        img_hits = []
        if want_img:
            qv = self.m.image_query(text_q)
            if C.QUERY_TRANSLATE and hasattr(self.m, "translate"):
                pq.translated = self.m.translate(text_q)
                if pq.translated:
                    w = C.TRANSLATE_WEIGHT
                    tv = self.m.image_query(pq.translated)
                    mix = [(1 - w) * a + w * b for a, b in zip(qv, tv)]
                    n = math.sqrt(sum(x * x for x in mix)) or 1.0
                    qv = [x / n for x in mix]
            img_hits = self.q.query_points(
                C.COLLECTION, query=qv, using="image",
                query_filter=self._filter(company_id, pq, mime="image"), limit=C.CANDIDATES, with_payload=True,
            ).points

        # 3) rerank text candidates with the cross-encoder (text fetched from store, tenant-scoped)
        text_c = []
        if text_hits:
            ids = [str(p.id) for p in text_hits]
            rows = {r["point_id"]: r for r in self.db.execute(
                f"SELECT * FROM chunks WHERE company_id=? AND point_id IN ({','.join('?' * len(ids))})",
                [company_id, *ids])}
            cands = [rows[str(p.id)] for p in text_hits if str(p.id) in rows]
            probs = self.m.rerank(text_q, [r["text"] for r in cands])
            text_c = [(r["file_id"], p, r["kind"], r["page"], r["text"]) for r, p in zip(cands, probs)]
        img_c = [(p.payload["file_id"], p.score, bool(p.payload.get("has_ocr"))) for p in img_hits]
        return pq, text_c, img_c

    def fuse(self, pq, text_c, img_c, type_filter=None, params=None):
        """Put both modalities on one probability scale, keep best evidence per file.

        text:   cross-encoder probability p -> sigmoid(t_temp * logit(p) + t_bias)
        visual: SigLIP logit (scale*cos + bias) -> sigmoid(i_temp * logit + i_bias)
        Params tuned on the golden set with a held-out split (eval/tune.py)."""
        P = {"t_temp": C.TEXT_TEMP, "t_bias": C.TEXT_BIAS, "i_temp": C.IMAGE_TEMP, "i_bias": C.IMAGE_BIAS,
             "ocr_w": C.OCR_WEIGHT, "type_pen": C.TYPE_HINT_PENALTY, "z_w": C.DISTINCT_WEIGHT,
             "vis_ocr_w": C.VISUAL_ON_TEXT_IMAGE_WEIGHT, **(params or {})}
        t_logits = [math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6))) for _, p, *_ in text_c]
        i_logits = [self.m.siglip_logit(cos) for _, cos, _ in img_c]
        tz, iz = _z(t_logits), _z(i_logits)
        scored: dict[str, Hit] = {}
        ocr_best: dict[str, Hit] = {}
        vis_conf: dict[str, float] = {}
        for (fid, p, kind, page, text), lg, z in zip(text_c, t_logits, tz):
            conf = s = _sig(P["t_temp"] * lg + P["t_bias"] + P["z_w"] * z)
            h = Hit(fid, s * (P["ocr_w"] if kind == "ocr" else 1.0), kind, page, text, {}, conf)
            if kind == "ocr" and (fid not in ocr_best or h.score > ocr_best[fid].score):
                ocr_best[fid] = h
            self._keep(scored, h)
        for (fid, cos, has_ocr), lg, z in zip(img_c, i_logits, iz):
            conf = s = _sig(P["i_temp"] * lg + P["i_bias"] + P["z_w"] * z)
            if has_ocr:  # SigLIP 'reads' rendered text; that evidence is already covered by OCR
                s *= P["vis_ocr_w"]
                conf = s
            vis_conf[fid] = max(conf, vis_conf.get(fid, 0.0))
            self._keep(scored, Hit(fid, s, "visual", None, None, {"cosine": round(cos, 4)}, conf))

        # same file hit by OCR text and visually: show the OCR text (it means more to a user)
        # and combine the two independent signals for the badge with noisy-OR
        for fid, ocr_hit in ocr_best.items():
            h = scored[fid]
            if h is not ocr_hit:
                h.kind, h.page, h.snippet = "ocr", ocr_hit.page, ocr_hit.snippet
                h.conf = 1 - (1 - h.conf) * (1 - ocr_hit.conf)
            elif fid in vis_conf:
                h.conf = 1 - (1 - h.conf) * (1 - vis_conf[fid])

        # soft type hint from the query ("foto ..." / "invoice ...")
        if pq.type_hint and not type_filter:
            for h in scored.values():
                if (pq.type_hint == "image") != (h.kind in ("visual", "ocr")):
                    h.score *= P["type_pen"]
        return sorted(scored.values(), key=lambda h: h.score, reverse=True)

    @staticmethod
    def _keep(scored, h):
        cur = scored.get(h.file_id)
        if cur is None or h.score > cur.score:
            scored[h.file_id] = h

    def _files(self, company_id, ids):
        if not ids:
            return {}
        rows = self.db.execute(f"SELECT * FROM files WHERE company_id=? AND file_id IN ({','.join('?' * len(ids))})",
                               [company_id, *ids])
        return {r["file_id"]: dict(r) for r in rows}

    def file(self, company_id, file_id):
        r = self.db.execute("SELECT * FROM files WHERE company_id=? AND file_id=?", (company_id, file_id)).fetchone()
        return dict(r) if r else None

    def stats(self, company_id):
        rows = self.db.execute("SELECT mime_group, status, COUNT(*) n FROM files WHERE company_id=? GROUP BY 1,2",
                               (company_id,)).fetchall()
        out = {"image": 0, "document": 0, "skipped": 0}
        for r in rows:
            out["skipped" if r["status"] != "indexed" else r["mime_group"]] += r["n"]
        out["total"] = out["image"] + out["document"]
        return out

    def list_files(self, company_id, limit=200):
        return [dict(r) for r in self.db.execute(
            "SELECT file_id,name,mime_group,channel,created_at,status FROM files WHERE company_id=? "
            "ORDER BY created_at DESC LIMIT ?", (company_id, limit))]
