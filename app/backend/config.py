import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", APP_DIR / "data"))
STATE_DIR = Path(os.getenv("STATE_DIR", APP_DIR / ".state"))

# QDRANT_URL set -> server/cluster mode (prod). Unset -> embedded local mode (demo, no Docker).
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # from secret manager in prod; never commit
COLLECTION = os.getenv("COLLECTION", "media_v1")

# TEXT_BACKEND:
#   "e5"     -> multilingual-e5-small (dense 384) + BM25 sparse + mMiniLM cross-encoder  (demo default, ~1 GB download)
#   "bge-m3" -> BGE-M3 dense 1024 + learned sparse + bge-reranker-v2-m3                   (prod target, ~4.5 GB)
TEXT_BACKEND = os.getenv("TEXT_BACKEND", "e5")
if TEXT_BACKEND == "bge-m3":
    TEXT_MODEL, TEXT_DIM = "BAAI/bge-m3", 1024
    RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
else:
    TEXT_MODEL, TEXT_DIM = "intfloat/multilingual-e5-small", 384
    RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "google/siglip2-base-patch16-256")
IMAGE_DIM = 768

# Use pre-downloaded weights from ../models/<name> if present (air-gapped or slow networks)
MODELS_DIR = Path(os.getenv("MODELS_DIR", APP_DIR.parent / "models"))


def _local(repo):
    p = MODELS_DIR / repo.split("/")[-1]
    return str(p) if (p / "config.json").exists() else repo


TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "Helsinki-NLP/opus-mt-id-en")  # CC-BY-4.0
QUERY_TRANSLATE = os.getenv("QUERY_TRANSLATE", "1") == "1"
# Load models when the API starts instead of on the first search (which otherwise takes ~10 s).
WARMUP = os.getenv("WARMUP", "1") == "1"
TEXT_MODEL, RERANK_MODEL, IMAGE_MODEL = _local(TEXT_MODEL), _local(RERANK_MODEL), _local(IMAGE_MODEL)
TRANSLATE_MODEL = _local(TRANSLATE_MODEL)

# Demo tenants = companies. In prod this comes from the authenticated session, never the client.
TENANTS = {"tenant_demo": "Toko Lari Cepat (demo)", "tenant_other": "PT Lain Sejahtera (isolation test)"}

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DOC_EXT = {".pdf", ".txt"}

# Retrieval and fusion knobs, tuned on eval/golden.jsonl (see eval/tune.py)
CANDIDATES = 40
CHUNK_CHARS, CHUNK_OVERLAP = 1200, 150
OCR_MIN_CHARS = 20
# Tuned by eval/tune.py with 2-fold cross-validation (both folds agree, see eval/TUNING.md), 2026-09-30
TEXT_TEMP, TEXT_BIAS = 0.5, 0.0
IMAGE_TEMP, IMAGE_BIAS = 0.5, 1.0
OCR_WEIGHT = 0.6           # OCR text is noisier than a document's text layer
TYPE_HINT_PENALTY = 0.2    # score multiplier for the modality the user did NOT ask for
TRANSLATE_WEIGHT = 0.3         # blend of SigLIP(query) and SigLIP(EN translation)
DISTINCT_WEIGHT = 0.25          # boost for a candidate that stands out within its modality
VISUAL_ON_TEXT_IMAGE_WEIGHT = 0.3  # SigLIP 'reading' receipts duplicates OCR evidence
# Badge thresholds from dev-set score distributions (2026-09-30):
#   >= 0.65 -> 0 non-relevant hits above (precision 1.00);  >= 0.45 -> precision 0.81
STRONG_CONFIDENT = 0.65    # "Sangat cocok"
MIN_CONFIDENT = 0.45       # "Cocok"; below -> "Mungkin" (shown collapsed)
