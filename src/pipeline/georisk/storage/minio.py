"""MinIO S3-compatible storage client."""

from pathlib import Path
from typing import Any, BinaryIO

import boto3
import structlog
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from georisk.config import get_config

logger = structlog.get_logger()


class MinioStorage:
    """Client for MinIO S3-compatible object storage."""

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
    ):
        """Initialize the MinIO storage client.

        Args:
            endpoint: MinIO endpoint URL.
            access_key: Access key for authentication.
            secret_key: Secret key for authentication.
            secure: Use HTTPS if True.
        """
        config = get_config()

        self.endpoint = endpoint or config.minio.endpoint
        self.access_key = access_key or config.minio.access_key
        self.secret_key = secret_key or config.minio.secret_key
        self.secure = secure if secure is not None else config.minio.secure
        self.bucket_imagery = config.minio.bucket_imagery
        self.bucket_changes = config.minio.bucket_changes

        # Build endpoint URL
        protocol = "https" if self.secure else "http"
        self.endpoint_url = f"{protocol}://{self.endpoint}"

        self._client = None

    @property
    def client(self) -> Any:
        """Get or create the boto3 S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=BotoConfig(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                ),
            )
            logger.info("Connected to MinIO", endpoint=self.endpoint)
        return self._client

    def ensure_bucket(self, bucket: str) -> None:
        """Ensure a bucket exists, creating it if necessary.

        Args:
            bucket: Bucket name.
        """
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=bucket)
                logger.info("Created bucket", bucket=bucket)
            else:
                raise

    def upload_file(
        self,
        local_path: Path,
        bucket: str,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a local file to storage.

        Args:
            local_path: Path to the local file.
            bucket: Target bucket name.
            object_key: Object key (path) in the bucket.
            content_type: MIME type of the file.

        Returns:
            Full object path (bucket/key).
        """
        self.ensure_bucket(bucket)

        self.client.upload_file(
            str(local_path),
            bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

        logger.info(
            "Uploaded file",
            bucket=bucket,
            key=object_key,
            size=local_path.stat().st_size,
        )

        return f"{bucket}/{object_key}"

    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        bucket: str,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file-like object to storage.

        Args:
            file_obj: File-like object to upload.
            bucket: Target bucket name.
            object_key: Object key (path) in the bucket.
            content_type: MIME type of the file.

        Returns:
            Full object path (bucket/key).
        """
        self.ensure_bucket(bucket)

        self.client.upload_fileobj(
            file_obj,
            bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

        logger.info("Uploaded file object", bucket=bucket, key=object_key)
        return f"{bucket}/{object_key}"

    def download_file(self, bucket: str, object_key: str, local_path: Path) -> Path:
        """Download a file from storage.

        Args:
            bucket: Source bucket name.
            object_key: Object key in the bucket.
            local_path: Local path to save the file.

        Returns:
            Path to the downloaded file.
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)

        self.client.download_file(bucket, object_key, str(local_path))

        logger.info("Downloaded file", bucket=bucket, key=object_key, path=str(local_path))
        return local_path

    def get_presigned_url(
        self,
        bucket: str,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for direct access.

        Args:
            bucket: Bucket name.
            object_key: Object key in the bucket.
            expires_in: URL expiration time in seconds.

        Returns:
            Presigned URL string.
        """
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )

        logger.debug("Generated presigned URL", bucket=bucket, key=object_key)
        return url

    def list_objects(self, bucket: str, prefix: str = "") -> list[dict[str, Any]]:
        """List objects in a bucket with optional prefix filter.

        Args:
            bucket: Bucket name.
            prefix: Optional prefix to filter objects.

        Returns:
            List of object metadata dictionaries.
        """
        objects = []

        paginator = self.client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        for page in pages:
            for obj in page.get("Contents", []):
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                })

        return objects

    def delete_object(self, bucket: str, object_key: str) -> None:
        """Delete an object from storage.

        Args:
            bucket: Bucket name.
            object_key: Object key to delete.
        """
        self.client.delete_object(Bucket=bucket, Key=object_key)
        logger.info("Deleted object", bucket=bucket, key=object_key)

    def object_exists(self, bucket: str, object_key: str) -> bool:
        """Check if an object exists.

        Args:
            bucket: Bucket name.
            object_key: Object key to check.

        Returns:
            True if object exists, False otherwise.
        """
        try:
            self.client.head_object(Bucket=bucket, Key=object_key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            raise

    # Convenience methods for specific buckets

    def upload_imagery(
        self,
        local_path: Path,
        aoi_id: str,
        scene_id: str,
        filename: str | None = None,
    ) -> str:
        """Upload imagery to the imagery bucket.

        Args:
            local_path: Path to the local raster file.
            aoi_id: Area of Interest ID.
            scene_id: Scene identifier.
            filename: Optional filename (defaults to local filename).

        Returns:
            Object key path.
        """
        filename = filename or local_path.name
        object_key = f"{aoi_id}/{scene_id}/{filename}"

        return self.upload_file(
            local_path,
            self.bucket_imagery,
            object_key,
            content_type="image/tiff",
        )

    def upload_change_artifacts(
        self,
        local_path: Path,
        aoi_id: str,
        run_id: str,
        filename: str | None = None,
    ) -> str:
        """Upload change detection artifacts to the changes bucket.

        Args:
            local_path: Path to the local file.
            aoi_id: Area of Interest ID.
            run_id: Processing run ID.
            filename: Optional filename (defaults to local filename).

        Returns:
            Object key path.
        """
        filename = filename or local_path.name
        object_key = f"{aoi_id}/{run_id}/{filename}"

        # Determine content type
        suffix = local_path.suffix.lower()
        content_type = {
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".geojson": "application/geo+json",
            ".json": "application/json",
        }.get(suffix, "application/octet-stream")

        return self.upload_file(
            local_path,
            self.bucket_changes,
            object_key,
            content_type=content_type,
        )
