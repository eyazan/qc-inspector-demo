"""Object storage abstraction for artifacts (PDFs, region crops, JSON/MD).

Local filesystem now; S3/MinIO is a drop-in via ACTIVE_OBJECT_STORE without
touching callers. Keys are POSIX-style paths (e.g. "run_x/pdfs/vendor/a.pdf").
"""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ObjectStore(ABC):
    name: str = "base"

    @abstractmethod
    def put(self, key: str, data: bytes) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def url(self, key: str) -> str: ...


class LocalFsObjectStore(ObjectStore):
    name = "local"

    def __init__(self, root: Path | None = None, mount: str | None = None):
        self._root = Path(root or (settings.data_root / "objects"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._mount = mount or settings.static_mount_path

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if not str(p).startswith(str(self._root.resolve())):
            raise ValueError("Invalid object key (path traversal)")
        return p

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url(key)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    def url(self, key: str) -> str:
        return f"{self._mount.rstrip('/')}/objects/{key}"


class S3ObjectStore(ObjectStore):  # pragma: no cover - future drop-in
    name = "s3"

    def __init__(self):
        try:
            import boto3  # noqa: F401
        except ImportError as err:
            raise RuntimeError(
                "S3ObjectStore needs boto3. pip install boto3, set S3_BUCKET/"
                "S3_ENDPOINT_URL, or use ACTIVE_OBJECT_STORE=local."
            ) from err
        import boto3

        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None
        )

    def put(self, key, data):
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return self.url(key)

    def get(self, key):
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def exists(self, key):
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key):
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def url(self, key):
        base = (settings.s3_endpoint_url or "").rstrip("/")
        return f"{base}/{self._bucket}/{key}" if base else f"s3://{self._bucket}/{key}"


def get_object_store() -> ObjectStore:
    if (settings.active_object_store or "local") == "s3":
        return S3ObjectStore()
    return LocalFsObjectStore()
