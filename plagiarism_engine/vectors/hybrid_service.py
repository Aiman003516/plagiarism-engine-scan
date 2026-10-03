import os
import json
import time
import numpy as np
from typing import List, Dict, Any, Tuple
from plagiarism_engine.vectors.pgvector_store import PgVectorStore
from plagiarism_engine.vector_store import VectorStore

pg_store = PgVectorStore()

class HybridVectorService:
    def __init__(self, vstore: VectorStore):
        self.vstore = vstore
        self.backend = os.environ.get("VECTOR_BACKEND", "hybrid")

    def store_embeddings(self, project_id: str, files_embeddings: List[Tuple[str, List[float]]]) -> None:
        """Store embeddings in pgvector. FAISS is handled by vstore."""
        if self.backend in ("hybrid", "pgvector"):
            for file_id, embedding in files_embeddings:
                pg_store.store_embedding(file_id, embedding)

    def search_similar(self, query_vector: List[float], top_k: int, exclude_project_id: str = None) -> List[Tuple[Dict[str, Any], float]]:
        if self.backend == "pgvector":
            return pg_store.search_similar(query_vector, top_k, exclude_project_id)
        # In hybrid, we would use FAISS (which is already done by vstore.search_bulk)
        # If we need single vector search from FAISS, vstore doesn't expose it directly yet.
        return pg_store.search_similar(query_vector, top_k, exclude_project_id)

    def delete_project_embeddings(self, project_id: str) -> None:
        if self.backend in ("hybrid", "pgvector"):
            pg_store.delete_project_embeddings(project_id)
        if self.backend in ("hybrid", "faiss"):
            self.vstore.delete_project(project_id)

    def count_embeddings(self) -> int:
        if self.backend == "pgvector":
            return pg_store.count_embeddings()
        # Not fully accurate for FAISS as it counts vectors per project in mapping
        return len(self.vstore._mapping.get("vectors", {}))

    def hydrate_faiss_from_db(self) -> None:
        if self.backend != "hybrid":
            return
            
        print("[HybridVectorService] Hydrating FAISS from PostgreSQL pgvector...")
        t0 = time.time()
        embeddings = pg_store.get_all_embeddings()
        
        # Reset FAISS mapping and indices
        with self.vstore._lock:
            self.vstore._mapping = {"next_id": 1, "dims": {}, "vectors": {}}
            for domain in self.vstore._indices:
                idx = self.vstore._indices[domain]
                if idx is not None:
                    idx.reset()
            
            # Group embeddings by project and domain
            # We don't have the original text, but we have the vectors
            # Actually, hydrating FAISS requires calling add_with_ids
            for file_id, emb, meta in embeddings:
                domain = "code" if meta.get("file_type") == "code" else "text"
                dim = len(emb)
                index = self.vstore._get_index(domain, dim)
                
                new_id = self.vstore._next_id()
                emb_np = np.array([emb], dtype="float32")
                index.add_with_ids(np.ascontiguousarray(emb_np), np.array([new_id], dtype="int64"))
                
                self.vstore._mapping["vectors"][str(new_id)] = {
                    "project_id": meta.get("project_id"),
                    "file_path": meta.get("relative_path"),
                    "domain": domain,
                }
            self.vstore._save_mapping()
            for domain in self.vstore._indices:
                self.vstore._persist_index(domain)
                
        print(f"[HybridVectorService] Hydrated {len(embeddings)} embeddings into FAISS in {time.time() - t0:.2f}s")
