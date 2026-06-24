# Task List: Yaadein Backend Implementation

This checklist is structured to be highly parsable by AI IDE agents. Each task outlines code locations, target schemas, strict requirements, dependencies, and validation commands.

---

## Phase 1: Project Scaffolding & CI/CD Setup

- [ ] **Task 1.1: Dependency Scaffolding**
  - **Action**: Create `pyproject.toml` specifying Poetry/Rye backend configuration.
  - **Dependencies**: None.
  - **Key Packages**: `fastapi`, `uvicorn`, `sqlalchemy[mypy]`, `psycopg[binary]`, `celery`, `redis`, `pydantic-settings`, `boto3` (R2 client), `pillow` (image scaling), `imagehash` (pHash), `pgvector` (vector mappings), `pytest`, `httpx` (async test client).
  - **Verification**: Run `poetry install` (or equivalent package manager build).

- [ ] **Task 1.2: Local Development Docker Environment**
  - **Action**: Create `docker-compose.yml` to define Postgres database, Redis queue backend, and MinIO storage service.
  - **Environment specs**:
    - Postgres: Image `ankane/pgvector:v0.5.1` (or latest Postgres image with pgvector preloaded). Port `5432`.
    - Redis: Image `redis:7-alpine`. Port `6379`.
    - MinIO (Mock Cloudflare R2): Image `minio/minio`. Port `9000` (API) and `9001` (Console).
  - **Verification**: Run `docker compose up -d` and assert all services report healthy status.

- [ ] **Task 1.3: Multi-Stage Production Dockerfile**
  - **Action**: Create `Dockerfile` and `.dockerignore`.
  - **Specs**:
    - Base stage: Python 3.11/3.12 light build.
    - Stage 1: Build dependency layer (`poetry export` to requirements, pip install).
    - Stage 2 (API runner): Expose port `8000`, command `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
    - Stage 3 (Worker runner): Command `celery -A src.workers.app.celery_app worker --loglevel=info`.
  - **Verification**: Run `docker build --target api -t yaadein-api .` and `docker build --target worker -t yaadein-worker .`.

- [ ] **Task 1.4: CI Pipeline Setup**
  - **Action**: Create `.github/workflows/test.yml`.
  - **Specs**: Triggers on pull requests and pushes to `main`. Installs code, runs `ruff check`, `mypy src/`, and `pytest`.
  - **Verification**: Commit configurations and verify GitHub Action tests pass.

---

## Phase 2: Database Models & Supabase Auth Integration

- [ ] **Task 2.1: Configuration Settings & Database Connections**
  - **Action**: Create `src/config.py` and `src/database.py`.
  - **Specs**:
    - `src/config.py`: Build Pydantic `BaseSettings` parsing `DATABASE_URL`, `REDIS_URL`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `SUPABASE_JWT_SECRET`.
    - `src/database.py`: Configure SQLAlchemy engine with pool configuration (`pool_size=20`, `max_overflow=10`) and create `sessionmaker`.
  - **Verification**: Run a sanity script verifying connection to target Postgres instance.

- [ ] **Task 2.2: ORM Declarative Models**
  - **Action**: Create files under `src/models/` mapping directly to the schemas defined in [schema.sql](file:///e:/Projects/Yaadein/docs/schema.sql).
  - **Strict Constraints**:
    - `media` table must have composite primary key `(event_id, id)` and partition annotations for SQLAlchemy.
    - `albums` and `album_media` tables must have composite primary keys `(event_id, id)` and `(event_id, album_id, media_id)` respectively.
    - Define matching composite foreign keys on all partitioned targets.
  - **Verification**: Code compilation and validation checks on ORM imports.

- [ ] **Task 2.3: Database Migrations Setup**
  - **Action**: Initialize Alembic using `alembic init -t async src/migrations`.
  - **Specs**: Modify `src/migrations/env.py` to import SQLAlchemy base models for auto-generation.
  - **Verification**: Run `alembic revision --autogenerate -m "initial_schema"`.

- [ ] **Task 2.4: Supabase Sync Triggers & Partition Initialization**
  - **Action**: Add custom raw SQL commands to the generated Alembic migration file.
  - **Specs**:
    - Add DDL to create the 64 partition tables for `media`, `albums`, and `album_media`.
    - Add DDL to create function `public.handle_new_user()` and matching trigger `on_auth_user_created` on `auth.users`.
  - **Verification**: Execute `alembic upgrade head` and verify table schema inside database.

- [ ] **Task 2.5: Supabase JWT Verification Middleware**
  - **Action**: Implement JWT checking inside `src/api/deps.py`.
  - **Specs**:
    - Extract bearer token from HTTP `Authorization` header.
    - Verify signature using HS256 algorithm and `settings.SUPABASE_JWT_SECRET`.
    - Retrieve corresponding user row from `public.users` table using the `sub` UUID claim.
  - **Verification**: Write unit test passing mocked Supabase JWT and assert current user returns successfully.

---

## Phase 3: Event & Guest Registration Flow

- [ ] **Task 3.1: Event Management Endpoints**
  - **Action**: Create `src/api/v1/events.py` and `src/schemas/event.py`.
  - **API routes**:
    - `POST /events`: Creates an event (requires host authentication).
    - `GET /events`: Lists events owned by current host (requires host auth).
    - `GET /events/slug/{slug}`: Fetches public event settings (unauthenticated).
    - `PUT /events/{id}`: Updates event branding and features (requires host auth).
  - **Verification**: Run API requests via Pytest or Curl, verifying database state changes.

- [ ] **Task 3.2: Guest Session Setup & Consent API**
  - **Action**: Create `src/api/v1/auth.py` and `src/schemas/user.py`.
  - **API routes**:
    - `POST /events/{event_id}/guests`: Registers guest details (guest session ID, name, phone, face search consent flag). Inserts rows into `guests` and `face_consents` tables.
  - **Verification**: Send request with `guest_session_id` and name; assert corresponding rows appear in `guests` and `face_consents` tables.

---

## Phase 4: R2 Storage & Upload Resilience

- [ ] **Task 4.1: Cloudflare R2 Storage Client Integration**
  - **Action**: Create `src/services/storage.py`.
  - **Specs**:
    - Build wrapper around `boto3.client("s3")` passing target Cloudflare R2 endpoint URL and keys.
    - Implement `generate_presigned_upload_url(object_key)` and `generate_presigned_multipart_upload_urls(object_key, file_size)`.
  - **Verification**: Write unit tests executing local presigning mocks.

- [ ] **Task 4.2: Batched Presigned URLs Endpoint**
  - **Action**: Create `src/api/v1/uploads.py` and `src/schemas/upload.py`.
  - **API route**:
    - `POST /uploads/presign`: Accepts batch payload of files. Calculates chunks dynamically (10MB target) for files >10MB, calls storage service, and returns chunk presigned URLs and S3 upload IDs.
  - **Verification**: Send request with files over and under 10MB; verify returned JSON contains matching S3 parts.

- [ ] **Task 4.3: Upload Confirmation Endpoint**
  - **Action**: Create `src/api/v1/media.py` (confirm route) and `src/schemas/media.py`.
  - **API route**:
    - `POST /media/confirm`: Receives object key and idempotency key. Executes `s3_client.head_object()` against R2 to confirm file exists and size matches. Creates row in `media` table with status `'pending_verify'` and dispatches processing worker.
  - **Verification**: Mock successful `head_object` check and verify celery task dispatch.

- [ ] **Task 4.4: Image Processing Celery Task**
  - **Action**: Create `src/workers/tasks/media.py`.
  - **Specs**:
    - Download image from R2.
    - Downsize to **400px width WebP** (Thumbnail) and **1600px width WebP** (Preview).
    - Upload generated images to public R2 paths.
  - **Verification**: Execute task locally and check outputs on MinIO.

---

## Phase 5: Moderation & Perceptual Duplicate Detection (pHash)

- [ ] **Task 5.1: AWS Rekognition Moderation Client**
  - **Action**: Create `src/services/moderation.py`.
  - **Specs**: Integrate `boto3.client("rekognition")` to call `detect_moderation_labels` on R2 image objects. Filter for unsafe labels.
  - **Verification**: Mock safe/unsafe responses and assert check outcomes.

- [ ] **Task 5.2: Perceptual Hashing (pHash)**
  - **Action**: Create `src/services/images.py` pHash helper.
  - **Specs**: Using `pillow` and `imagehash` library, generate 64-bit DCT pHash from loaded image stream. Convert output to a 64-character binary bitstring.
  - **Verification**: Pass sample identical but resized images and assert generated binary hashes are identical.

- [ ] **Task 5.3: XOR-Hamming Duplicate Search Query**
  - **Action**: Add database lookup method in SQLAlchemy.
  - **Specs**: Execute query `SELECT id FROM media WHERE event_id = :event_id AND bit_count(phash # :incoming_phash) <= 10` using raw SQL statement bindings inside model.
  - **Verification**: Run duplicate image check against a seeded database containing visually similar photos.

- [ ] **Task 5.4: Processing Task Pipeline Stitching**
  - **Action**: Update `process_image_upload` celery task to run moderation scan and duplicate check in sequence.
  - **Specs**: Transition media status to `'visible'` if safe and unique, `'rejected'` if unsafe, or `'duplicate'` if duplicate.
  - **Verification**: Run complete processing pipeline for safe, unsafe, and duplicate image test cases.

---

## Phase 6: Face Recognition & Custom Albums

- [ ] **Task 6.1: Biometric Opt-in Verification**
  - **Action**: Add check in guest registration endpoints. Ensure face templates are only generated if guest has valid `face_consents` record.
  - **Verification**: Ensure no face embedding task is dispatched for non-consenting guests.

- [ ] **Task 6.2: Face Embedding Generation Task**
  - **Action**: Create `src/workers/tasks/face.py` (embedding task).
  - **Specs**:
    - Extract face bounding boxes and generate 512-dimension float vectors (using dlib/insightface model).
    - Save records to `face_embeddings` table with pgvector format.
  - **Verification**: Pass testing photo and assert correct float coordinates saved in DB.

- [ ] **Task 6.3: Daily Face Clustering Batch Job**
  - **Action**: Create celery periodic task `cluster_faces_job` running daily.
  - **Specs**: Fetch all embeddings for active event, group vectors using DBSCAN or k-means, write cluster listings to `face_clusters` and update `face_embeddings.cluster_id`.
  - **Verification**: Seed mock vectors and verify clustering outputs cluster groupings correctly.

- [ ] **Task 6.4: Albums Management Endpoints**
  - **Action**: Create `src/api/v1/albums.py` and `src/schemas/album.py`.
  - **API routes**:
    - `POST /events/{event_id}/albums`: Create dynamic (based on list of cluster IDs) or static (based on list of media IDs) albums.
    - `GET /events/{event_id}/albums`: List all albums.
    - `GET /events/{event_id}/albums/{album_id}`: Fetch media items matching the album criteria (filtering dynamic face templates or static junction items).
  - **Verification**: Create static/dynamic albums and request contents; assert correct records returned.

---

## Phase 7: Downloads, Overage, and Slideshow Integration

- [ ] **Task 7.1: Gated Original Download Endpoint**
  - **Action**: Create `src/api/v1/downloads.py`.
  - **API route**:
    - `GET /media/{event_id}/{media_id}/download`: Counts event media rows created prior to the current item's creation timestamp. If count exceeds limit (500 for Basic), blocks with `403 Forbidden`. If clean, generates temporary R2 presigned download URL and returns a 307 redirect.
  - **Verification**: Assert download request for 501st photo on Basic event plan returns `403 Forbidden`.

- [ ] **Task 7.2: Async ZIP Export Task**
  - **Action**: Create `src/workers/tasks/media.py` (zip task).
  - **Specs**:
    - Celery task fetches all visible media urls for target event or album.
    - Bundles objects into a ZIP file in worker disk.
    - Uploads ZIP to private exports R2 path and updates `exports` table status.
  - **Verification**: Dispatch export task, verify zip lands on R2, and verify download URL works.

- [ ] **Task 7.3: Supabase Realtime Replication Config**
  - **Action**: Configure Postgres publication.
  - **Specs**: Run SQL command `ALTER PUBLICATION supabase_realtime ADD TABLE media;` during migration.
  - **Verification**: Assert local client connection to Supabase Realtime socket receives push event updates when a new media row is added.
