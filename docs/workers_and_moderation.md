# Background Workers and Moderation Trigger Architecture

This document describes how background worker tasks, safety scans, and periodic batch jobs are triggered, executed, and verified within Yaadein.

## Overview

Yaadein uses **Celery** as the distributed task queue and **Redis** as both the message broker and result backend. All configurations are initialized in [src/workers/app.py](file:///e:/Projects/Yaadein/src/workers/app.py).

---

## 1. Image Processing & AWS Rekognition Moderation
* **Task Name:** `src.workers.tasks.media.process_image_upload`
* **Definition:** [process_image_upload](file:///e:/Projects/Yaadein/src/workers/tasks/media.py#L127) in [src/workers/tasks/media.py](file:///e:/Projects/Yaadein/src/workers/tasks/media.py)

### Trigger
When a user uploads a media asset and confirms the upload via the `/confirm-upload` endpoint (defined in [src/api/v1/media.py](file:///e:/Projects/Yaadein/src/api/v1/media.py)), the API calls:
```python
process_image_upload.delay(str(payload.event_id), str(new_media.id))
```

### Execution Steps
1. **Download:** Downloads the original image from the R2 Storage bucket using [R2StorageService](file:///e:/Projects/Yaadein/src/services/storage.py).
2. **Perceptual Hashing (pHash):** Generates a perceptual hash of the image via [generate_phash](file:///e:/Projects/Yaadein/src/services/images.py).
3. **AWS Rekognition Moderation Scan:** Calls the AWS Rekognition API via [ModerationService](file:///e:/Projects/Yaadein/src/services/moderation.py).
   * If any unsafe/NSFW labels are detected with confidence >= 50%, updates the media database status to `"rejected"` and stops.
4. **Duplicate Check:** Queries the database using the generated pHash to check if a duplicate image already exists in the same event.
   * If a duplicate is found, the media's status is set to `"duplicate"` and execution stops.
5. **Thumbnails & Previews:** Downscales the safe image into:
   * **Thumbnail:** 400px width WebP format
   * **Preview:** 1600px width WebP format
6. **Upload & Publish:** Uploads the thumbnail and preview assets back to the R2 Storage bucket and updates the database record status to `"visible"`.
7. **Next Step Trigger:** If the event has face search enabled and the guest has active consent, it triggers the face embedding generator task:
   ```python
   generate_face_embeddings.delay(str(event_id), str(media_id), str(consent.id))
   ```

---

## 2. Face Embeddings Extraction
* **Task Name:** `src.workers.tasks.face.generate_face_embeddings`
* **Definition:** [generate_face_embeddings](file:///e:/Projects/Yaadein/src/workers/tasks/face.py#L87) in [src/workers/tasks/face.py](file:///e:/Projects/Yaadein/src/workers/tasks/face.py)

### Trigger
1. **Direct Flow:** Dispatched automatically near the end of the [process_image_upload](file:///e:/Projects/Yaadein/src/workers/tasks/media.py#L127) task when a new image passes all filters and the uploading guest has provided consent.
2. **Back-fill Flow:** When a guest grants face search consent at a later stage (handled in [src/api/v1/auth.py](file:///e:/Projects/Yaadein/src/api/v1/auth.py)), the backend queries all previously uploaded `visible` images by that guest session and dispatches a backfill run:
   ```python
   generate_face_embeddings.delay(str(event_id), str(m.id), str(consent.id))
   ```

### Execution Steps
1. Downloads the image WebP/JPG from R2 storage.
2. Detects and extracts facial bounding boxes and 128-dimensional embedding vectors using the Rekognition face index / embedding service.
3. Inserts the coordinates and embeddings into the `face_embeddings` database table.

---

## 3. Periodic Face Clustering (DBSCAN)
* **Task Name:** `src.workers.tasks.face.cluster_faces_job`
* **Definition:** [cluster_faces_job](file:///e:/Projects/Yaadein/src/workers/tasks/face.py#L191) in [src/workers/tasks/face.py](file:///e:/Projects/Yaadein/src/workers/tasks/face.py)

### Trigger
Scheduled via the **Celery Beat** scheduler configuration inside [src/workers/app.py](file:///e:/Projects/Yaadein/src/workers/app.py#L19) to run daily at midnight UTC:
```python
celery_app.conf.beat_schedule = {
    "daily-face-clustering": {
        "task": "src.workers.tasks.face.cluster_faces_job",
        "schedule": crontab(hour=0, minute=0),
    }
}
```

### Execution Steps
1. Fetches all active/non-expired events.
2. Groups face embedding vectors in each event using cosine distance DBSCAN clustering.
3. Creates new face cluster profiles and maps the embeddings to those clusters in the database.

---

## 4. Asynchronous ZIP Exports
* **Task Name:** `src.workers.tasks.media.generate_zip_export`
* **Definition:** [generate_zip_export](file:///e:/Projects/Yaadein/src/workers/tasks/media.py#L279) in [src/workers/tasks/media.py](file:///e:/Projects/Yaadein/src/workers/tasks/media.py)

### Trigger
Dispatched when a host requests downloading an event or album ZIP in [src/api/v1/downloads.py](file:///e:/Projects/Yaadein/src/api/v1/downloads.py):
```python
generate_zip_export.delay(str(new_export.id), str(event_id), payload.scope, album_id_str)
```

### Execution Steps
1. Queries the media rows matching the requested event or album.
2. Downloads the original media assets from R2.
3. Bundles them into a ZIP archive, uploads the archive to a designated R2 path, and updates the DB Export row's status to `"completed"` with the download URL.

---

## Local Verification and Testing

### Running Celery Workers Locally
1. Start the local Redis broker (e.g., using `docker-compose up redis`).
2. Run the Celery worker process:
   ```bash
   poetry run celery -A src.workers.app.celery_app worker --loglevel=info
   ```
3. (Optional) Run the periodic beat scheduler:
   ```bash
   poetry run celery -A src.workers.app.celery_app beat --loglevel=info
   ```

### Running Automated Tests
The worker test files are located at:
* [tests/workers/test_media.py](file:///e:/Projects/Yaadein/tests/workers/test_media.py)
* [tests/workers/test_face.py](file:///e:/Projects/Yaadein/tests/workers/test_face.py)

To run the worker tests:
```bash
poetry run pytest tests/workers/
```
