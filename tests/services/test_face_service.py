import io
import math
from PIL import Image
from src.services.face import FaceEmbeddingService
from src.services.model_loader import ensure_face_models


def create_blank_jpeg(size: tuple[int, int] = (320, 320)) -> bytes:
    img = Image.new("RGB", size, color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_face_models_loading() -> None:
    yunet_path, sface_path = ensure_face_models()
    assert yunet_path is not None
    assert sface_path is not None


def test_generate_embeddings_blank_image() -> None:
    service = FaceEmbeddingService()
    blank_bytes = create_blank_jpeg()
    embeddings = service.generate_embeddings(blank_bytes)
    # A plain blank gray canvas has no faces detected by YuNet
    assert embeddings == []


def test_generate_embeddings_empty_bytes() -> None:
    service = FaceEmbeddingService()
    assert service.generate_embeddings(b"") == []


def test_generate_embeddings_mock_fallback() -> None:
    service = FaceEmbeddingService()
    fake_bytes = b"not-a-valid-image-format"
    embeddings = service.generate_embeddings(fake_bytes)
    assert len(embeddings) in (1, 2)
    for vec in embeddings:
        assert len(vec) == 128
        # Ensure unit L2 normalization
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4


def test_cluster_embeddings_dbscan() -> None:
    service = FaceEmbeddingService()

    # Seed 3 128-d unit vectors:
    # vec1 & vec2 are nearly identical (cosine distance ~0.05)
    # vec3 is orthogonal (cosine distance ~1.0)
    vec1 = [0.0] * 128
    vec1[0] = 1.0

    vec2 = [0.0] * 128
    vec2[0] = 0.95
    vec2[1] = math.sqrt(1.0 - 0.95**2)

    vec3 = [0.0] * 128
    vec3[127] = 1.0

    labels = service.cluster_embeddings([vec1, vec2, vec3], eps=0.4, min_samples=1)
    assert len(labels) == 3
    assert labels[0] == labels[1]
    assert labels[0] != labels[2]
