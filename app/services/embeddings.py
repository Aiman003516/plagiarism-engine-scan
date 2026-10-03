"""On-demand FAISS embedding indexing (decoupled from the upload stream)."""

from typing import Dict

from plagiarism_engine import VectorStore, SystemDBStore


# ---------------------------------------------------------------------------
# On-demand FAISS embedding indexing (decoupled from the upload stream)
# ---------------------------------------------------------------------------
def _index_project_embeddings(
    vstore: VectorStore,
    db_store: SystemDBStore,
    project_id: str,
    log_callback=None,
) -> Dict[str, int]:
    """(Re)build a project's FAISS embeddings from its DB-stored files.

    Embedding generation was decoupled from the upload stream (``_run_intake``)
    for performance, so every freshly uploaded project starts with an EMPTY
    vector index. This routine is the single place that fills it: it is called
    on demand by POST /api/plagiarism/projects/{project_id}/index-embeddings
    and automatically by Deep Scan when a project has no vectors yet.

    Any vectors already stored for the project are purged first, so repeated
    calls stay idempotent instead of stacking duplicate embeddings for the
    same files. Blocking by design (CodeBERT / BGE-M3 encoding) — callers run
    it inside an executor so the event loop is never stalled.
    """
    files_data = db_store.get_project_files(project_id)

    # Replace rather than append: keeps re-indexing idempotent.
    vstore.delete_project(project_id)

    added = vstore.index_project_files(
        project_files=files_data,
        project_id=project_id,
        log_callback=log_callback,
    )

    print(
        f"[FAISS] Project '{project_id}': indexed {added.get('code', 0)} code + "
        f"{added.get('text', 0)} text vectors from {len(files_data)} stored files."
    )
    return added
