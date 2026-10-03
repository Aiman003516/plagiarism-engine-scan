"""PgVector storage implementation."""

from typing import List, Dict, Any, Tuple
import json

from plagiarism_engine.db import store


class PgVectorStore:
    def __init__(self):
        self.store = store
        
    def store_embedding(self, file_id: str, embedding: List[float]) -> None:
        """UPDATE the embedding column in project_files"""
        if self.store.mode != "postgresql":
            return
            
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            # In pgvector, we can pass a list of floats as a string or array depending on the adapter.
            # Using JSON string representation '[0.1, 0.2, ...]' is standard for pgvector text input
            embedding_str = json.dumps(embedding)
            cur.execute(
                "UPDATE project_files SET embedding = %s WHERE id = %s;",
                (embedding_str, file_id)
            )
            conn.commit()
        finally:
            conn.close()

    def search_similar(self, query_vector: List[float], top_k: int, exclude_project_id: str = None) -> List[Tuple[Dict[str, Any], float]]:
        """Search similar vectors using <=> cosine distance operator."""
        if self.store.mode != "postgresql":
            return []
            
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            query_vector_str = json.dumps(query_vector)
            
            if exclude_project_id:
                cur.execute(
                    """
                    SELECT id, project_id, relative_path, file_type, 
                           1 - (embedding <=> %s) AS similarity 
                    FROM project_files 
                    WHERE embedding IS NOT NULL 
                      AND project_id != %s
                    ORDER BY embedding <=> %s 
                    LIMIT %s;
                    """,
                    (query_vector_str, exclude_project_id, query_vector_str, top_k)
                )
            else:
                cur.execute(
                    """
                    SELECT id, project_id, relative_path, file_type, 
                           1 - (embedding <=> %s) AS similarity 
                    FROM project_files 
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s 
                    LIMIT %s;
                    """,
                    (query_vector_str, query_vector_str, top_k)
                )
                
            rows = cur.fetchall()
            results = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    meta = {
                        "file_id": r['id'],
                        "project_id": r['project_id'],
                        "relative_path": r['relative_path'],
                        "file_type": r['file_type']
                    }
                    similarity = float(r['similarity'])
                else:
                    meta = {
                        "file_id": r[0],
                        "project_id": r[1],
                        "relative_path": r[2],
                        "file_type": r[3]
                    }
                    similarity = float(r[4])
                results.append((meta, similarity))
            return results
        finally:
            conn.close()

    def delete_project_embeddings(self, project_id: str) -> None:
        """SET embedding = NULL for all files in project"""
        if self.store.mode != "postgresql":
            return
            
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE project_files SET embedding = NULL WHERE project_id = %s;",
                (project_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def count_embeddings(self) -> int:
        """COUNT(*) WHERE embedding IS NOT NULL"""
        if self.store.mode != "postgresql":
            return 0
            
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM project_files WHERE embedding IS NOT NULL;")
            row = cur.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def get_all_embeddings(self) -> List[Tuple[str, List[float], Dict[str, Any]]]:
        """Get all embeddings to hydrate FAISS."""
        if self.store.mode != "postgresql":
            return []
            
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, project_id, relative_path, file_type, embedding::text FROM project_files WHERE embedding IS NOT NULL;"
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    meta = {
                        "file_id": r['id'],
                        "project_id": r['project_id'],
                        "relative_path": r['relative_path'],
                        "file_type": r['file_type']
                    }
                    # pgvector returns '[0.1, ...]' string representation when cast to text
                    emb = json.loads(r['embedding'])
                else:
                    meta = {
                        "file_id": r[0],
                        "project_id": r[1],
                        "relative_path": r[2],
                        "file_type": r[3]
                    }
                    emb = json.loads(r[4])
                results.append((meta['file_id'], emb, meta))
            return results
        finally:
            conn.close()
