# Yaadein Backend 📸🎥

Yaadein is an AI-powered event photo and video sharing platform designed to collect, manage, and share event memories in real-time. This repository houses the stateless FastAPI backend, background Celery processing pipelines, and database schemas supporting table partitioning, pgvector face embeddings, and S3/Cloudflare R2 local emulation.

---

## 📖 Table of Contents

1. [Features](#-features)
2. [Architecture & Tech Stack](#-architecture--tech-stack)
3. [System Prerequisites](#-system-prerequisites)
4. [Directory Structure](#-directory-structure)
5. [Environment Configuration](#-environment-configuration)
6. [Local Development Setup](#-local-development-setup)
7. [Running the Application](#-running-the-application)
8. [Testing & Quality Assurance](#-testing--quality-assurance)
9. [Database Design & Partitioning](#-database-design--partitioning)
10. [DPDP Act Compliance & Consent Guidelines](#-dpdp-act-compliance--consent-guidelines)

---

## ✨ Features

- **Direct-to-R2 Resumable Uploads:** Bypasses API servers for high-concurrency uploads. The client requests batched presigned URLs (incorporating multipart chunking for files >10MB) to upload directly to Cloudflare R2.
- **Real-Time Live Gallery:** Media status changes automatically broadcast to guests and screens via Supabase Realtime WAL-based socket replication.
- **AI Moderation Gate:** All uploaded media undergoes an automatic, asynchronous safety scan via AWS Rekognition prior to landing in the public gallery.
- **Perceptual Duplicate Detection:** Employs 64-bit DCT perceptual hashing (pHash) and XOR-Hamming similarity searches to block duplicate or near-identical image uploads.
- **Privacy-Centric Face Recognition:** Tailored for India's DPDP Act 2023. Generates 512-dimension face vectors via pgvector that are isolated per event and auto-purged on expiry.
- **Static & Dynamic Albums:** Allows users to view static hand-picked collections or dynamic galleries dynamically filtered by face clusters.
- **Asynchronous ZIP Exports:** Bundles and packages full events or album media into ZIP archives in the background using Celery workers.
- **Overage Guardrail:** Restricts downloads to 500 images on basic plans but keeps accepting uploads mid-event to preserve client experience.

---

## 🛠️ Architecture & Tech Stack

| Layer | Component |
| --- | --- |
| **Backend Framework** | FastAPI (Python 3.14) |
| **ASGI Server** | Uvicorn |
| **Relational Database** | PostgreSQL + pgvector (Hosted on Supabase) |
| **Distributed Task Queue** | Celery + Redis (Message broker & result backend) |
| **Object Storage** | Cloudflare R2 (Local MinIO emulation) |
| **Database Migrations** | Alembic (SQLAlchemy ORM integration) |
| **Linter & Formatter** | Ruff |
| **Type Checker** | Mypy (Strict mode) |

---

## 📋 System Prerequisites

Before running the project locally, install:
- **Python >= 3.14**
- **Poetry** (Python dependency management)
- **Docker & Docker Compose** (for database, Redis, and storage containerization)
- **AWS CLI / AWS Credentials** (if using AWS Rekognition moderation)

---

## 📂 Directory Structure

Here is a breakdown of the Yaadein workspace layout:

```text
├── .agents/                    # Custom agent instructions, rules, and workflows
├── .github/                    # CI/CD pipelines (e.g. tests running on main merge/PRs)
├── docs/                       # Architectural Decision Records (ADRs) & documentation guides
│   ├── adr/                    # Design logs for core technical decisions
│   │   ├── 0002-media-table-hash-partitioning.md
│   │   ├── 0003-db-at-rest-encryption-only.md
│   │   ├── 0004-batched-multipart-upload-presign.md
│   │   ├── 0005-albums-table-partitioning.md
│   │   ├── 0006-split-bucket-storage-access-control.md
│   │   ├── 0007-perceptual-duplicate-detection.md
│   │   └── 0008-use-supabase-auth.md
│   ├── api_design_guide.md     # Production REST API contracts and endpoints spec
│   ├── schema.sql              # Clean reference PostgreSQL database schema
│   ├── tasks.md                # Development roadmap divided into feature phases
│   └── yaadein-steering-doc-v2.md # Core steering and product architecture rules
├── src/                        # Primary application source
│   ├── api/                    # HTTP layer and endpoints routing
│   │   ├── deps.py             # Shared dependencies (authentication, DB sessions)
│   │   └── v1/                 # Versioned REST endpoints (auth, events, media, uploads, etc.)
│   ├── migrations/             # Alembic database migrations tracking
│   ├── models/                 # SQLAlchemy ORM models mapping partitioned database tables
│   ├── schemas/                # Pydantic schemas for data serialization and validation
│   ├── services/               # Integrations (AWS Rekognition, storage client, image utils)
│   ├── workers/                # Celery background workers entry points and setup
│   │   ├── app.py              # Celery app configuration and periodic schedules
│   │   └── tasks/              # Individual worker tasks (media processing, face clustering)
│   ├── config.py               # Settings loader using Pydantic Settings
│   ├── database.py             # SQLAlchemy async engine and sessionmaker config
│   └── main.py                 # FastAPI application initializer
├── tests/                      # Python Pytest suite
│   ├── api/                    # REST endpoint verification tests
│   ├── services/               # Core business services unit tests
│   ├── workers/                # Background worker integration tests
│   └── conftest.py             # Async client setup and database fixtures
├── Dockerfile                  # Multi-stage production container setup (API and Worker)
├── docker-compose.yml          # Local developer container services (Postgres, Redis, MinIO)
├── pyproject.toml              # Project dependencies, packaging, and tooling configs
└── poetry.lock                 # Poetry dependency lockfile
```

---

## ⚙️ Environment Configuration

Copy or create a `.env` file at the project root with the following parameters:

```env
# Database & Cache Broker
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/yaadein
REDIS_URL=redis://localhost:6379/0

# Object Storage (Local MinIO defaults matches docker-compose)
R2_BUCKET_NAME=yaadein-bucket
R2_ENDPOINT_URL=http://localhost:9000
R2_ACCESS_KEY_ID=minioadmin
R2_SECRET_ACCESS_KEY=minioadmin

# JWT Authentication
SUPABASE_JWT_SECRET=dummy_supabase_jwt_secret_for_local_development_must_be_changed

# AWS Rekognition (Image Moderation API)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
```

---

## 🚀 Local Development Setup

Follow these commands to configure the project locally:

### 1. Spin Up Infrastructure
Start the local database (PostgreSQL with `pgvector`), message queue broker (Redis), and local S3 emulation (MinIO) in the background:
```bash
docker compose up -d
```
Verify that all services report healthy:
- **MinIO Console URL:** `http://localhost:9001` (Credentials: `minioadmin` / `minioadmin`)

### 2. Install Project Dependencies
Use Poetry to construct a local virtual environment and retrieve library packages:
```bash
poetry install
```

### 3. Apply Schema Migrations
Initialize database tables, sync triggers, and the 64 hash-partitions for media/albums using Alembic:
```bash
poetry run alembic upgrade head
```

---

## 🏃 Running the Application

### 1. Run the FastAPI Web Server
Launch the ASGI web app using Uvicorn:
```bash
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```
- **Swagger UI Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentations:** `http://localhost:8000/redoc`

### 2. Run Celery Workers
Start processing uploaded media files, generating thumbnails, running safety filters, and creating face vector representations:
```bash
poetry run celery -A src.workers.app.celery_app worker --loglevel=info
```

### 3. Run Celery Beat Scheduler
Trigger daily/periodic tasks (such as the daily face clustering pipeline run):
```bash
poetry run celery -A src.workers.app.celery_app beat --loglevel=info
```

---

## 🧪 Testing & Quality Assurance

Run the test suite using pytest to assert backend correctness:
```bash
poetry run pytest
```

Execute code formatting checks and strict static typing checks:
```bash
# Linting
poetry run ruff check

# Type checking
poetry run mypy src/
```

---

## 🗄️ Database Design & Partitioning

To sustain massive transaction loads during popular events without table lockups, we implement the following:

- **Hash Partitioning:** The core `media`, `albums`, and `album_media` tables are hash-partitioned into **64 separate partition tables** based on their `event_id` column.
- **Supabase User Sync Trigger:** Standard users are automatically synced into `public.users` via a Postgres trigger (`on_auth_user_created`) listening to `auth.users` row creations.
- **Hot Caching:** Relies on `gallery_cache` tables and Redis caching to offload live joins during peak event gallery reads.

For design rationale, view the **Architectural Decision Records** at [docs/adr](file:///e:/Projects/Yaadein/docs/adr/).

---

## 🛡️ DPDP Act Compliance & Consent Guidelines

The platform implements stringent mechanisms to adhere to India's **Digital Personal Data Protection (DPDP) Act 2023** concerning biometric face data:
1. **Double Opt-In Required:** Face-recognition is strictly disabled by default. The host must enable it at the event level, and each guest must explicitly check an opt-in consent box before uploading media.
2. **Encrypted Isolation:** Biometric face vectors are stored in a separate table (`face_embeddings`) using pgvector, and search queries are strictly bounded to prevent cross-event pooling.
3. **Automatic Erasure:** Biometric face templates are automatically purged along with the event retention policies or when guest consent is revoked.
