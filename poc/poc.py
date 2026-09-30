"""Semantic media search, POC.

Usage:
  python poc.py init
  python poc.py ingest <company_id> <path>          # file or folder (jpg/png/webp/pdf/txt)
  python poc.py search <company_id> "<query>"
  python poc.py eval   <company_id> golden.jsonl     # {"query": "...", "expected": ["file.pdf", ...]}

POC scope: images + PDFs/text, hybrid (dense+sparse+image) retrieval, RRF fusion,
cross-encoder rerank, date parsing from query. No real customer data, use synthetic samples only.
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import dateparser.search
import imagehash
import pytesseract
import torch
from FlagEmbedding import BGEM3FlagModel, FlagReranker
from PIL import Image, ImageOps
from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from transformers import AutoModel, AutoProcessor

COLLECTION = "media_poc_v1"
SIGLIP_ID = "google/siglip2-base-patch16-384"  # verify checkpoint name/licence before use
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DOC_EXT = {".pdf", ".txt"}
CHUNK_CHARS, OVERLAP = 1800, 200
OCR_MIN_CHARS = 20

qdrant = QdrantClient(url="http://localhost:6333")
_models = {}


def m(name):
    if name not in _models:
        if name == "bge":
            _models[name] = BGEM3FlagModel("BAAI/bge-m3", use_fp16=torch.cuda.is_available())
        elif name == "rerank":
            _models[name] = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=torch.cuda.is_available())
        elif name == "siglip":
            _models[name] = (AutoModel.from_pretrained(SIGLIP_ID).eval(), AutoProcessor.from_pretrained(SIGLIP_ID))
    return _models[name]


# Embeddings
def embed_text(texts):
    out = m("bge").encode(texts, return_dense=True, return_sparse=True)
    sparse = [
        models.SparseVector(indices=[int(k) for k in w], values=[float(v) for v in w.values()])
        for w in out["lexical_weights"]
    ]
    return out["dense_vecs"].tolist(), sparse


@torch.no_grad()
def embed_image(img):
    model, proc = m("siglip")
    feats = model.get_image_features(**proc(images=[img], return_tensors="pt"))
    return torch.nn.functional.normalize(feats, dim=-1)[0].tolist()


@torch.no_grad()
def embed_image_query(text):
    model, proc = m("siglip")
    inputs = proc(text=[text], padding="max_length", max_length=64, return_tensors="pt")
    feats = model.get_text_features(**inputs)
    return torch.nn.functional.normalize(feats, dim=-1)[0].tolist()


# Pre-processing
def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk(text):
    text = " ".join(text.split())
    return [text[i:i + CHUNK_CHARS] for i in range(0, max(len(text), 1), CHUNK_CHARS - OVERLAP)] if text else []


def prep_image(path):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # applies rotation, drops EXIF
    img.thumbnail((768, 768))
    ocr = pytesseract.image_to_string(img, lang="ind+eng").strip()
    return img, (ocr if len(ocr) >= OCR_MIN_CHARS else ""), str(imagehash.phash(img))


def prep_doc(path):
    if path.suffix == ".txt":
        return [(1, c) for c in chunk(path.read_text(errors="ignore"))]
    out = []
    for pno, page in enumerate(PdfReader(path).pages, 1):
        out += [(pno, c) for c in chunk(page.extract_text() or "")]
    return out  # scanned PDFs (no text layer) -> OCR path in v1.1


# Commands
def init():
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    qdrant.create_collection(
        COLLECTION,
        vectors_config={
            "text": models.VectorParams(size=1024, distance=models.Distance.COSINE),
            "image": models.VectorParams(size=768, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={"text_sparse": models.SparseVectorParams()},
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)
        ),
    )
    qdrant.create_payload_index(
        COLLECTION, "company_id", models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True)
    )
    for f, t in [("file_id", "keyword"), ("mime_group", "keyword"), ("created_at", "datetime")]:
        qdrant.create_payload_index(COLLECTION, f, t)
    print(f"created {COLLECTION}")


def point_id(company_id, digest, idx):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{company_id}|{digest}|{idx}|v1"))


def ingest(company_id, root):
    paths = [p for p in (Path(root).rglob("*") if Path(root).is_dir() else [Path(root)]) if p.is_file()]
    seen = set()
    for p in paths:
        ext = p.suffix.lower()
        if ext not in IMG_EXT | DOC_EXT:
            continue
        digest = sha256(p)
        if digest in seen:  # exact dedup (prod: lookup in index_jobs per tenant)
            print(f"dup  {p.name}")
            continue
        seen.add(digest)
        created = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        base = {"company_id": company_id, "file_id": p.name, "sha256": digest, "created_at": created}
        points = []
        if ext in IMG_EXT:
            img, ocr, phash = prep_image(p)
            vec = {"image": embed_image(img)}
            if ocr:
                dense, sparse = embed_text([ocr])
                vec |= {"text": dense[0], "text_sparse": sparse[0]}
            points.append(models.PointStruct(
                id=point_id(company_id, digest, 0), vector=vec,
                payload=base | {"mime_group": "image", "phash": phash, "has_ocr": bool(ocr)},
            ))
        else:
            chunks = prep_doc(p)
            if not chunks:
                print(f"skip {p.name} (no text layer)")
                continue
            dense, sparse = embed_text([c for _, c in chunks])
            for i, ((pno, c), d, s) in enumerate(zip(chunks, dense, sparse)):
                points.append(models.PointStruct(
                    id=point_id(company_id, digest, i), vector={"text": d, "text_sparse": s},
                    # POC keeps chunk text for rerank; prod hydrates from source after authz
                    payload=base | {"mime_group": "document", "page": pno, "chunk": c},
                ))
        qdrant.upsert(COLLECTION, points)
        print(f"ok   {p.name} -> {len(points)} pts")


def parse_dates(query):
    """'invoice minggu lalu' -> (clean query, created_at filter). Coarse on purpose for POC."""
    found = dateparser.search.search_dates(query, languages=["id", "en"], settings={"PREFER_DATES_FROM": "past"})
    if not found:
        return query, None
    phrase, dt = found[0]
    clean = query.replace(phrase, " ").strip() or query
    return clean, models.FieldCondition(key="created_at", range=models.DatetimeRange(gte=dt))


def search(company_id, query, k=10, show=True):
    q, date_cond = parse_dates(query)
    must = [models.FieldCondition(key="company_id", match=models.MatchValue(value=company_id))]  # server-side, never from client
    if date_cond:
        must.append(date_cond)
    flt = models.Filter(must=must)
    dense, sparse = embed_text([q])
    res = qdrant.query_points(
        COLLECTION,
        prefetch=[
            models.Prefetch(query=dense[0], using="text", limit=50, filter=flt),
            models.Prefetch(query=sparse[0], using="text_sparse", limit=50, filter=flt),
            models.Prefetch(query=embed_image_query(q), using="image", limit=50, filter=flt),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=50,
        with_payload=True,
    ).points
    # rerank text-bearing hits with cross-encoder; keep image-only hits in fused order
    texty = [p for p in res if p.payload.get("chunk")]
    if texty:
        scores = m("rerank").compute_score([[q, p.payload["chunk"]] for p in texty], normalize=True)
        scores = scores if isinstance(scores, list) else [scores]
        for p, s in zip(texty, scores):
            p.score = 0.5 + s  # lift reranked docs into comparable range with RRF scores
    res.sort(key=lambda p: p.score, reverse=True)
    # collapse chunks -> one hit per file
    hits, files = [], set()
    for p in res:
        if p.payload["file_id"] not in files:
            files.add(p.payload["file_id"])
            hits.append(p)
    hits = hits[:k]
    if show:
        print(f"query={q!r} date_filter={bool(date_cond)}")
        for p in hits:
            print(f"{p.score:.3f}  {p.payload['file_id']}  p{p.payload.get('page', '-')}")
    return [p.payload["file_id"] for p in hits]


def evaluate(company_id, golden):
    rows = [json.loads(line) for line in Path(golden).read_text().splitlines() if line.strip()]
    hit10 = mrr = 0.0
    for r in rows:
        got = search(company_id, r["query"], show=False)
        ranks = [got.index(e) + 1 for e in r["expected"] if e in got]
        hit10 += bool(ranks)
        mrr += 1 / min(ranks) if ranks else 0
    print(f"n={len(rows)}  Recall@10={hit10 / len(rows):.3f}  MRR@10={mrr / len(rows):.3f}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    {"init": init, "ingest": ingest, "search": search, "eval": evaluate}.get(cmd, lambda *_: print(__doc__))(*args)
