"""
FAISS-powered multilingual vector store for the plagiarism engine.

Replaces the previous ChromaDB implementation with two in-process FAISS
indices (one for ``code``, one for ``text``) for higher performance and
full offline stability:

  - Each index is an ``IndexIDMap(IndexFlatIP(dim))``:
      * ``IndexFlatIP`` over L2-normalized embeddings == cosine similarity
      * ``IndexIDMap`` gives stable int64 IDs and supports ``remove_ids``
  - FAISS only accepts 64-bit integer IDs, so a JSON mapping file
    (``data/faiss_mapping.json``) maps those IDs to
    ``{"project_id": str, "file_path": str}`` and vice versa.
  - Indices are persisted with ``faiss.write_index`` next to the mapping
    file and reloaded automatically on startup.
"""

import os
import re
import json
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

MODELS_DIR = Path(os.environ.get('MODELS_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')))

LOCAL_MODEL_PATHS = {
    "code": str(MODELS_DIR / "codebert-base"),
    "bge_m3": str(MODELS_DIR / "bge-m3"),
    "labse": str(MODELS_DIR / "LaBSE"),
    "arabert": str(MODELS_DIR / "arabertv02"),
    "e5_large": str(MODELS_DIR / "multilingual-e5-large"),
    "e5_base": str(MODELS_DIR / "multilingual-e5-base"),
    "paraphrase": str(MODELS_DIR / "paraphrase-multilingual-MiniLM-L12-v2"),
    "minilm": str(MODELS_DIR / "all-MiniLM-L6-v2")
}

def is_arabic_text(text: str) -> bool:
    """Checks if text contains Arabic characters."""
    if not text:
        return False
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]')
    return bool(arabic_pattern.search(text))

class LazyModelPool:
    """
    On-demand Lazy Model Pool.
    Models are only instantiated in RAM when a specific task/domain is encountered.
    """

    def __init__(self):
        self._loaded_models: Dict[str, SentenceTransformer] = {}

    def get_model(self, key: str) -> Optional[SentenceTransformer]:
        """Fetch model by key, loading it lazily if not already in memory."""
        if key in self._loaded_models:
            return self._loaded_models[key]

        target_path = LOCAL_MODEL_PATHS.get(key)
        if not target_path or not Path(target_path).exists():
            fallback_path = str(MODELS_DIR / "all-MiniLM-L6-v2")
            if Path(fallback_path).exists():
                target_path = fallback_path
            else:
                target_path = LOCAL_MODEL_PATHS["minilm"]

        try:
            model_instance = SentenceTransformer(target_path)
            self._loaded_models[key] = model_instance
            return model_instance
        except Exception:
            return None

    def get_model_dimension(self, key: str) -> int:
        """Get the output embedding dimension for a model, loading it if needed."""
        model = self.get_model(key)
        if model:
            try:
                return model.get_sentence_embedding_dimension()
            except Exception:
                pass
        return 384  # Safe default fallback

# Global Singleton Lazy Model Pool
model_pool = LazyModelPool()

# Domains served by the store; each one gets its own isolated FAISS index.
DOMAINS = ("code", "text")

# LazyModelPool key used to embed each domain.
DOMAIN_MODEL_KEYS = {"code": "code", "text": "bge_m3"}

# Default number of cross-project matches returned per file by search_bulk().
DEFAULT_TOP_K = 5


class VectorStore:
    """
    Production FAISS Vector Store with Cosine Similarity (normalized Inner Product).

    Maintains two domain-isolated indices (``code`` and ``text``), each an
    ``IndexIDMap(IndexFlatIP(dim))`` so vectors keep stable int64 IDs and can
    be removed per project via ``remove_ids``. A JSON sidecar file maps every
    int64 ID to ``{"project_id": str, "file_path": str}`` and back.
    """

    def __init__(
        self,
        index_dir: str = "./data/faiss_index",
        mapping_path: str = "./data/faiss_mapping.json",
    ):
        self.index_dir = Path(index_dir)
        self.mapping_path = Path(mapping_path)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._indices: Dict[str, Optional[faiss.Index]] = {d: None for d in DOMAINS}

        # int64 id -> {"project_id", "file_path", "domain"} (+ next_id counter, dims)
        self._mapping: Dict[str, Any] = self._load_mapping()

        # Reload persisted FAISS indices from disk (created lazily otherwise).
        for domain in DOMAINS:
            path = self._index_path(domain)
            if path.exists():
                try:
                    self._indices[domain] = faiss.read_index(str(path))
                except Exception:
                    self._indices[domain] = None

    # ------------------------------------------------------------------
    # Persistence helpers (JSON ID mapping + FAISS index files)
    # ------------------------------------------------------------------
    def _load_mapping(self) -> Dict[str, Any]:
        """Load the JSON mapping file (int64 id <-> project/file metadata)."""
        if self.mapping_path.exists():
            try:
                data = json.loads(self.mapping_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("vectors"), dict):
                    data.setdefault("next_id", 1)
                    data.setdefault("dims", {})
                    return data
            except Exception:
                pass
        return {"next_id": 1, "dims": {}, "vectors": {}}

    def _save_mapping(self) -> None:
        """Atomically persist the JSON mapping file."""
        tmp_path = self.mapping_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self._mapping, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.mapping_path)

    def _index_path(self, domain: str) -> Path:
        return self.index_dir / f"{domain}.index"

    def _persist_index(self, domain: str) -> None:
        """Write a domain's FAISS index to disk (caller holds the lock)."""
        index = self._indices.get(domain)
        if index is not None:
            faiss.write_index(index, str(self._index_path(domain)))

    def _get_index(self, domain: str, dim: Optional[int] = None) -> faiss.Index:
        """
        Return the domain index, creating it lazily as
        ``IndexIDMap(IndexFlatIP(dim))`` (caller holds the lock).
        """
        index = self._indices.get(domain)
        if index is not None:
            return index

        if not dim:
            dim = self._mapping.get("dims", {}).get(domain)
        if not dim:
            dim = model_pool.get_model_dimension(DOMAIN_MODEL_KEYS[domain])

        index = faiss.IndexIDMap(faiss.IndexFlatIP(int(dim)))
        self._indices[domain] = index
        self._mapping.setdefault("dims", {})[domain] = int(index.d)
        return index

    def _next_id(self) -> int:
        """Allocate the next unique int64 ID (caller holds the lock)."""
        new_id = int(self._mapping.get("next_id", 1))
        self._mapping["next_id"] = new_id + 1
        return new_id

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def index_project_files(
        self,
        project_files: List[Dict[str, Any]],
        project_id: str,
        log_callback: Optional[Any] = None,
    ) -> Dict[str, int]:
        """
        Task-Based Dispatching Indexer using FAISS + Batch Processing.

        Routes code files strictly to the CodeBERT model & ``code`` index,
        and text files strictly to the BGE-M3 model & ``text`` index.
        Embeddings are L2-normalized so IndexFlatIP == cosine similarity.
        Every vector gets a unique int64 ID recorded in the JSON mapping.
        """
        batch_size = 32

        code_files: List[Dict[str, Any]] = []
        text_files: List[Dict[str, Any]] = []
        for file_rec in project_files:
            content = file_rec.get('content', '')
            if not content or not content.strip():
                continue
            if file_rec.get('file_type', 'text') == 'code':
                code_files.append(file_rec)
            else:
                text_files.append(file_rec)

        added = {"code": 0, "text": 0}
        if code_files:
            added["code"] = self._encode_and_add(
                code_files, project_id, "code", batch_size, log_callback
            )
        if text_files:
            added["text"] = self._encode_and_add(
                text_files, project_id, "text", batch_size, log_callback
            )

        if log_callback:
            log_callback(
                f"  ✅ [FAISS] Indexed {added['code']} code + {added['text']} text vectors "
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
        """Encode one domain's files in batches and add them to its FAISS index."""
        model = model_pool.get_model(DOMAIN_MODEL_KEYS[domain]) or model_pool.get_model("minilm")
        if model is None:
            if log_callback:
                log_callback(
                    f"  ⚠️ [FAISS] No embedding model available for '{domain}' domain; "
                    f"skipping {len(files)} files."
                )
            return 0

        try:
            dim = int(model.get_sentence_embedding_dimension())
        except Exception:
            dim = model_pool.get_model_dimension(DOMAIN_MODEL_KEYS[domain])

        if log_callback:
            log_callback(
                f"  🤖 [FAISS] Encoding {len(files)} {domain} files "
                f"in batches of {batch_size} (dim={dim})..."
            )

        added = 0
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            texts = [f.get('content', '')[:4000] for f in batch]

            # Heavy work stays OUTSIDE the lock so scans can run concurrently.
            embeddings = model.encode(texts, convert_to_numpy=True, batch_size=batch_size)
            embeddings = np.asarray(embeddings, dtype="float32")
            if embeddings.ndim == 1:
                embeddings = embeddings.reshape(1, -1)

            # L2-normalize so inner product == cosine similarity.
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            embeddings = embeddings / norms

            with self._lock:
                index = self._get_index(domain, dim)
                ids = np.array([self._next_id() for _ in batch], dtype="int64")
                index.add_with_ids(np.ascontiguousarray(embeddings), ids)

                for j, file_rec in enumerate(batch):
                    file_path = file_rec.get('relative_path', file_rec.get('filename', ''))
                    self._mapping["vectors"][str(int(ids[j]))] = {
                        "project_id": project_id,
                        "file_path": file_path,
                        "domain": domain,
                    }
                added += len(batch)

        with self._lock:
            self._save_mapping()
            self._persist_index(domain)
        return added

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------
    def delete_project(self, project_id: str) -> int:
        """
        Remove every vector belonging to ``project_id`` from both FAISS
        indices (via ``remove_ids``) and from the JSON mapping file.
        Returns the number of vectors removed.
        """
        with self._lock:
            ids_by_domain: Dict[str, List[int]] = {d: [] for d in DOMAINS}
            for str_id, meta in list(self._mapping.get("vectors", {}).items()):
                if meta.get("project_id") == project_id:
                    domain = meta.get("domain", "text")
                    ids_by_domain.setdefault(domain, []).append(int(str_id))
                    del self._mapping["vectors"][str_id]

            removed = 0
            for domain, ids in ids_by_domain.items():
                if not ids:
                    continue
                index = self._indices.get(domain)
                if index is not None and index.ntotal > 0:
                    index.remove_ids(np.array(ids, dtype="int64"))
                    self._persist_index(domain)
                removed += len(ids)

            self._save_mapping()
            return removed

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------
    def count_project_vectors(self, project_id: str) -> int:
        """
        Number of vectors currently held in the FAISS indices for
        ``project_id`` (``0`` == the project has never been deep-indexed).

        Read-only and cheap: it scans the in-memory JSON ID mapping, which is
        the authoritative record of which int64 IDs belong to which project.
        Lets callers decide whether embeddings must be generated on demand
        before running ``search_bulk()``.
        """
        with self._lock:
            return sum(
                1
                for meta in self._mapping.get("vectors", {}).values()
                if meta.get("project_id") == project_id
            )

    # ------------------------------------------------------------------
    # Bulk semantic search
    # ------------------------------------------------------------------
    def search_bulk(self, project_id: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
        """
        For every vector of ``project_id``, query the FAISS index for its
        top-k most similar vectors (cosine via inner product), filter out
        matches belonging to the SAME project, and return a clean list of
        cross-project semantic overlaps.
        """
        matches: List[Dict[str, Any]] = []

        with self._lock:
            vectors = self._mapping.get("vectors", {})

            # Bucket this project's own ids per domain.
            own_by_domain: Dict[str, List[int]] = {d: [] for d in DOMAINS}
            for str_id, meta in vectors.items():
                if meta.get("project_id") == project_id:
                    own_by_domain.setdefault(meta.get("domain", "text"), []).append(int(str_id))

            for domain in DOMAINS:
                index = self._indices.get(domain)
                own_ids = own_by_domain.get(domain, [])
                if not own_ids or index is None or index.ntotal == 0:
                    continue

                # Reconstruct this project's stored (already normalized)
                # embeddings and use them as the query batch. IndexIDMap does
                # not implement reconstruct(), so resolve int64 labels to
                # internal offsets via id_map and reconstruct from the
                # underlying IndexFlatIP.
                try:
                    labels = faiss.vector_to_array(index.id_map)
                except Exception:
                    continue
                pos_of_label = {int(lbl): pos for pos, lbl in enumerate(labels)}

                query_ids: List[int] = []
                query_paths: List[str] = []
                query_vecs: List[np.ndarray] = []
                for int_id in own_ids:
                    pos = pos_of_label.get(int_id)
                    if pos is None:
                        continue  # id no longer present in the FAISS index
                    try:
                        vec = index.index.reconstruct_n(pos, 1)[0]
                    except Exception:
                        continue
                    query_ids.append(int_id)
                    query_paths.append(vectors[str(int_id)].get("file_path", ""))
                    query_vecs.append(np.asarray(vec, dtype="float32"))
                if not query_vecs:
                    continue

                queries = np.ascontiguousarray(np.vstack(query_vecs))
                own_id_set = set(query_ids)

                # Fetch extra hits so we still have top_k results after
                # dropping same-project matches.
                k = min(int(index.ntotal), top_k + len(own_id_set))
                scores, result_ids = index.search(queries, k)

                for row, (score_row, id_row) in enumerate(zip(scores, result_ids)):
                    collected = 0
                    for score, hit_id in zip(score_row, id_row):
                        hit_id = int(hit_id)
                        if hit_id == -1 or hit_id in own_id_set:
                            continue  # FAISS padding / same-project match
                        hit_meta = vectors.get(str(hit_id))
                        if not hit_meta or hit_meta.get("project_id") == project_id:
                            continue
                        matches.append({
                            "source_file": query_paths[row],
                            "matched_project_id": hit_meta.get("project_id"),
                            "matched_file": hit_meta.get("file_path"),
                            "similarity": round(float(score), 4),
                            "domain": domain,
                        })
                        collected += 1
                        if collected >= top_k:
                            break

        matches.sort(key=lambda m: m["similarity"], reverse=True)
        return matches


# Backward-compatible alias for legacy imports (previously the ChromaDB class).
MultilingualVectorStore = VectorStore



