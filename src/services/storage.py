import math
from typing import Any, cast
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from src.config import settings


class R2StorageService:
    def __init__(self) -> None:
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        self.bucket_name = settings.R2_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        try:
            self.s3_client.create_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            # Bucket might already exist or be owned by you
            error_code = e.response.get("Error", {}).get("Code")
            if error_code not in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                raise

    def generate_presigned_upload_url(
        self, object_key: str, expires_in: int = 3600
    ) -> str:
        """
        Generates a presigned URL for a single put_object upload.
        """
        return cast(
            str,
            self.s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key,
                },
                ExpiresIn=expires_in,
            ),
        )

    def generate_presigned_multipart_upload_urls(
        self, object_key: str, file_size: int, expires_in: int = 3600
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Initiates a multipart upload and generates presigned URLs for each 10MB chunk.
        """
        # 1. Initiate multipart upload
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=object_key,
        )
        upload_id = response["UploadId"]

        # 2. Calculate chunk/part URLs
        chunk_size = 10 * 1024 * 1024  # 10MB target chunk size
        num_parts = math.ceil(file_size / chunk_size)

        part_urls = []
        for part_number in range(1, num_parts + 1):
            url = self.s3_client.generate_presigned_url(
                ClientMethod="upload_part",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in,
            )
            part_urls.append(
                {
                    "part_number": part_number,
                    "url": url,
                }
            )

        return upload_id, part_urls

    def complete_multipart_upload(
        self, object_key: str, upload_id: str
    ) -> dict[str, Any]:
        """
        Completes a multipart upload by listing all uploaded parts and sending the complete call.
        """
        parts_response = self.s3_client.list_parts(
            Bucket=self.bucket_name,
            Key=object_key,
            UploadId=upload_id,
        )
        parts = []
        for part in parts_response.get("Parts", []):
            parts.append(
                {
                    "PartNumber": part["PartNumber"],
                    "ETag": part["ETag"],
                }
            )

        # S3 requires the parts list to be sorted by PartNumber
        parts.sort(key=lambda p: p["PartNumber"])

        return cast(
            dict[str, Any],
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            ),
        )

    def head_object(self, object_key: str) -> dict[str, Any]:
        """
        Gets metadata (headers) for the object in S3/R2.
        """
        return cast(
            dict[str, Any],
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_key,
            ),
        )

    def get_object_body(self, object_key: str) -> bytes:
        """
        Downloads and returns the bytes of the object in S3/R2.
        """
        response = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=object_key,
        )
        return cast(bytes, response["Body"].read())

    def upload_bytes(self, data: bytes, object_key: str, content_type: str) -> None:
        """
        Uploads raw bytes to the specified key in S3/R2.
        """
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    def generate_presigned_download_url(
        self, object_key: str, expires_in: int = 3600
    ) -> str:
        """
        Generates a presigned URL for downloading an object.
        """
        return cast(
            str,
            self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key,
                },
                ExpiresIn=expires_in,
            ),
        )
