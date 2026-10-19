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

    msg = (
        f"[Postgres Vector] Project '{project_id}': indexed {added.get('code', 0)} code + "
        f"{added.get('text', 0)} text vectors from {len(files_data)} stored files."
    )
    if log_callback:
        _safe_log(log_callback, msg)
    else:
        print(msg)
    return added
