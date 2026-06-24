# Product Steering Document

## Yaadein — AI-Powered Event Photo & Video Sharing Platform

**Version 2** — updated to incorporate architecture review, scaling/compliance fixes, database hosting decision, and upload resilience spec.

---

## Product Vision

Build a modern event media sharing platform that enables event hosts, wedding organizers, photographers, and guests to seamlessly collect, manage, share, discover, and preserve event memories.

The platform should eliminate fragmented sharing through WhatsApp, Google Drive, Telegram, and other messaging apps by providing a centralized, mobile-first experience.

Primary target market:

- Indian Weddings
- Engagements
- Birthday Parties
- Corporate Events
- Conferences
- College Festivals
- Community Events

---

## Core Problem Statement

Event guests capture thousands of photos and videos.

Current workflow:

- Photos scattered across WhatsApp groups
- Media quality compressed
- Difficult to collect content
- Duplicate photos everywhere
- No centralized gallery
- Event organizers lose valuable memories

The platform should solve this by providing:

- QR-based uploads
- Real-time galleries
- AI-powered organization
- Easy downloads
- Photographer collaboration

**Note:** Since the core problem is "WhatsApp fatigue," WhatsApp cannot be absent from the solution. See [Growth & Distribution Strategy](#growth--distribution-strategy) — the share-back loop into WhatsApp is the primary acquisition channel, not an afterthought.

---

## High-Level Technical Architecture

| Layer | Choice |
|---|---|
| Frontend | Next.js |
| Backend | FastAPI |
| Database | Postgres, hosted on **Supabase** (see [Database & Hosting Decision](#database--hosting-decision)) |
| Object Storage | Cloudflare R2 |
| Queue | Redis |
| Workers | Celery Workers |
| Realtime | Supabase Realtime (WAL-based, replaces a self-managed WebSocket layer) |
| CDN | Cloudflare CDN |
| Vector Search | pgvector (via Supabase) for face-embedding similarity |

---

## Architecture Principles

AI should follow these rules:

### Rule 1 — Never route media uploads through backend servers

Required flow:

```
Client
 ↓
Signed Upload URL(s)
 ↓
Cloudflare R2 (multipart)
 ↓
HEAD verification + Metadata Registration
 ↓
Background Processing
```

### Rule 2 — Backend must remain stateless for compute

Avoid local filesystem storage. Use only object storage. Realtime/connection state is delegated to Supabase Realtime, not held in FastAPI processes — this is what keeps "stateless backend" and "live gallery updates" compatible.

### Rule 3 — All heavy processing must be asynchronous

Examples: thumbnail generation, ZIP exports, face recognition, duplicate detection, notifications, video transcoding. Always via background workers (Celery), autoscaled on **queue depth**, not a fixed worker count.

### Rule 4 — System should support 100 → 1,000 → 10,000 concurrent uploads without architectural rewrites

This requires, explicitly:
- PgBouncer / Supavisor connection pooling in front of Postgres
- Celery autoscaling tied to queue depth
- Redis-backed cache for any single event experiencing a traffic spike (a "hot wedding" should not hammer Postgres directly — serve cached gallery reads)
- `media` table partitioned/indexed by `event_id` from day one, since ~95% of queries are scoped to a single event

### Rule 5 — The database layer must stay swappable

**FastAPI is the only thing permitted to issue real queries against the database.** Supabase is used for: Postgres, Realtime, Row Level Security, and pgvector. Supabase's auto-generated REST/GraphQL API and Supabase Auth are **not** to be called directly by the frontend or Celery workers for core domain logic.

This keeps migration to self-hosted Postgres (or RDS/Citus/Neon at scale) a `pg_dump` + connection-string change — not a rewrite. Decide **now**, deliberately, whether session/auth uses Supabase Auth or a self-rolled JWT system in FastAPI — this is the one piece that is expensive to swap retroactively, so it should not be decided by default.

### Rule 6 — Uploads must survive bad networks and crowds, not just R2 itself

See [Media Upload Resilience Spec](#media-upload-resilience-spec) for the full requirement set (chunking, retry, concurrency caps, rate limiting, idempotency, orphan cleanup).

---

## Database & Hosting Decision

**Decision: Supabase-hosted Postgres**, not raw self-hosted Postgres, for the current build phase.

Rationale:
- Supabase Realtime (WAL-based) solves live gallery/slideshow updates without standing up a separate WebSocket/pub-sub service
- Row Level Security maps directly onto "guest sees only event X," "host manages only their events" — replacing hand-rolled multi-tenant RBAC
- pgvector ships built-in for face-embedding similarity search — no separate vector DB
- Supavisor gives connection pooling out of the box at upload-spike volumes

Known limits to plan around:
- At ~10,000 events/month, custom sharding/read-replica tuning may need more control than the managed layer gives — revisit self-hosted Postgres (RDS Aurora, Citus, Neon) at that point
- This is a config/infra change, not a rewrite, **only if Rule 5 is followed** (FastAPI as the only door to the data)

---

## User Personas

### Event Host
Creates events. Manages gallery, downloads memories, moderates uploads.
**Goals:** Collect guest photos, preserve memories, share galleries.

### Guest
Joins via QR code. Uploads photos/videos, browses gallery.
**Goals:** Share captured moments, with zero friction on bad venue wifi.

### Photographer
Professional vendor. Uploads professional media, manages client galleries.
**Goals:** Deliver photos, upsell services. (Primary B2B2C growth channel — see below.)

### Admin
Platform operator. Manages users, subscriptions, abuse moderation.
**Goals:** Platform growth, revenue generation.

---

## Core Domain Modules

### Event Management Module
Create / edit / delete / archive event, settings, branding, visibility.
**Outputs:** Event ID, Event Slug, Event QR Code.

### QR Sharing Module
Generate, download, print QR. Track scan count, unique visitors, upload conversion rate.

### Media Upload Module
Image/video/batch/drag-drop/mobile upload. **Requirements:** original quality, resumable multipart uploads, real-time progress. Full resilience spec below.

### Gallery Module
Infinite scroll, masonry grid, albums, filters, search. Images and videos. Reads should hit a Redis-backed cache, not Postgres directly, for any event under load.

### Moderation Module
**Day-1 requirement, not "future":** every upload passes through a blocking NSFW/abuse classifier (e.g., Rekognition or an open-source equivalent) before it's visible in the gallery. Default to auto-publish for trusted hosts; host-approval mode is opt-in. A human review queue does not scale to "wedding happening right now" and is not the day-1 plan.

### Slideshow Module
Real-time slideshow, auto-refresh, TV mode for reception displays. Powered by Supabase Realtime, not a custom WebSocket layer.

### Download Module
Single image, album, full event ZIP export — all generated asynchronously via Celery.

---

## AI Feature Modules

### Face Recognition Module
**Purpose:** Find all photos of a specific person.

**Mandatory constraints (not optional, given biometric data under India's DPDP Act 2023):**
- **Opt-in per event** — host explicitly enables face search for their event
- **Opt-in per guest** — a single, visible checkbox at upload time, not buried in T&Cs
- Embeddings stored in a **separate, encrypted table**, never pooled across events (no global face index — a cross-event index is a stalking vector, not just a compliance risk)
- Embeddings auto-purge on the same retention schedule as the event's media

### Duplicate Detection Module
Perceptual hashing + similarity matching to remove redundant uploads.

### Smart Album Module
Auto-create albums: Bride, Groom, Stage, Ceremony, Reception, Family, Friends.

### Smart Search Module
Natural-language queries: "show selfies," "show stage photos," "show bride photos."

---

## Media Upload Resilience Spec

Direct-to-R2 upload is correct, but a single presigned PUT is **not sufficient** on its own. Required layers:

### 1. Chunked, resumable uploads
- Use R2's S3-compatible **multipart upload API**: split files into ~5–10MB chunks, request a presigned URL **per chunk**
- A single PUT for a 200MB wedding video over venue wifi will fail routinely — chunking means a failed chunk is retried alone, not the whole file
- `tus-js-client` (or equivalent) for resumability across page reloads, not just mid-session retries

### 2. Retry logic
- Exponential backoff per chunk (1s → 2s → 4s...), capped at ~5 attempts before surfacing a "tap to retry" state to the guest
- Never retry the whole file on a single chunk failure

### 3. Bulk / concurrent upload handling
- Batch the presigned-URL request — one API call returning N URLs for N files, not N separate calls
- Cap client-side concurrency to ~4–6 simultaneous file uploads regardless of selection size
- Rate-limit the presigned-URL endpoint **per-event and per-device** (token bucket), not globally — one viral event should not throttle every other event on the platform

### 4. Ad-hoc failure handling
- **Orphaned multipart uploads:** set an R2 lifecycle rule to auto-abort incomplete multipart uploads after ~24h
- **Unverified "done" signals:** never trust the client's completion callback — issue a `HEAD` request against R2 to confirm the object exists and matches expected size before creating the media record
- **Duplicate uploads on retry:** generate a client-side idempotency key (hash of file + event + guest) so a retried confirm call can't create duplicate media rows
- **Virus/NSFW scanning:** runs **after** the object lands in R2 and is `HEAD`-verified, triggered as a worker job, before the media is marked visible in the gallery (the file bypasses the backend on the way in, so scanning can't happen pre-upload)

Flow stays: **client → presigned URL(s) → R2 (multipart) → HEAD-verify → confirm (idempotent) → queue worker (scan, thumbnail, transcode) → gallery.**

---

## Detailed Upload Use Case

**Actor:** Guest
**Precondition:** Guest opens event page (via QR scan or link).

**Main flow:**
1. Guest selects files
2. Client requests batched presigned multipart URLs for all files in one call (rate-limited per event/device)
3. Client uploads chunks directly to R2, with per-chunk retry and backoff
4. On completion, client sends an idempotent "confirm" call per file
5. Backend issues `HEAD` against R2 to verify object existence/size before trusting the confirm
6. Media record created; processing jobs queued (NSFW scan → thumbnail → transcode if video)
7. Gallery updates in real time via Supabase Realtime once the media passes moderation

**Success criteria:** Upload completes; media appears in gallery after passing the moderation gate.

**Failure cases:**
- Network interruption mid-chunk → chunk-level retry, not file-level
- Invalid file type → rejected before any presigned URL is issued
- Upload timeout / abandoned upload → R2 lifecycle rule cleans up after 24h
- Duplicate confirm call → idempotency key prevents duplicate records

---

## Database Domain Model

Core entities: Users, Events, Albums, Media, Guests, QR Codes, Comments, Reactions, Notifications, Subscriptions, Payments, Face Embeddings, Exports.

Additional constraints:
- `media` table partitioned/indexed by `event_id` (the dominant access pattern)
- `face_embeddings` lives in a separate, encrypted table, never joined across events, with its own retention/purge job
- A `gallery_cache` (Redis or materialized table) per event, refreshed on write, to avoid live joins on every gallery read for hot events

---

## API Design Principles

Backend exposes REST APIs:

```
/api/v1/events
/api/v1/media
/api/v1/uploads
/api/v1/gallery
/api/v1/slideshow
/api/v1/admin
```

**Requirements:** JWT authentication (decision: Supabase Auth vs. self-rolled — make explicitly per Rule 5), role-based authorization, pagination, filtering, versioning.

---

## Scalability Requirements

| Phase | Target |
|---|---|
| Phase 1 | 100 events/month |
| Phase 2 | 1,000 events/month |
| Phase 3 | 10,000 events/month |

Architecture scales horizontally via: PgBouncer/Supavisor pooling, Celery autoscaling on queue depth, Redis caching for hot events, and `event_id`-partitioned data from day one (see Rule 4).

---

## Security Requirements

Mandatory:
- JWT authentication
- Signed upload URLs (multipart, short-lived, scoped per chunk)
- Rate limiting — per event and per device on the presigned-URL endpoint
- Upload validation (file type/size before URL issuance)
- Virus/NSFW scanning post-landing, pre-gallery-visibility
- RBAC authorization (via Postgres RLS)
- Secure downloads
- Encrypted-at-rest storage for face embeddings, with consent gating and scheduled purge
- R2 lifecycle policy to abort/clean orphaned multipart uploads

---

## Monetization Model

| Plan | Includes |
|---|---|
| Basic | 500 photos, 30 days storage |
| Premium | Unlimited photos + videos, 1 year storage |
| Professional | Photographer plan, white label, multiple events |

**Overage policy (required, not implicit):** Never hard-block guest uploads mid-event when a cap is hit. Keep accepting uploads; auto-send the host a one-tap upgrade link (via WhatsApp/email); gate only the **download** of overage media until upgraded. Blocking uploads mid-wedding is a permanent churn event for the host.

---

## Growth & Distribution Strategy

This is the actual differentiator, not a feature module:

- **WhatsApp share-back loop:** every gallery includes a branded "share to WhatsApp" deep link with a watermarked preview — this is free, viral distribution back into the exact channel the product is meant to replace
- **WhatsApp notifications:** "your photos are ready," "47 new photos uploaded" nudges sent via WhatsApp Business API for host re-engagement (directly reusable infrastructure from the separate WhatsApp middleware platform work)
- **Photographer B2B2C channel:** photographers as a distribution wedge — every wedding they shoot becomes a new paying event, with an upsell path to white-label for their business
- Vertical focus: own Indian weddings before expanding to other event types; AI smart albums/face search are retention features for later, not the initial wedge

---

## Data Lifecycle & Compliance

- **DR/backup:** cross-cloud backup (R2 + a second object store/cold storage) for any event tagged as a wedding — irreplaceable content needs redundancy beyond a single vendor's SLA
- **Retention reminders:** T-30/T-7/T-1 expiry notifications before media deletion
- **Monetized archive tier:** a "forever archive" paid tier turns the data-loss liability into a revenue line
- **Biometric data (face embeddings):** DPDP Act 2023 compliance — explicit opt-in, encrypted storage, no cross-event pooling, scheduled erasure (see Face Recognition Module above)

---

## Non-Functional Requirements

**Availability:** 99.9%

**Performance:**
- Gallery load < 2 sec (served from cache for active events)
- Upload start < 1 sec
- Thumbnail generation < 10 sec — **images only**
- Video processing (scan + transcode) — separate SLA, ~1–2 min, shown as a "processing" badge; never blocks gallery view

**Security:** OWASP compliant

**Mobile Experience:** Mobile-first, designed for poor venue connectivity as the default condition, not the edge case

---

## Instructions for AI

When generating specifications from this document, always produce:

1. User Stories
2. Acceptance Criteria
3. API Contracts
4. Database Schemas
5. Sequence Diagrams
6. Edge Cases
7. Security Considerations
8. Scaling Considerations
9. Monitoring Requirements
10. Implementation Tasks

For every feature module, provide: Business Objective, Actors, Preconditions, Main Flow, Alternative Flows, Failure Flows, API Design, Database Design, Worker Design, Testing Strategy.

**Do not re-derive decisions already made in this document.** Specifically:
- Database access goes through FastAPI only (Rule 5) — do not propose direct frontend-to-Supabase calls for core domain logic
- Uploads are chunked/multipart with per-chunk retry, idempotent confirmation, and post-landing scanning (Media Upload Resilience Spec) — do not propose a single-shot PUT flow
- Moderation is a blocking classifier at launch, not a human queue (Moderation Module)
- Face recognition requires double opt-in and isolated storage (Face Recognition Module) — do not propose a global face index
- `media` is partitioned by `event_id` from the first schema (Database Domain Model)

This steering document is the single source of truth for generating detailed PRDs, use cases, epics, Jira stories, backend APIs, database design, and implementation plans for the event photo-sharing platform.
