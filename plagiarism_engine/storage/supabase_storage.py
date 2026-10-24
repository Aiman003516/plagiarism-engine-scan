import os
from typing import List, Any
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    create_client = None
    Client = Any
    HAS_SUPABASE = False
from .base import StorageService


class SupabaseStorage(StorageService):
    @staticmethod
    def _validate_safe_path(p: str) -> str:
        clean = p.replace("\\", "/").strip().lstrip("/")
        parts = clean.split("/")
        if ".." in parts or any(part == "." for part in parts):
            raise ValueError(f"Unsafe path traversal detected: {p}")
        return clean

    @staticmethod
    def _validate_safe_path(p: str) -> str:
        clean = p.replace("\\", "/").strip().lstrip("/")
        parts = clean.split("/")
        if ".." in parts or any(part == "." for part in parts):
            raise ValueError(f"Unsafe path traversal detected: {p}")
        return clean

    def __init__(self, url: str, key: str, bucket: str = "project-files"):
        if not HAS_SUPABASE or create_client is None:
            raise ImportError("The 'supabase' package is required when STORAGE_BACKEND='supabase'.")
        self.supabase: Client = create_client(url, key)
        self.bucket = bucket
        
        # Ensure bucket exists (or handle failure gracefully if no permissions)
        try:
            buckets = self.supabase.storage.list_buckets()
            if not any(b.name == self.bucket for b in buckets):
                self.supabase.storage.create_bucket(self.bucket)
        except Exception:
            pass # Ignored, permissions might be restricted

    def save_file(self, path: str, content: bytes) -> str:
        clean_path = self._validate_safe_path(path)
        self.supabase.storage.from_(self.bucket).upload(
            file=content,
            path=clean_path,
            file_options={"upsert": "true"}
        )
        return self.supabase.storage.from_(self.bucket).get_public_url(clean_path)

    def read_file(self, path: str) -> bytes:
        clean_path = self._validate_safe_path(path)
        res = self.supabase.storage.from_(self.bucket).download(clean_path)
        return res

    def delete_file(self, path: str) -> None:
        clean_path = self._validate_safe_path(path)
        self.supabase.storage.from_(self.bucket).remove([clean_path])

    def delete_directory(self, dir_path: str) -> None:
        clean_path = dir_path.lstrip("/")
        # Supabase doesn't support recursive delete out of the box; we have to list and delete.
        files = self.list_files(clean_path)
        if files:
            self.supabase.storage.from_(self.bucket).remove(files)

    def list_files(self, dir_path: str) -> List[str]:
        clean_path = dir_path.replace("\\", "/").lstrip("/")
        if clean_path and not clean_path.endswith("/"):
            clean_path += "/"

        res = self.supabase.storage.from_(self.bucket).list(clean_path)
        files: List[str] = []
        for item in res or []:
            name = item.get("name")
            if not name or name == ".emptyFolderPlaceholder":
                continue
            item_path = f"{clean_path}{name}"
            # In Supabase Storage, folder placeholders have id=None and metadata=None
            if item.get("id") is None and item.get("metadata") is None:
                files.extend(self.list_files(item_path))
            else:
                files.append(item_path)
        return files

    def file_exists(self, path: str) -> bool:
        clean_path = path.lstrip("/")
        # Simplest way is to try to list it
        folder = os.path.dirname(clean_path)
        name = os.path.basename(clean_path)
        res = self.supabase.storage.from_(self.bucket).list(folder, {"search": name})
        return len(res) > 0 and any(item.get("name") == name for item in res)
