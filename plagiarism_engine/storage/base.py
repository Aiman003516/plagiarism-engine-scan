from abc import ABC, abstractmethod
from typing import List

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
    def list_files(self, dir_path: str) -> List[str]:
        """List all files in a directory."""
        ...

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        ...
