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

# Raw semantic admission thresholds for semantic-only matches (pairs with 0 shared fingerprints).
# BGE-M3 threshold 0.885 sits above the max unrelated real text pair (0.876, n=652) and admits both
# English (0.960) and Arabic (0.909) paraphrases without depending on a calibrated floor.
SEMANTIC_ADMISSION_RAW: dict = {
    "bge-m3": 0.885,
    "multilingual-e5-base": 0.890,
    "LaBSE": 0.800,
}

# Code gate: code is never admitted on meaning alone. A semantic boost applies only when the pair
# shares >= min_shared_fps Winnowing fingerprints.
CODE_SEMANTIC_GATE: dict = {
    "min_shared_fps": 3,
    "min_calibrated": 0.70,
    "alpha": 0.30,
}

# MOSS-style common-code suppression: fingerprints that appear in >= max(COMMON_FP_MIN_PROJECTS,
# COMMON_FP_FRACTION * total_projects) are ignored as shared boilerplate/framework templates.
COMMON_FP_MIN_PROJECTS = 5
COMMON_FP_FRACTION = 0.05



class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/plagiarism_engine")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "pgvector")  # Re-aligned to unified architecture
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "project-files")
    JWT_SECRET = os.environ.get("JWT_SECRET", "")
    MODELS_DIR = os.environ.get("MODELS_DIR", "./models")

