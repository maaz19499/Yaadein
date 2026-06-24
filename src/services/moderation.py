import boto3
from src.config import settings


class ModerationService:
    def __init__(self) -> None:
        kwargs = {}
        if settings.AWS_REGION:
            kwargs["region_name"] = settings.AWS_REGION
        if settings.AWS_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        if settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

        self.client = boto3.client("rekognition", **kwargs)

    def is_image_safe(self, image_bytes: bytes) -> bool:
        """
        Calls detect_moderation_labels on image bytes and returns True if safe,
        False if unsafe (has moderation labels with confidence >= 50.0).
        """
        try:
            response = self.client.detect_moderation_labels(
                Image={"Bytes": image_bytes},
                MinConfidence=50.0
            )
            labels = response.get("ModerationLabels", [])
            return len(labels) == 0
        except Exception as e:
            # Re-raise the exception to let the caller/worker handle it
            raise e
