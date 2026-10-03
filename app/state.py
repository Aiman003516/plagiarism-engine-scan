"""Shared singletons, data paths, model caches and scan-history persistence."""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
from datetime import datetime

from plagiarism_engine import VectorStore, SystemDBStore


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Lazy model preloading
# ---------------------------------------------------------------------------

_models_ready = False
_model_lock = threading.Lock()


def _preload_models():
    """Background preload of ML models so first scan is fast."""
    global _models_ready
    try:
        from plagiarism_engine.vector_store import model_pool
        model_pool.get_model("code")
        model_pool.get_model("bge_m3")
        model_pool.get_model("minilm")
        _models_ready = True
    except Exception as e:
        print(f"Failed to preload models: {e}")

# ---------------------------------------------------------------------------
# Singletons (cached)
# ---------------------------------------------------------------------------
_db: Optional[SystemDBStore] = None
_vstore: Optional[VectorStore] = None

DATA_DIR = Path(os.environ.get("PLAGIARISM_DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Deep AI scan model cache (loaded once per server lifetime)
_MODELS_DIR = os.environ.get("MODELS_DIR", str(PROJECT_ROOT / "models"))
_deep_scan_models: Dict[str, Any] = {}
_deep_scan_model_lock = threading.Lock()


def _get_deep_scan_model(model_name: str):
    """Load (and cache) a SentenceTransformer model by name. Thread-safe."""
    from sentence_transformers import SentenceTransformer

    model_key = model_name
    if model_key in _deep_scan_models:
        return _deep_scan_models[model_key]

    with _deep_scan_model_lock:
        # Double-check under lock in case another thread raced us.
        if model_key in _deep_scan_models:
            return _deep_scan_models[model_key]

        model_path = os.path.join(_MODELS_DIR, model_name)
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model path not found: {model_path}")

        model = SentenceTransformer(model_path)
        # UniXcoder / BGE-M3 positional embeddings are bounded; cap the
        # token window to avoid "index out of bounds" on long files.
        try:
            model.max_seq_length = 512
        except Exception:
            pass
        _deep_scan_models[model_key] = model
        return model


def get_db() -> SystemDBStore:
    global _db
    if _db is None:
        _db = SystemDBStore(sqlite_db_path=str(DATA_DIR / "system_db.sqlite"))
    return _db


def get_vstore() -> VectorStore:
    global _vstore
    if _vstore is None:
        _vstore = VectorStore(
            index_dir=str(DATA_DIR / "faiss_index"),
            mapping_path=str(DATA_DIR / "faiss_mapping.json"),
        )
    return _vstore


# ---------------------------------------------------------------------------
# In-memory scan history (persisted to a JSON file for simplicity)
# ---------------------------------------------------------------------------
HISTORY_FILE = DATA_DIR / "scan_history.json"


def _load_history() -> List[Dict[str, Any]]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            backup_path = HISTORY_FILE.with_suffix(f".corrupt.{int(datetime.now().timestamp())}.json")
            HISTORY_FILE.rename(backup_path)
            print(f"Failed to load history, backed up corrupted file to {backup_path}: {e}")
            return []
    return []


def _save_history(history: List[Dict[str, Any]]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
