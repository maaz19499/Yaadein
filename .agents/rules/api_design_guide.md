# Yaadein API Design Guide

This guide specifies the production-ready REST API endpoints, JSON payloads, headers, query parameters, and auth requirements for the Yaadein backend.

---

## Global API Standards

- **Base URL**: `/api/v1`
- **Content-Type**: `application/json`
- **Authentication**:
  - **User Endpoints**: Authenticated via standard `Authorization: Bearer <supabase_jwt>` in request headers. FastAPI verifies the JWT signature and extracts the user's ID (`sub` claim) and links it to our public `users` profile.
  - **Guest Endpoints**: Unauthenticated, but requires `X-Guest-Session-ID` and `X-Event-ID` headers to prevent cross-event scanning or unauthorized access.

---

## 1. Authentication & Profiles

### GET `/auth/me`
Fetches the public profile of the authenticated Host/Photographer.
- **Authentication**: Required (JWT)
- **Response `200 OK`**:
```json
{
  "id": "u1-uuid-1234",
  "phone": "+919876543210",
  "name": "Priya Sharma",
  "role": "host",
  "created_at": "2026-06-23T12:00:00Z"
}
```

### PUT `/auth/profile`
Updates the name and details of the profile.
- **Authentication**: Required (JWT)
- **Request Body**:
```json
{
  "name": "Priya Rahul Sharma"
}
```
- **Response `200 OK`**:
```json
{
  "id": "u1-uuid-1234",
  "phone": "+919876543210",
  "name": "Priya Rahul Sharma",
  "role": "host",
  "created_at": "2026-06-23T12:00:00Z"
}
```

---

## 2. Event Management

### POST `/events`
Creates a new event.
- **Authentication**: Required (JWT, Role: Host/Photographer)
- **Request Body**:
```json
{
  "slug": "priya-rahul-wedding",
  "is_wedding": true,
  "face_search_enabled": false
}
```
- **Response `201 Created`**:
```json
{
  "id": "e1-uuid-5678",
  "host_id": "u1-uuid-1234",
  "slug": "priya-rahul-wedding",
  "plan": "basic",
  "face_search_enabled": false,
  "is_wedding": true,
  "storage_expires_at": "2026-07-23T12:00:00Z",
  "created_at": "2026-06-23T12:05:00Z"
}
```

### GET `/events`
Lists all events managed by the currently logged-in host.
- **Authentication**: Required (JWT)
- **Response `200 OK`**:
```json
[
  {
    "id": "e1-uuid-5678",
    "slug": "priya-rahul-wedding",
    "plan": "basic",
    "created_at": "2026-06-23T12:05:00Z"
  }
]
```

### GET `/events/slug/{slug}`
Public configuration lookup. Called by the frontend when a guest scans a QR code (before the guest registers a session).
- **Authentication**: None
- **Response `200 OK`**:
```json
{
  "id": "e1-uuid-5678",
  "slug": "priya-rahul-wedding",
  "face_search_enabled": true,
  "is_wedding": true,
  "plan": "basic"
}
```

---

## 3. Guest Registration

### POST `/events/{event_id}/guests`
Registers a guest session name when scanning the QR code, storing consent and identity data.
- **Authentication**: None
- **Request Body**:
```json
{
  "guest_session_id": "gs-7f2a-uuid-9999",
  "name": "Rahul Mehta",
  "phone": "+919123456780",
  "face_search_consent": true
}
```
- **Response `200 OK`**:
```json
{
  "status": "success",
  "guest": {
    "guest_session_id": "gs-7f2a-uuid-9999",
    "name": "Rahul Mehta",
    "face_search_consent": true
  }
}
```

---

## 4. Media Uploads

### POST `/uploads/presign`
Generates batched presigned URLs for direct-to-R2 uploads. Rate-limited per device and event.
- **Authentication**: None (Requires `X-Guest-Session-ID` / `X-Event-ID` if unauthenticated guest, or standard JWT if host)
- **Request Body**:
```json
{
  "event_id": "e1-uuid-5678",
  "files": [
    {
      "client_file_id": "temp-file-1",
      "file_name": "dance_video.mp4",
      "file_size_bytes": 118293440,
      "mime_type": "video/mp4",
      "checksum": "sha256-a1b2c3d4..."
    },
    {
      "client_file_id": "temp-file-2",
      "file_name": "selfie.jpg",
      "file_size_bytes": 4213880,
      "mime_type": "image/jpeg",
      "checksum": "sha256-e5f6g7h8..."
    }
  ]
}
```
- **Response `200 OK`**:
```json
{
  "files": [
    {
      "client_file_id": "temp-file-1",
      "r2_upload_id": "mp-upload-token-abc123", 
      "r2_object_key": "events/e1/originals/temp-file-1.mp4",
      "idempotency_key": "idem-key-video",
      "chunk_size_bytes": 10485760,
      "chunks": [
        { "part_number": 1, "url": "https://r2.cloudflare.com/..." },
        { "part_number": 2, "url": "https://r2.cloudflare.com/..." }
      ]
    },
    {
      "client_file_id": "temp-file-2",
      "r2_upload_id": null, 
      "r2_object_key": "events/e1/originals/temp-file-2.jpg",
      "idempotency_key": "idem-key-image",
      "chunks": [
        { "part_number": 1, "url": "https://r2.cloudflare.com/..." }
      ]
    }
  ]
}
```

### POST `/media/confirm`
Triggers immediate background verification (`HEAD` check on R2, database registration, and dispatches the Celery moderation pipeline).
- **Authentication**: None (Requires validation headers)
- **Request Body**:
```json
{
  "event_id": "e1-uuid-5678",
  "idempotency_key": "idem-key-image",
  "r2_object_key": "events/e1/originals/temp-file-2.jpg",
  "r2_upload_id": null
}
```
- **Response `202 Accepted`**:
```json
{
  "status": "pending_verify",
  "message": "File registration initialized and processing task queued."
}
```

---

## 5. Gallery Feeds

### GET `/events/{event_id}/gallery`
Fetches a paginated grid of visible gallery items. Hits the Redis-backed gallery cache.
- **Authentication**: None
- **Query Parameters**:
  - `limit` (default: 50)
  - `cursor` (created_at timestamp + ID for pagination offset)
  - `face_cluster_ids` (comma-separated cluster IDs for filtered viewing)
- **Response `200 OK`**:
```json
{
  "media": [
    {
      "id": "m1-uuid-777",
      "type": "image",
      "thumbnail_url": "https://cdn.yaadein.com/thumbnails/m1.webp",
      "preview_url": "https://cdn.yaadein.com/previews/m1.webp",
      "width": 1920,
      "height": 1080,
      "uploaded_by_name": "Rahul Mehta",
      "created_at": "2026-06-23T12:10:00Z"
    }
  ],
  "next_cursor": "2026-06-23T12:10:00Z_m1-uuid-777"
}
```

---

## 6. Albums & Custom Filters

### GET `/events/{event_id}/faces`
Fetches all face clusters identified in this event (only available if `face_search_enabled` is true).
- **Authentication**: None (Requires guest session headers verifying consent)
- **Response `200 OK`**:
```json
[
  {
    "cluster_id": "cl1-uuid-999",
    "matched_guest_name": "Rahul Mehta",
    "cover_thumbnail_url": "https://cdn.yaadein.com/thumbnails/cl1.webp"
  }
]
```

### POST `/events/{event_id}/albums`
Creates a custom static or dynamic album.
- **Authentication**: JWT (Host/Photographer)
- **Request Body (Dynamic Album)**:
```json
{
  "name": "Selfies of Priya",
  "type": "dynamic",
  "dynamic_filters": {
    "face_cluster_ids": ["cl1-uuid-999"]
  }
}
```
- **Response `201 Created`**:
```json
{
  "id": "album-uuid-3333",
  "event_id": "e1-uuid-5678",
  "name": "Selfies of Priya",
  "type": "dynamic",
  "dynamic_filters": {
    "face_cluster_ids": ["cl1-uuid-999"]
  },
  "created_at": "2026-06-23T12:20:00Z"
}
```

---

## 7. Gated Downloads & Exports

### GET `/media/{event_id}/{media_id}/download`
Verifies user subscription status and creation-order overage limits, then generates a temporary, short-lived presigned R2 original download URL redirect.
- **Authentication**: None (Requires guest session validation)
- **Response `307 Temporary Redirect`**:
  - Redirects to `https://r2.cloudflare.com/private-bucket/events/e1/...` with a 5-minute expiry token.
- **Response `403 Forbidden`** (if overage cap hit):
```json
{
  "error": "DOWNLOAD_LOCKED",
  "message": "Event storage limit exceeded. Ask the host to upgrade their plan to unlock high-resolution downloads."
}
```

### POST `/events/{event_id}/exports`
Triggers background ZIP packaging of the event.
- **Authentication**: Required (JWT, Host/Photographer)
- **Request Body**:
```json
{
  "scope": "full_event" // Options: full_event, album
}
```
- **Response `202 Accepted`**:
```json
{
  "export_id": "ex-uuid-0000",
  "status": "queued"
}
```
