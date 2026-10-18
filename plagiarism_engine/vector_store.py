"""
Unified Postgres Vector Store for the plagiarism engine.

This module replaces the legacy FAISS in-memory implementation.
It utilizes the LazyModelPool to encode files, and immediately
delegates to PgVectorStore for Binary Quantization and storage
directly into PostgreSQL.
"""

import os
import re
import threading
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from plagiarism_engine.config import load_project_env
from plagiarism_engine.vectors.pgvector_store import PgVectorStore

load_project_env()

MODELS_DIR = Path(os.environ.get('MODELS_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')))

MODEL_SUBDIRS = {
    "code": "codebert-base",
    "unixcoder": "unixcoder-base",
    "bge_m3": "bge-m3",
    "labse": "LaBSE",
    "arabert": "arabertv02",
    "e5_large": "multilingual-e5-large",
    "e5_base": "multilingual-e5-base",
    "paraphrase": "paraphrase-multilingual-MiniLM-L12-v2",
    "minilm": "all-MiniLM-L6-v2",
}

LOCAL_MODEL_PATHS = {k: str(MODELS_DIR / v) for k, v in MODEL_SUBDIRS.items()}

def is_arabic_text(text: str) -> bool:
    """Checks if text contains Arabic characters."""
    if not text:
        return False
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]')
    return bool(arabic_pattern.search(text))

MAX_SEQ_TOKENS = 512


def _cap_max_seq_length(model: SentenceTransformer, ceiling: int = MAX_SEQ_TOKENS) -> None:
    """Clamp model.max_seq_length so inputs never exceed the position-embedding table.

    RoBERTa-family checkpoints (UniXcoder, CodeBERT) expose max_position_embeddings = N + 2
    because two slots are reserved for the padding offset; feeding more than N tokens raises
    'index N+2 is out of bounds'. Some local checkpoints ship without a sentence-transformers
    max_seq_length, so the tokenizer would not truncate at all.
    """
    try:
        limit = ceiling
        cfg = getattr(getattr(model[0], "auto_model", None), "config", None)
        max_pos = getattr(cfg, "max_position_embeddings", None) if cfg is not None else None
        if max_pos:
            model_type = getattr(cfg, "model_type", "") or ""
            usable = int(max_pos) - 2 if model_type in ("roberta", "xlm-roberta", "camembert") else int(max_pos)
            limit = min(limit, usable)
        current = getattr(model, "max_seq_length", None)
        if not current or current > limit:
            model.max_seq_length = limit
    except Exception:
        try:
            model.max_seq_length = ceiling
        except Exception:
            pass


class LazyModelPool:
    """
    On-demand Lazy Model Pool.
    Models are only instantiated in RAM when a specific task/domain is encountered.

    Models are cached by the *resolved model folder name* (e.g. "unixcoder-base"),
    never by the requested key, so a fallback model can never masquerade as the
    model that was asked for.
    """
    def __init__(self):
        self._loaded_models: Dict[str, SentenceTransformer] = {}
        self._lock = threading.Lock()

    def _resolve_model_dir(self, subdir: str) -> Optional[Path]:
        env_dir = os.environ.get("MODELS_DIR")
        candidates = []
        if env_dir:
            candidates.append(Path(env_dir) / subdir)
        candidates.append(MODELS_DIR / subdir)
        candidates.append(Path(r"D:\AI engine\models") / subdir)
        for cand in candidates:
            if cand.exists():
                return cand
        return None

    def expected_model_name(self, key: str) -> Optional[str]:
        """Folder name that get_model_with_name(key) would load, without loading it."""
        subdir = MODEL_SUBDIRS.get(key)
        if subdir and self._resolve_model_dir(subdir) is not None:
            return subdir
        fallback = MODEL_SUBDIRS["minilm"]
        if self._resolve_model_dir(fallback) is not None:
            return fallback
        return None

    def get_model_with_name(self, key: str) -> Tuple[Optional[SentenceTransformer], Optional[str]]:
        """Load the model for `key` and return (model, actually_loaded_folder_name)."""
        subdir = MODEL_SUBDIRS.get(key)
        resolved = self._resolve_model_dir(subdir) if subdir else None
        resolved_name = subdir
        if resolved is None:
            fallback = MODEL_SUBDIRS["minilm"]
            resolved = self._resolve_model_dir(fallback)
            resolved_name = fallback
            warnings.warn(
                f"[LazyModelPool] Model '{subdir or key}' not found; falling back to '{fallback}'. "
                f"Vectors will be tagged '{fallback}' and never compared with other models.",
                stacklevel=2,
            )
        if resolved is None:
            return None, None

        with self._lock:
            if resolved_name in self._loaded_models:
                return self._loaded_models[resolved_name], resolved_name
            try:
                model_instance = SentenceTransformer(str(resolved))
            except Exception:
                return None, None
            _cap_max_seq_length(model_instance)
            self._loaded_models[resolved_name] = model_instance
            return model_instance, resolved_name

    def get_model(self, key: str) -> Optional[SentenceTransformer]:
        """Backward-compatible wrapper around get_model_with_name()."""
        model, _ = self.get_model_with_name(key)
        return model

    def get_model_dimension(self, key: str) -> int:
        model = self.get_model(key)
        if model:
            try:
                return model.get_sentence_embedding_dimension()
            except Exception:
                pass
        return 384  # Safe default fallback

# Global Singleton Lazy Model Pool
model_pool = LazyModelPool()

# Code model chosen from evidence by scripts/calibrate_semantic_models.py (see calibration_results.md):
# unixcoder-base AUC 1.000 / margin +0.228 vs codebert-base AUC 0.970 / margin -0.001.
DOMAIN_MODEL_KEYS = {"code": "unixcoder", "text": "bge_m3"}
DEFAULT_TOP_K = 5


def expected_model_for_domain(domain: str) -> Optional[str]:
    """Model folder name currently expected for a file_type domain ("code" / "text")."""
    key = DOMAIN_MODEL_KEYS.get(domain, DOMAIN_MODEL_KEYS["text"])
    return model_pool.expected_model_name(key)


def _safe_log(cb: Optional[Any], msg: str) -> None:
    if not cb:
        return
    try:
        cb(msg)
    except (UnicodeEncodeError, UnicodeError):
        try:
            # Fall back to ASCII representation if terminal/stdout doesn't support the characters
            cb(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass
    except Exception:
        pass


class VectorStore:
    """
    Unified Postgres Vector Store.
    Proxies encoding tasks to the ML models, and storage/search tasks
    to PgVectorStore which implements Binary Quantization + 2-Step Rescoring.
    Maintains compatibility with legacy app logic (intake/deep scan).
    """

    def __init__(self, db_store: Optional[Any] = None, **kwargs):
        # Ignore legacy kwargs like index_dir or mapping_path
        self.pg_store = PgVectorStore(db_store=db_store)
        self._lock = threading.Lock()

    def index_project_files(
        self,
        project_files: List[Dict[str, Any]],
        project_id: str,
        log_callback: Optional[Any] = None,
    ) -> Dict[str, int]:
        """
        Encode files in batches and store directly in Postgres via PgVectorStore.
        """
        batch_size = 32
        code_files: List[Dict[str, Any]] = []
        text_files: List[Dict[str, Any]] = []
        skipped_ids: List[str] = []
        
        for file_rec in project_files:
            content = file_rec.get('content', '')
            if not content or not content.strip():
                rel = file_rec.get('relative_path', file_rec.get('filename', ''))
                skipped_ids.append(f"{project_id}::{rel}")
                continue
            if file_rec.get('file_type', 'text') == 'code':
                code_files.append(file_rec)
            else:
                text_files.append(file_rec)

        added = {"code": 0, "text": 0}
        if code_files:
            added["code"] = self._encode_and_add(code_files, project_id, "code", batch_size, log_callback)
        if text_files:
            added["text"] = self._encode_and_add(text_files, project_id, "text", batch_size, log_callback)
        if skipped_ids:
            self.pg_store.mark_skipped(skipped_ids)

        if log_callback:
            _safe_log(
                log_callback,
                f"  ✅ [Postgres] Indexed {added['code']} code + {added['text']} text vectors "
                f"for project '{project_id}'."
            )
        return added

    def _encode_and_add(
        self,
        files: List[Dict[str, Any]],
        project_id: str,
        domain: str,
        batch_size: int,
        log_callback: Optional[Any],
    ) -> int:
        model, model_name = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS[domain])
        if model is None:
            if log_callback:
                _safe_log(log_callback, f"  ⚠️ [Postgres] No embedding model available for '{domain}'.")
            return 0

        if log_callback:
            _safe_log(log_callback, f"  🤖 [Postgres] Encoding {len(files)} {domain} files with '{model_name}'...")

        added = 0
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            texts = [f.get('content', '')[:4000] for f in batch]

            embeddings = model.encode(texts, convert_to_numpy=True, batch_size=batch_size)
            embeddings = np.asarray(embeddings, dtype="float32")
            if embeddings.ndim == 1:
                embeddings = embeddings.reshape(1, -1)

            # L2-normalize
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            embeddings = embeddings / norms

            # Option 1: Zero-pad 768-dim (UniXcoder/CodeBERT) / 384-dim (MiniLM) to unified 1024-dim (BGE-M3).
            # Padding preserves cosine and Hamming exactly; rows are only ever compared with rows
            # carrying the same embedding_model tag, so padded spaces never mix.
            cur_dim = embeddings.shape[1]
            if cur_dim < 1024:
                embeddings = np.pad(embeddings, ((0, 0), (0, 1024 - cur_dim)), mode="constant", constant_values=0.0)
            elif cur_dim > 1024:
                embeddings = embeddings[:, :1024]
                norms2 = np.linalg.norm(embeddings, axis=1, keepdims=True)
                norms2[norms2 == 0.0] = 1.0
                embeddings = embeddings / norms2

            batch_data = []
            for j, file_rec in enumerate(batch):
                file_path = file_rec.get('relative_path', file_rec.get('filename', ''))
                file_id = f"{project_id}::{file_path}"
                batch_data.append((file_id, embeddings[j], domain, model_name))
                
            added += self.pg_store.store_embeddings_batch(project_id, batch_data)

        return added

    def delete_project(self, project_id: str) -> int:
        return self.pg_store.delete_project_embeddings(project_id)

    def count_project_vectors(self, project_id: str) -> int:
        return self.pg_store.count_project_vectors(project_id)

    def needs_reindex(self, project_id: str) -> bool:
        """True if the project has no vectors, or any vector was produced by a model other than
        the one currently expected for its file_type (e.g. legacy CodeBERT rows, untagged rows)."""
        expected = {
            "code": expected_model_for_domain("code"),
            "text": expected_model_for_domain("text"),
        }
        return self.pg_store.needs_reindex(project_id, expected)

    def search_bulk(self, project_id: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
        return self.pg_store.search_bulk(project_id, top_k)

    def get_pair_similarity(self, project_a: str, path_a: str, project_b: str, path_b: str, raw: bool = False) -> float:
        return self.pg_store.get_pair_similarity(project_a, path_a, project_b, path_b, raw=raw)


# Backward-compatible alias
MultilingualVectorStore = VectorStore
