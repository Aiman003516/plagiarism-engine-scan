# Phase 5 Goal: Cloud Storage & Serverless Readiness

## Objective
Abstract file storage behind a `StorageService` interface so the system works on both local filesystem and cloud storage (Supabase Storage / AWS S3). Make the entire system deployable to a serverless platform.

## Context
Read `MASTER_ROADMAP.md` in this repo for the full project context. This is Phase 5 of 6.
Phases 2-4 must be completed before starting this phase.

## Tasks

### Task 1: Create StorageService Abstraction

Create `plagiarism_engine/storage/`:
```
plagiarism_engine/storage/
├── __init__.py          — export get_storage_service()
├── base.py              — StorageService abstract base class
├── local_storage.py     — LocalStorage implementation (current behavior)
└── supabase_storage.py  — SupabaseStorage implementation (cloud)
```

**base.py:**
```python
from abc import ABC, abstractmethod

class StorageService(ABC):
    @abstractmethod
    def save_file(self, path: str, content: bytes) -> str:
        """Save file, return the storage path/URL."""
        ...

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read file content by path."""
        ...

    @abstractmethod
    def delete_file(self, path: str) -> None:
        """Delete a file by path."""
        ...

    @abstractmethod
    def delete_directory(self, dir_path: str) -> None:
        """Delete a directory and all contents."""
        ...

    @abstractmethod
    def list_files(self, dir_path: str) -> list[str]:
        """List all files in a directory."""
        ...

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        ...
```

**local_storage.py** — wraps the current `data/` folder file operations.

**supabase_storage.py** — uses the Supabase Python client (`supabase-py`) to store/retrieve files from a Supabase Storage bucket.

### Task 2: Replace All Direct Filesystem Access

Search the entire backend for direct `os.path`, `Path()`, `open()`, `shutil` calls that handle project files and replace them with `StorageService` method calls.

Key locations to update:
- Git clone temp directory management in `services/git_clone.py`
- File upload handling in `routers/scanner.py`
- Project deletion (file cleanup) in `routers/projects.py`
- FAISS index file save/load in `vectors/faiss_store.py`

### Task 3: Environment-Driven Configuration

Create or update `.env.example`:
```env
# Storage backend: "local" or "supabase"
STORAGE_BACKEND=local

# Supabase config (only needed if STORAGE_BACKEND=supabase)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbG...
SUPABASE_STORAGE_BUCKET=project-files

# Vector backend: "hybrid", "pgvector", or "faiss"
VECTOR_BACKEND=hybrid

# Database
DATABASE_URL=postgresql://localhost:5432/plagiarism_engine

# JWT
JWT_SECRET=your-secret-here
```

Create `plagiarism_engine/config.py`:
```python
import os

class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/plagiarism.db")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "faiss")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "project-files")
    JWT_SECRET = os.environ.get("JWT_SECRET", "")
    MODELS_DIR = os.environ.get("MODELS_DIR", "./models")
```

### Task 4: Add `supabase` to Requirements

In `requirements.txt`:
```
supabase>=2.0.0
```

### Task 5: Verify

1. Test with `STORAGE_BACKEND=local` — everything works as before
2. Test with `STORAGE_BACKEND=supabase` — files upload to Supabase bucket
3. Test project deletion — files removed from storage
4. Test FAISS index persistence on local storage
5. Run frontend TypeScript check
6. Git push

## Success Criteria
- [ ] `StorageService` abstraction created with local and Supabase implementations
- [ ] All direct filesystem access replaced with StorageService calls
- [ ] `Config` class centralizes all environment variables
- [ ] System works with `STORAGE_BACKEND=local` (unchanged behavior)
- [ ] System works with `STORAGE_BACKEND=supabase` (cloud storage)
- [ ] `.env.example` updated with all configuration variables
- [ ] Git pushed to GitHub
