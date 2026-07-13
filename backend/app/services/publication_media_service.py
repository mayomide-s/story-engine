from __future__ import annotations

import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.models import Asset
from app.services.providers import get_storage_provider


class PublicationMediaError(RuntimeError):
    """Raised when a publication asset cannot be safely prepared for upload."""


@contextmanager
def open_publication_media(asset: Asset) -> Iterator[Path]:
    storage = get_storage_provider()
    temporary_path: Path | None = None
    try:
        if getattr(storage, "name", "") == "local":
            resolved = Path(storage.resolve_path(asset.storage_key))
            if not resolved.exists() or not resolved.is_file():
                raise PublicationMediaError("The frozen publication asset is not readable from local storage.")
            yield resolved
            return

        if getattr(storage, "name", "") == "r2":
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(asset.storage_key).suffix) as handle:
                temporary_path = Path(handle.name)
                response = storage.client.get_object(Bucket=storage.bucket_name, Key=asset.storage_key)
                body = response["Body"]
                try:
                    while True:
                        chunk = body.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                finally:
                    body.close()
            yield temporary_path
            return

        raise PublicationMediaError("The active storage provider does not support publication uploads.")
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
