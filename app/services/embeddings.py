"""On-demand Postgres vector embedding indexing (decoupled from the upload stream)."""

from typing import Dict, Optional, Any

from plagiarism_engine import VectorStore, SystemDBStore
from plagiarism_engine.vector_store import _safe_log


# ---------------------------------------------------------------------------
# On-demand Postgres vector embedding indexing (decoupled from the upload stream)
# ---------------------------------------------------------------------------
def _index_project_embeddings(
    vstore: VectorStore,
    db_store: SystemDBStore,
    project_id: str,
    log_callback: Optional[Any] = None,
    force: bool = False,
) -> Dict[str, int]:
    """(Re)build a project's Postgres vector embeddings from its DB-stored files.

    Embedding generation was decoupled from the upload stream (``_run_intake``)
    for performance, so every freshly uploaded project starts with an EMPTY
    vector index. This routine is called on demand by POST /api/plagiarism/projects/{id}/index-embeddings
    and automatically by Deep Scan / Hybrid Fusion when a project has missing or stale vectors.

    Incremental by default: only encodes missing or stale files, preserving existing
    valid vectors to avoid expensive redundant neural network encodings. Pass force=True
    to wipe and re-encode all files from scratch.
    """
    files_data = db_store.get_project_files(project_id)

    if force:
        vstore.delete_project(project_id)

    added = vstore.index_project_files(
        project_files=files_data,
        project_id=project_id,
        log_callback=log_callback,
        force=force,
    )

    try:
        p_rec = db_store.get_project_by_id(project_id)
        if p_rec and p_rec.get("abstract"):
            import json
            from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
            from plagiarism_engine.vectors.pgvector_store import PgVectorStore
            from plagiarism_engine.text_detector import normalize_arabic_text
            model, _ = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
            if model:
                norm = normalize_arabic_text(p_rec["abstract"][:1500])
                raw = model.encode(norm, convert_to_numpy=True)
                pv = PgVectorStore(db_store)
                emb_1024 = pv._normalize_and_pad_1d(raw, 1024)
                db_store.update_project(
                    project_id,
                    abstract_embedding=json.dumps(emb_1024.tolist()),
                    abstract_embedding_binary=pv._quantize_to_bit_string(emb_1024)
                )
    except Exception as e:
        print(f"Notice on project abstract embedding indexing: {e}")

    msg = (
        f"[Postgres Vector] Project '{project_id}': indexed {added.get('code', 0)} code + "
        f"{added.get('text', 0)} text vectors from {len(files_data)} stored files."
    )
    if log_callback:
        _safe_log(log_callback, msg)
    else:
        print(msg)
    return added
