from pathlib import Path
from shutil import copyfile

from app.config import get_settings


class LocalStorageProvider:
    name = "local"

    def __init__(self):
        self.settings = get_settings()
        self.base_path = Path(self.settings.local_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, storage_key: str) -> str:
        return str((self.base_path / storage_key).resolve())

    def save_file(self, source_path: str, storage_key: str) -> dict:
        source = Path(source_path)
        target = self.base_path / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, target)

        return {
            "storage_key": storage_key,
            "public_url": f"/assets/{storage_key}",
            "size_bytes": target.stat().st_size,
        }
