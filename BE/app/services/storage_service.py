"""File storage abstraction. Local disk today; swap for S3/Azure Blob by implementing the same methods."""

import asyncio
import hashlib
import shutil
import uuid
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.storage_path
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_key(deal_id: uuid.UUID, document_id: uuid.UUID, extension: str) -> str:
        return f"{deal_id}/{document_id}{extension}"

    def path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    async def save(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def delete(self, key: str) -> None:
        path = self.path_for(key)
        await asyncio.to_thread(path.unlink, True)

    async def delete_prefix(self, prefix: str) -> None:
        path = self.path_for(prefix)
        if path.is_dir():
            await asyncio.to_thread(shutil.rmtree, path, True)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


storage = LocalStorage()
