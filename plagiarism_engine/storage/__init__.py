from .base import StorageService
from .local_storage import LocalStorage
from .supabase_storage import SupabaseStorage
from plagiarism_engine.config import Config

_instance = None


def get_storage_service() -> StorageService:
    global _instance
    if _instance is None:
        if Config.STORAGE_BACKEND.lower() == "supabase":
            if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set for supabase storage backend")
            _instance = SupabaseStorage(
                url=Config.SUPABASE_URL,
                key=Config.SUPABASE_KEY,
                bucket=Config.SUPABASE_STORAGE_BUCKET,
            )
        else:
            _instance = LocalStorage()
    return _instance


__all__ = ["StorageService", "LocalStorage", "SupabaseStorage", "get_storage_service"]

