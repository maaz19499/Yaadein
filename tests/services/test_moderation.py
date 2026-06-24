from unittest.mock import patch
from src.services.moderation import ModerationService


def test_moderation_service_safe_image() -> None:
    service = ModerationService()
    # Mock detect_moderation_labels response
    mock_response = {
        "ModerationLabels": []
    }
    with patch.object(service.client, "detect_moderation_labels", return_value=mock_response) as mock_detect:
        result = service.is_image_safe(b"dummy_bytes")
        assert result is True
        mock_detect.assert_called_once_with(
            Image={"Bytes": b"dummy_bytes"},
            MinConfidence=50.0
        )


def test_moderation_service_unsafe_image() -> None:
    service = ModerationService()
    mock_response = {
        "ModerationLabels": [
            {"Name": "Explicit Nudity", "Confidence": 95.0}
        ]
    }
    with patch.object(service.client, "detect_moderation_labels", return_value=mock_response) as mock_detect:
        result = service.is_image_safe(b"dummy_bytes")
        assert result is False
        mock_detect.assert_called_once_with(
            Image={"Bytes": b"dummy_bytes"},
            MinConfidence=50.0
        )
