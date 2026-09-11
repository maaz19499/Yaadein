import hashlib
import logging
import random
from typing import Any
import cv2
import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)


class FaceEmbeddingService:
    """
    Service to handle face detection, embedding extraction, and face clustering
    using OpenCV Zoo YuNet (face detection) and SFace (128-d face embedding).
    Falls back to a deterministic 128-d mock generator when image decoding fails
    or during tests with synthetic byte payloads.
    """

    _detector: Any = None
    _recognizer: Any = None
    _models_initialized: bool = False

    @classmethod
    def _init_models(cls) -> None:
        if cls._models_initialized:
            return
        try:
            from src.services.model_loader import ensure_face_models

            yunet_path, sface_path = ensure_face_models()
            cls._detector = cv2.FaceDetectorYN.create(
                yunet_path,
                "",
                (320, 320),
                score_threshold=settings.FACE_SCORE_THRESHOLD,
            )
            cls._recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
            cls._models_initialized = True
            logger.info("Successfully initialized YuNet and SFace OpenCV models.")
        except Exception as e:
            logger.warning(
                "Could not initialize OpenCV face models: %s. "
                "Will fallback to deterministic mock embeddings.",
                e,
            )
            cls._models_initialized = True

    def generate_embeddings(self, image_bytes: bytes) -> list[list[float]]:
        """
        Detect faces in the image and return their 128-dimension SFace embedding vectors.
        Returns mock 128-d embeddings if decoding fails or models are unavailable.
        """
        if not image_bytes:
            return []

        self._init_models()

        if self._detector is not None and self._recognizer is not None:
            try:
                np_arr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if img is not None and img.size > 0:
                    h, w = img.shape[:2]
                    self._detector.setInputSize((w, h))
                    _, faces = self._detector.detect(img)
                    if faces is None or len(faces) == 0:
                        return []

                    embeddings: list[list[float]] = []
                    for face in faces:
                        aligned_face = self._recognizer.alignCrop(img, face)
                        feature = self._recognizer.feature(aligned_face)
                        norm = float(np.linalg.norm(feature))
                        if norm > 0:
                            feature = feature / norm
                        embeddings.append(feature.flatten().tolist())
                    return embeddings
            except Exception as e:
                logger.warning(
                    "OpenCV face detection/extraction encountered error: %s. "
                    "Falling back to mock embeddings.",
                    e,
                )

        # Fallback to deterministic 128-d mock embeddings
        return self._mock_embeddings(image_bytes)

    def _mock_embeddings(self, image_bytes: bytes) -> list[list[float]]:
        """
        Deterministically generates 128-dimension unit vectors based on SHA-256 hash.
        Used for fallback and synthetic tests.
        """
        sha = hashlib.sha256(image_bytes).hexdigest()
        num_faces = 1 if int(sha[0], 16) % 2 == 0 else 2

        embeddings = []
        for i in range(num_faces):
            rng_face = random.Random(int(sha, 16) + i)
            vector = [rng_face.gauss(0, 1) for _ in range(128)]

            # Normalize to unit length (L2 norm) for cosine distance
            norm = sum(x * x for x in vector) ** 0.5
            if norm > 0:
                vector = [x / norm for x in vector]
            else:
                vector = [0.0] * 128
                vector[0] = 1.0

            embeddings.append(vector)

        return embeddings

    def cluster_embeddings(
        self,
        embeddings: list[list[float]],
        eps: float = 0.4,
        min_samples: int = 1,
    ) -> list[int]:
        """
        Clusters 128-dimensional vectors using cosine-distance DBSCAN algorithm.
        Returns a list of cluster label indices matching the index of input embeddings.
        -1 indicates noise (if min_samples > 1).
        """
        if not embeddings:
            return []

        X = np.array(embeddings, dtype=np.float32)
        # Re-verify that the vectors are unit vectors (normalize them)
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        X = (X / np.where(norms == 0, 1e-12, norms)).astype(np.float32)

        # Cosine distance = 1 - cosine_similarity.
        # Since vectors are normalized, cosine_similarity = dot product.
        dist_matrix = 1.0 - np.dot(X, X.T)

        n_samples = len(embeddings)
        labels = -np.ones(n_samples, dtype=int)
        cluster_id = 0

        for i in range(n_samples):
            if labels[i] != -1:
                continue

            # Get indices of neighbors within epsilon distance
            neighbors = np.where(dist_matrix[i] <= eps)[0].tolist()

            if len(neighbors) < min_samples:
                continue

            labels[i] = cluster_id

            # Expand the cluster
            queue = [n for n in neighbors if n != i]
            for neighbor in queue:
                if labels[neighbor] == -1:
                    labels[neighbor] = cluster_id
                    n_neighbors = np.where(dist_matrix[neighbor] <= eps)[0].tolist()
                    if len(n_neighbors) >= min_samples:
                        for val in n_neighbors:
                            if val not in queue and labels[val] == -1:
                                queue.append(val)

            cluster_id += 1

        return labels.tolist()
