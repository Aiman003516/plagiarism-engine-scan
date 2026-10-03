"""
FastAPI application entry point for the Plagiarism Detection Engine.

Builds the app (lifespan, CORS) and mounts every feature router. All endpoint
logic lives in `app/routers/*`, shared state in `app/state.py`, auth in
`app/dependencies.py`, and the scan pipeline in `app/services/*`.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    (the legacy `uvicorn backend:app` command still works via the backend.py shim)
"""

import os
import sys
import threading
from pathlib import Path
from contextlib import asynccontextmanager

# Increase Starlette's max_files limit to allow uploading massive project folders
import starlette.formparsers
starlette.formparsers.MultiPartParser.max_files = 100000
starlette.formparsers.MultiPartParser.max_fields = 100000

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Ensure the project root (which holds the plagiarism_engine package) is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.state import _preload_models
from app.routers import (
    auth,
    teams,
    users,
    dashboard,
    projects,
    history,
    scanner,
    deep_scan,
    compare,
    settings,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    thread = threading.Thread(target=_preload_models, daemon=True)
    thread.start()
    
    try:
        from plagiarism_engine.vectors.hybrid_service import HybridVectorService
        from app.state import get_vstore
        import os
        if os.environ.get("VECTOR_BACKEND", "hybrid") in ("hybrid", "faiss"):
            hvs = HybridVectorService(get_vstore())
            hvs.hydrate_faiss_from_db()
    except Exception as e:
        print(f"Failed to hydrate FAISS: {e}")
        
    yield


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Plagiarism Detection Engine API",
    description="Isolated standalone plagiarism scanning backend.",
    lifespan=lifespan,
)

# A wildcard origin cannot be combined with `allow_credentials=True` on
# credentialed requests, so the allowed origins are listed explicitly.
# The Vite dev server runs on port 3000 (frontend/package.json: "vite --port=3000").
# Override with PLAGIARISM_CORS_ORIGINS="http://host-a,http://host-b" when needed.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "PLAGIARISM_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers — included in the same order the endpoints were originally declared
# so route matching precedence is unchanged.
# ---------------------------------------------------------------------------
for _router_module in (
    auth,
    teams,
    users,
    dashboard,
    projects,
    history,
    scanner,
    deep_scan,
    compare,
    settings,
):
    app.include_router(_router_module.router)
