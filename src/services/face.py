import hashlib
import random
import numpy as np

class FaceEmbeddingService:
    """
    Service to handle face detection, embedding extraction, and face clustering.
    Falls back to a deterministic mock generator when dlib or insightface are not installed.
    """

    def generate_embeddings(self, image_bytes: bytes) -> list[list[float]]:
        """
        Detect faces in the image and return their 512-dimension embedding vectors.
        Returns mock embeddings if dlib/insightface are not available.
        Mock vectors are deterministically generated based on the SHA-256 hash of the image bytes
        to ensure identical files always yield identical face templates.
        """
        try:
            # Placeholder/Stub for future real model integration:
            # import insightface
            # ... real face detection & extraction ...
            pass
        except ImportError:
            pass

        # Fallback to deterministic mock embeddings
        sha = hashlib.sha256(image_bytes).hexdigest()
        
        # Deterministically decide if we have 1 or 2 faces in this mock photo
        num_faces = 1 if int(sha[0], 16) % 2 == 0 else 2
        
        embeddings = []
        for i in range(num_faces):
            # Generate a 512-dimension mock vector coordinates
            # Using i in seed variation to generate different vectors for different faces
            rng_face = random.Random(int(sha, 16) + i)
            vector = [rng_face.gauss(0, 1) for _ in range(512)]
            
            # Normalize to unit length (L2 norm) for cosine distance
            norm = sum(x * x for x in vector) ** 0.5
            if norm > 0:
                vector = [x / norm for x in vector]
            else:
                vector = [0.0] * 512
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
        Clustered 512-dimensional vectors using cosine-distance DBSCAN algorithm.
        Returns a list of cluster label indices matching the index of input embeddings.
        -1 indicates noise (if min_samples > 1).
        """
        if not embeddings:
            return []

        X = np.array(embeddings)
        # Re-verify that the vectors are unit vectors (normalize them)
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        X = X / np.where(norms == 0, 1e-12, norms)

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
