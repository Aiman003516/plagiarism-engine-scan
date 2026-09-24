import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import chromadb
import os
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

class MultilingualVectorStore:
    """
    Production Multilingual Vector Store utilizing ChromaDB with Cosine Distance.
    Features Task-Based Model Dispatching, Domain Isolation, and Multilingual Ensemble Processing.
    """

    def __init__(
        self, 
        collection_name: str = "streamlit_vector_db", 
        persist_directory: Optional[str] = "./chroma_app_db",
        model_name: Optional[str] = None
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory

        # Initialize Persistent ChromaDB Client
        if self.persist_directory:
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            self.client = chromadb.Client()

        # Domain Isolated Collections
        self.code_collection = self.client.get_or_create_collection(
            name="chroma_code_db",
            metadata={"hnsw:space": "cosine"}
        )
        self.docs_collection = self.client.get_or_create_collection(
            name="chroma_multilingual_docs_db",
            metadata={"hnsw:space": "cosine"}
        )

    def generate_code_embedding(self, code_text: str) -> List[float]:
        """Generate vector embedding for code using codebert-base."""
        model = model_pool.get_model("code") or model_pool.get_model("minilm")
        if not model or not code_text or not code_text.strip():
            dim = model_pool.get_model_dimension("code")
            return [0.0] * dim
        embedding = model.encode(code_text[:4000], convert_to_numpy=True)
        return embedding.tolist()

    def generate_multilingual_doc_embedding(self, text: str) -> List[float]:
        """
        Multilingual Ensemble Embedding Pipeline for Mixed Arabic & English Documents.
        Combines bge-m3 / minilm, LaBSE (cross-lingual), and arabertv02 (if Arabic text present).
        """
        if not text or not text.strip():
            dim = model_pool.get_model_dimension("bge_m3")
            return [0.0] * dim

        # Primary Multilingual Model (bge-m3 or minilm)
        primary_model = model_pool.get_model("bge_m3") or model_pool.get_model("minilm")
        emb = primary_model.encode(text[:4000], convert_to_numpy=True)

        # If Arabic text present, combine with LaBSE / AraBERT for cross-lingual alignment
        if is_arabic_text(text):
            labse_model = model_pool.get_model("labse")
            if labse_model:
                labse_emb = labse_model.encode(text[:4000], convert_to_numpy=True)
                if len(emb) == len(labse_emb):
                    emb = ((emb + labse_emb) / 2.0)

        return emb.tolist()

    def upsert_code_file(self, doc_id: str, code_text: str, metadata: Dict[str, Any]) -> None:
        """Upsert source code into isolated Code ChromaDB collection."""
        if not code_text or not code_text.strip():
            return
        embedding = self.generate_code_embedding(code_text)
        meta = metadata or {}
        meta["doc_id"] = doc_id
        meta["domain"] = "code"

        self.code_collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[code_text[:2000]]
        )

    def upsert_doc_file(self, doc_id: str, doc_text: str, metadata: Dict[str, Any]) -> None:
        """Upsert mixed Arabic/English text document into Multilingual Docs ChromaDB collection."""
        if not doc_text or not doc_text.strip():
            return
        embedding = self.generate_multilingual_doc_embedding(doc_text)
        meta = metadata or {}
        meta["doc_id"] = doc_id
        meta["domain"] = "text_multilingual"
        meta["has_arabic"] = is_arabic_text(doc_text)

        self.docs_collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[doc_text[:2000]]
        )

    def index_project_files(
        self, 
        project_files: List[Dict[str, Any]], 
        project_id: str,
        log_callback: Optional[Any] = None
    ) -> None:
        """
        Task-Based Dispatching Indexer using Batch Processing.
        Routes code files strictly to CodeBERT & Code Collection,
        and text files strictly to Multilingual Document Ensemble.
        """
        batch_size = 32
        
        # Split into code and text files
        code_files = [f for f in project_files if f.get('file_type', 'text') == 'code']
        text_files = [f for f in project_files if f.get('file_type', 'text') != 'code']
        
        # Process code files in batches
        code_model = model_pool.get_model("code") or model_pool.get_model("minilm")
        if code_model and code_files:
            if log_callback:
                log_callback(f"  🤖 [Batch] Encoding {len(code_files)} code files...")
            
            for i in range(0, len(code_files), batch_size):
                batch = code_files[i:i+batch_size]
                contents = [f.get('content', '')[:4000] for f in batch]
                embeddings = code_model.encode(contents, batch_size=batch_size, convert_to_numpy=True)
                
                for j, file_rec in enumerate(batch):
                    file_id = f"{project_id}::{file_rec.get('relative_path', file_rec['filename'])}"
                    meta = {
                        "project_id": project_id,
                        "filename": file_rec['filename'],
                        "file_type": 'code',
                        "extension": file_rec.get('extension', ''),
                        "doc_id": file_id,
                        "domain": "code"
                    }
                    self.code_collection.upsert(
                        ids=[file_id],
                        embeddings=[embeddings[j].tolist()],
                        metadatas=[meta],
                        documents=[file_rec.get('content', '')[:2000]]
                    )

        # Process text files in batches
        text_model = model_pool.get_model("bge_m3") or model_pool.get_model("minilm")
        if text_model and text_files:
            if log_callback:
                log_callback(f"  🤖 [Batch] Encoding {len(text_files)} text files...")
                
            for i in range(0, len(text_files), batch_size):
                batch = text_files[i:i+batch_size]
                contents = [f.get('content', '')[:4000] for f in batch]
                embeddings = text_model.encode(contents, batch_size=batch_size, convert_to_numpy=True)
                
                for j, file_rec in enumerate(batch):
                    content = file_rec.get('content', '')
                    has_ar = is_arabic_text(content)
                    
                    # Apply cross-lingual Arabic alignment if needed
                    emb = embeddings[j]
                    if has_ar:
                        labse_model = model_pool.get_model("labse")
                        if labse_model:
                            labse_emb = labse_model.encode(content[:4000], convert_to_numpy=True)
                            if len(emb) == len(labse_emb):
                                emb = ((emb + labse_emb) / 2.0)
                                
                    file_id = f"{project_id}::{file_rec.get('relative_path', file_rec['filename'])}"
                    meta = {
                        "project_id": project_id,
                        "filename": file_rec['filename'],
                        "file_type": 'text',
                        "extension": file_rec.get('extension', ''),
                        "doc_id": file_id,
                        "domain": "text_multilingual",
                        "has_arabic": has_ar
                    }
                    self.docs_collection.upsert(
                        ids=[file_id],
                        embeddings=[emb.tolist()],
                        metadatas=[meta],
                        documents=[content[:2000]]
                    )

    def batch_index_project_files(
        self,
        project_files: List[Dict[str, Any]],
        project_id: str,
        batch_size: int = 64,
        log_callback: Optional[Any] = None
    ) -> None:
        """
        High-performance batch indexer using SentenceTransformer's native batch encoding.
        Encodes documents in batches of `batch_size` (default 64) instead of one at a time,
        significantly reducing per-document overhead for large corpora (100K+ files).
        """
        code_files = []
        text_files = []

        # 1. Separate files by type
        for file_rec in project_files:
            file_type = file_rec.get('file_type', 'text')
            content = file_rec.get('content', '')
            if not content or not content.strip():
                continue
            if file_type == 'code':
                code_files.append(file_rec)
            else:
                text_files.append(file_rec)

        # 2. Batch encode code files
        if code_files:
            code_model = model_pool.get_model("code") or model_pool.get_model("minilm")
            if code_model:
                if log_callback:
                    log_callback(f"  🤖 [Batch] Encoding {len(code_files)} code files in batches of {batch_size}...")

                for i in range(0, len(code_files), batch_size):
                    batch = code_files[i:i + batch_size]
                    texts = [f.get('content', '')[:4000] for f in batch]
                    embeddings = code_model.encode(texts, convert_to_numpy=True, batch_size=batch_size)

                    for j, file_rec in enumerate(batch):
                        file_id = f"{project_id}::{file_rec.get('relative_path', file_rec['filename'])}"
                        meta = {
                            "project_id": project_id,
                            "filename": file_rec['filename'],
                            "file_type": 'code',
                            "extension": file_rec.get('extension', ''),
                            "doc_id": file_id,
                            "domain": "code"
                        }
                        self.code_collection.upsert(
                            ids=[file_id],
                            embeddings=[embeddings[j].tolist()],
                            metadatas=[meta],
                            documents=[file_rec.get('content', '')[:2000]]
                        )

        # 3. Batch encode text files
        if text_files:
            text_model = model_pool.get_model("bge_m3") or model_pool.get_model("minilm")
            if text_model:
                if log_callback:
                    log_callback(f"  🤖 [Batch] Encoding {len(text_files)} text files in batches of {batch_size}...")

                for i in range(0, len(text_files), batch_size):
                    batch = text_files[i:i + batch_size]
                    texts = [f.get('content', '')[:4000] for f in batch]
                    embeddings = text_model.encode(texts, convert_to_numpy=True, batch_size=batch_size)

                    for j, file_rec in enumerate(batch):
                        file_id = f"{project_id}::{file_rec.get('relative_path', file_rec['filename'])}"
                        meta = {
                            "project_id": project_id,
                            "filename": file_rec['filename'],
                            "file_type": 'text',
                            "extension": file_rec.get('extension', ''),
                            "doc_id": file_id,
                            "domain": "text_multilingual",
                            "has_arabic": is_arabic_text(file_rec.get('content', ''))
                        }
                        self.docs_collection.upsert(
                            ids=[file_id],
                            embeddings=[embeddings[j].tolist()],
                            metadatas=[meta],
                            documents=[file_rec.get('content', '')[:2000]]
                        )

                if log_callback:
                    log_callback(f"  ✅ [Batch] Indexed {len(code_files)} code + {len(text_files)} text files.")

