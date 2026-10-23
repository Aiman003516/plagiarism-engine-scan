import os
import shutil
from pathlib import Path
from typing import List

from .base import StorageService


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class LocalStorage(StorageService):
    def __init__(self, base_dir: str = "data/storage"):
        base_path = Path(base_dir)
        if not base_path.is_absolute() and base_dir == "data/storage":
            base_path = PROJECT_ROOT / "data" / "storage"
        self.base_dir = base_path.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        # Prevent path traversal
        clean_path = path.replace("\\", "/").lstrip("/")
        resolved = (self.base_dir / clean_path).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ValueError(f"Unsafe path detected: {path}")
        return resolved

    def save_file(self, path: str, content: bytes) -> str:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)

    def read_file(self, path: str) -> bytes:
        target = self._resolve_path(path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return target.read_bytes()

    def delete_file(self, path: str) -> None:
        target = self._resolve_path(path)
        if target.exists():
            target.unlink()

    def delete_directory(self, dir_path: str) -> None:
        target = self._resolve_path(dir_path)
        if target.exists() and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

    def list_files(self, dir_path: str) -> List[str]:
        target = self._resolve_path(dir_path)
        if not target.exists() or not target.is_dir():
            return []
        
        files = []
        for root, _, fnames in os.walk(target):
            for fname in fnames:
                full_path = Path(root) / fname
                rel_path = full_path.relative_to(self.base_dir)
                # Convert back to string with forward slashes
                files.append(str(rel_path).replace("\\", "/"))
        return files

    def file_exists(self, path: str) -> bool:
        target = self._resolve_path(path)
        return target.exists() and target.is_file()
