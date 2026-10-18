import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env() -> None:
    """Load key=value pairs from PROJECT_ROOT/.env into os.environ if not already set."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


load_project_env()


# Per-model semantic calibration floors = mean cosine of UNRELATED pairs, measured by
# scripts/calibrate_semantic_models.py (see calibration_results.md). Raw cosine is mapped to
# clip((raw - floor) / (1 - floor), 0, 1) so "unrelated" sits near 0 for every model.
# Text-model floors average the English and Arabic unrelated means.
SEMANTIC_CALIBRATION_FLOOR: dict = {
    "codebert-base": 0.98,
    "unixcoder-base": 0.30,
    "bge-m3": 0.72,
    "multilingual-e5-base": 0.75,
    "LaBSE": 0.35,
}


class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/plagiarism_engine")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "pgvector")  # Re-aligned to unified architecture
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "project-files")
    JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-here")
    MODELS_DIR = os.environ.get("MODELS_DIR", "./models")

