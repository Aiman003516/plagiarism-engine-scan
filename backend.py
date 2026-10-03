"""
Backward-compatibility shim for the Plagiarism Detection Engine backend.

The backend was refactored from this single 2,000+ line module into the
modular `app/` package:

    app/main.py            FastAPI app, CORS, lifespan, router mounting
    app/state.py           shared singletons (DB, vector store, model caches, history)
    app/dependencies.py    JWT auth + require_role() RBAC dependency
    app/routers/*.py       one APIRouter per domain (auth, users, projects, scanner, ...)
    app/services/*.py      scan pipeline, git clone, SSE scan sessions, embeddings

This file only re-exports the application so existing commands keep working:

    uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   (preferred)
"""

from app.main import app  # noqa: F401

__all__ = ["app"]
