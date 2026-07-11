from __future__ import annotations

from typing import Protocol


class StorageProvider(Protocol):
    name: str

    def save_file(self, source_path: str, storage_key: str) -> dict:
        ...

    def build_public_url(self, storage_key: str) -> str:
        ...

    def resolve_path(self, storage_key: str) -> str:
        ...
