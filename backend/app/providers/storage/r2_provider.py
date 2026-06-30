import mimetypes
from pathlib import Path

import boto3

from app.config import get_settings


class R2StorageProvider:
    name = "r2"

    def __init__(self):
        self.settings = get_settings()
        self.bucket_name = self.settings.r2_bucket_name
        self.public_base_url = self.settings.r2_public_base_url.rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{self.settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
            region_name="auto",
        )

    def resolve_path(self, storage_key: str) -> str:
        return f"{self.public_base_url}/{storage_key.lstrip('/')}"

    def save_file(self, source_path: str, storage_key: str) -> dict:
        source = Path(source_path)
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"

        self.client.upload_file(
            str(source),
            self.bucket_name,
            storage_key,
            ExtraArgs={"ContentType": mime_type},
        )

        return {
            "storage_key": storage_key,
            "public_url": self.resolve_path(storage_key),
            "size_bytes": source.stat().st_size,
            "mime_type": mime_type,
        }