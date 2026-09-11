import logging
import urllib.request
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

# Note: OpenCV Zoo uses Git LFS, so media.githubusercontent.com serves the actual binary ONNX weights
YUNET_DEFAULT_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_DEFAULT_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

# Minimum valid binary sizes (YuNet ~230KB, SFace ~1.2MB) to reject any Git LFS text pointers
MIN_MODEL_BYTES = 50_000


def ensure_model_file(model_path: str, source_url: str) -> str:
    """
    Checks if model file exists locally and is a valid binary model.
    If not, downloads it from the source URL.
    Returns the absolute path to the model file.
    """
    path = Path(model_path)
    if path.exists() and path.stat().st_size >= MIN_MODEL_BYTES:
        return str(path.resolve())

    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading model from %s to %s...", source_url, path)
    temp_path = path.with_suffix(".tmp")
    try:
        req = urllib.request.Request(
            source_url, headers={"User-Agent": "Yaadein-Backend/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp, open(
            temp_path, "wb"
        ) as f:
            while chunk := resp.read(65536):
                f.write(chunk)

        if temp_path.stat().st_size < MIN_MODEL_BYTES:
            raise ValueError(
                f"Downloaded file from {source_url} is too small ({temp_path.stat().st_size} bytes). "
                "Expected binary ONNX weights."
            )

        temp_path.replace(path)
        logger.info(
            "Successfully downloaded %s (%d bytes)", path.name, path.stat().st_size
        )
        return str(path.resolve())
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        logger.error("Failed to download model from %s: %s", source_url, e)
        raise e


def ensure_face_models() -> tuple[str, str]:
    """
    Ensures both YuNet and SFace ONNX models are present locally.
    Returns tuple of (yunet_path, sface_path).
    """
    yunet_path = ensure_model_file(settings.YUNET_MODEL_PATH, YUNET_DEFAULT_URL)
    sface_path = ensure_model_file(settings.SFACE_MODEL_PATH, SFACE_DEFAULT_URL)
    return yunet_path, sface_path
