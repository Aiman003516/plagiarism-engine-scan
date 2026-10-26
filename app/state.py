"""Shared singletons, data paths, model caches and scan-history persistence."""

import os
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
from datetime import datetime

from plagiarism_engine import VectorStore, SystemDBStore
from plagiarism_engine.config import load_project_env

load_project_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Lazy model preloading
# ---------------------------------------------------------------------------

_models_ready = False
_model_lock = threading.Lock()


def _preload_models():
    """Background preload of ML models actually used (UniXcoder & BGE-M3)."""
    global _models_ready
    try:
        from plagiarism_engine.vector_store import model_pool
        model_pool.get_model("unixcoder")
        model_pool.get_model("bge_m3")
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

        models_dir = os.environ.get("MODELS_DIR", _MODELS_DIR)
        model_path = os.path.join(models_dir, model_name)
        if not Path(model_path).exists():
            alt_path = os.path.join(r"D:\AI engine\models", model_name)
            if Path(alt_path).exists():
                model_path = alt_path
            else:
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
        _vstore = VectorStore()
    return _vstore


# ---------------------------------------------------------------------------
# In-memory scan history (persisted to a JSON file for simplicity)
# ---------------------------------------------------------------------------
HISTORY_FILE = DATA_DIR / "scan_history.json"


_history_lock = threading.Lock()
_history_cache: Optional[List[Dict[str, Any]]] = None
_history_summaries_cache: Optional[List[Dict[str, Any]]] = None
_history_mtime_ns: int = 0


def _load_history() -> List[Dict[str, Any]]:
    global _history_cache, _history_summaries_cache, _history_mtime_ns
    with _history_lock:
        if not HISTORY_FILE.exists():
            _history_cache = []
            _history_summaries_cache = []
            _history_mtime_ns = 0
            return []

        try:
            current_mtime = HISTORY_FILE.stat().st_mtime_ns
            if _history_cache is not None and current_mtime == _history_mtime_ns:
                return _history_cache

            content = HISTORY_FILE.read_text(encoding="utf-8")
            if not content.strip():
                _history_cache = []
                _history_summaries_cache = []
                _history_mtime_ns = current_mtime
                return []

            parsed = json.loads(content)
            _history_cache = parsed
            _history_summaries_cache = None
            _history_mtime_ns = current_mtime
            return parsed
        except Exception as e:
            try:
                backup_path = HISTORY_FILE.with_suffix(f".corrupt.{int(datetime.now().timestamp())}.json")
                HISTORY_FILE.rename(backup_path)
                print(f"Failed to load history, backed up corrupted file to {backup_path}: {e}")
            except Exception:
                pass
            _history_cache = []
            _history_summaries_cache = []
            _history_mtime_ns = 0
            return []


def _load_history_summaries() -> List[Dict[str, Any]]:
    """Return lightweight pre-computed summaries for the history list view."""
    global _history_summaries_cache
    with _history_lock:
        history = _load_history()
        if _history_summaries_cache is not None:
            return _history_summaries_cache

        summaries = []
        for entry in history:
            summaries.append({
                "id": entry.get("id", ""),
                "project_name": entry.get("project_name", ""),
                "scan_type": entry.get("scan_type", ""),
                "overall_similarity": entry.get("overall_similarity", 0),
                "code_similarity": entry.get("code_similarity", 0),
                "text_similarity": entry.get("text_similarity", 0),
                "verdict": entry.get("verdict", "SAFE"),
                "total_files": entry.get("total_files", 0),
                "total_loc": entry.get("total_loc", 0),
                "timestamp": entry.get("timestamp", ""),
            })
        _history_summaries_cache = summaries
        return summaries


def _sanitize_history_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Prune zero-similarity comparisons to prevent multi-megabyte JSON bloat."""
    if not isinstance(entry, dict):
        return entry
    comps = entry.get("comparisons")
    if not isinstance(comps, list) or not comps:
        return entry

    def _score(c):
        s = c.get("similarity", 0) or c.get("overall_similarity", 0) or c.get("composite_score", 0)
        if isinstance(s, str):
            try:
                return float(s.replace("%", "").strip())
            except ValueError:
                return 0.0
        return float(s) if isinstance(s, (int, float)) else 0.0

    meaningful = [c for c in comps if isinstance(c, dict) and _score(c) > 0]
    if len(meaningful) > 100:
        meaningful.sort(key=_score, reverse=True)
        meaningful = meaningful[:100]
    entry["comparisons"] = meaningful
    return entry


def _save_history(history: List[Dict[str, Any]]):
    global _history_cache, _history_summaries_cache, _history_mtime_ns
    with _history_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=DATA_DIR, prefix="history_tmp_", suffix=".json")
        try:
            sanitized = [_sanitize_history_entry(dict(e)) for e in history]
            with open(temp_fd, "w", encoding="utf-8") as f:
                json.dump(sanitized, f, indent=2, default=str)
            os.replace(temp_path, HISTORY_FILE)
            _history_cache = sanitized
            _history_summaries_cache = None
            try:
                _history_mtime_ns = HISTORY_FILE.stat().st_mtime_ns
            except Exception:
                _history_mtime_ns = 0
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise e
