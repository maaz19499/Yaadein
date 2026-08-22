# Yaadein API Design & Integration Guide

This guide is the complete REST API contract for the **Yaadein** platform. It specifies all endpoints, HTTP methods, headers, request bodies, query parameters, and response structures for frontend developers integrating with the backend.

---

## Table of Contents
1. [Global API Standards & Authentication](#global-api-standards--authentication)
2. [Authentication & User Profile](#1-authentication--user-profile)
3. [Event Lifecycle Management](#2-event-lifecycle-management)
4. [Guest PIN Gate & Registration](#3-guest-pin-gate--registration)
5. [Media Upload Pipeline (Direct-to-R2)](#4-media-upload-pipeline-direct-to-r2)
6. [Live Gallery & Infinite Scroll](#5-live-gallery--infinite-scroll)
7. [AI Face Recognition & Search](#6-ai-face-recognition--search)
8. [Albums Management](#7-albums-management)
9. [Downloads & Background Exports](#8-downloads--background-exports)
10. [Standard Error Responses](#10-standard-error-responses)

---

## Global API Standards & Authentication

- **Base URL**: `http://localhost:8000/api/v1` (or your deployed backend host `/api/v1`)
- **Content-Type**: `application/json` (except multipart file uploads)
- **JSON Casing**: The backend supports **`camelCase`** (used by the frontend) as well as `snake_case`.
- **Authentication Mechanisms**:
  - **Host / User Endpoints**: Provide Supabase JWT Bearer token in the request headers:
    ```http
    Authorization: Bearer <supabase_access_token>
    ```
  - **Guest Endpoints**: No login required. Pass guest session tracking headers:
    ```http
    X-Guest-Session-ID: <UUID>
    X-Event-ID: <UUID>
    ```

---

## 1. Authentication & User Profile

### `GET /auth/profile`
Fetches the profile of the currently authenticated host/user, including total events created.

- **Auth**: Required (`Bearer <JWT>`)
- **Response `200 OK`**:
```json
{
  "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "email": "host@yaadein.com",
  "name": "Aarav Sharma",
  "avatarUrl": "https://cdn.yaadein.com/avatars/user.jpg",
  "plan": "premium",
  "eventsCreated": 3
}
```

### `PATCH /auth/profile`
Updates the name and avatar of the authenticated user.

- **Auth**: Required (`Bearer <JWT>`)
- **Request Body**:
```json
{
  "name": "Aarav S. Sharma",
  "avatarUrl": "https://cdn.yaadein.com/avatars/new_user.jpg"
}
```
- **Response `200 OK`**: Updated `UserProfile` object.

---

## 2. Event Lifecycle Management

### `POST /events` (Create Event)
Creates a new event with initial configuration. Sets status to `pending` (for paid plans) or `active` (for starter/free). Automatically generates a clean, URL-safe slug if not supplied.

- **Auth**: Required (`Bearer <JWT>`, Host/Admin)
- **Request Body**:
```json
{
  "name": "Rohan & Priya Wedding",
  "type": "wedding",
  "date": "2026-12-15T18:30:00.000Z",
  "city": "Udaipur",
  "coverPhotoUrl": "https://cdn.yaadein.com/covers/wedding.jpg",
  "plan": "premium",
  "guestPin": "4821",
  "enableFaceSearch": true
}
```
- **Response `201 Created`**:
```json
{
  "id": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
  "hostId": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "slug": "rohan-priya-wedding-4k9z",
  "name": "Rohan & Priya Wedding",
  "type": "wedding",
  "date": "2026-12-15T18:30:00.000Z",
  "city": "Udaipur",
  "coverPhotoUrl": "https://cdn.yaadein.com/covers/wedding.jpg",
  "status": "pending",
  "plan": "premium",
  "photoCount": 0,
  "videoCount": 0,
  "guestCount": 0,
  "storageExpiresAt": "2027-03-15T18:30:00.000Z",
  "uploadExpiresAt": "2026-12-29T18:30:00.000Z",
  "expiresAt": "2027-03-15T18:30:00.000Z",
  "faceClustered": false,
  "faceSearchEnabled": true,
  "enableFaceSearch": true,
  "isWedding": true,
  "shareUrl": "/e/rohan-priya-wedding-4k9z",
  "guestPin": "4821",
  "createdAt": "2026-08-22T14:00:00.000Z"
}
```

### `PATCH /events/{event_id}` (Update Event)
Performs partial updates on an event. Used for activating the event after payment (`status: "active"`), editing event details, updating cover photos, or changing PIN.

- **Auth**: Required (`Bearer <JWT>`, Host/Owner)
- **Request Body** (all fields optional):
```json
{
  "status": "active",
  "coverPhotoUrl": "https://cdn.yaadein.com/covers/wedding-hd.jpg",
  "guestPin": "5920",
  "enableFaceSearch": true
}
```
- **Response `200 OK`**: Complete updated `EventResponse` object.

### `GET /events` (List User Events)
Lists all events created by the logged-in host with real-time aggregated photo, video, and guest counts for dashboard cards.

- **Auth**: Required (`Bearer <JWT>`)
- **Response `200 OK`**:
```json
[
  {
    "id": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
    "slug": "rohan-priya-wedding-4k9z",
    "name": "Rohan & Priya Wedding",
    "type": "wedding",
    "date": "2026-12-15T18:30:00.000Z",
    "city": "Udaipur",
    "coverPhotoUrl": "https://cdn.yaadein.com/covers/wedding.jpg",
    "status": "active",
    "plan": "premium",
    "photoCount": 156,
    "videoCount": 12,
    "guestCount": 85,
    "shareUrl": "/e/rohan-priya-wedding-4k9z",
    "createdAt": "2026-08-22T14:00:00.000Z"
  }
]
```

### `GET /events/{id_or_slug}` (Get Event Details)
Flexible lookup accepting either event UUID (`id`) or human-readable `slug`.

- **Auth**: Public (Optional `Bearer <JWT>`)
- **Response `200 OK`**: Complete `EventResponse` object.

### `GET /events/{event_id}/qr` (Get QR Code & Share Links)
Generates and returns the QR code asset URL and pre-formatted share links.

- **Auth**: Public / Host
- **Response `200 OK`**:
```json
{
  "qrUrl": "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=/e/rohan-priya-wedding-4k9z",
  "shareUrl": "/e/rohan-priya-wedding-4k9z",
  "whatsappUrl": "https://api.whatsapp.com/send?text=Upload%20your%20photos%20to%20Rohan%20%26%20Priya%20Wedding%20at%20%2Fe%2Frohan-priya-wedding-4k9z"
}
```

---

## 3. Guest PIN Gate & Registration

### `POST /events/{event_id}/authenticate` (Verify PIN)
Validates the 4-digit PIN entered by guests on the event gate screen before granting upload access.

- **Auth**: Public
- **Request Body**:
```json
{
  "pin": "4821"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "message": "Authenticated successfully"
}
```
- **Response `200 OK` (Invalid PIN)**:
```json
{
  "success": false,
  "message": "Invalid PIN. Please try again."
}
```

### `POST /events/{event_id}/guests` (Register Session & Consent)
Registers guest session information and stores DPDP/GDPR face search consent.

- **Auth**: Public
- **Request Body**:
```json
{
  "guestSessionId": "7f2a8901-4433-2211-9988-aabbccddeeff",
  "name": "Kavita Rao",
  "phone": "+919876543210",
  "faceSearchConsent": true
}
```
- **Response `200 OK`**:
```json
{
  "status": "success",
  "guest": {
    "guestSessionId": "7f2a8901-4433-2211-9988-aabbccddeeff",
    "name": "Kavita Rao",
    "faceSearchConsent": true
  }
}
```

---

## 4. Media Upload Pipeline (Direct-to-R2)

Yaadein uses direct-to-cloud (Cloudflare R2 / S3) chunked multipart uploads so client devices upload large media quickly and reliably without loading the API server.

### `POST /media/presigned-urls` (or `/uploads/presign`)
Requests presigned upload URLs for batch file uploads (chunk size 8MB).

- **Auth**: Bearer Token (Host) OR `X-Guest-Session-ID` + `X-Event-ID` (Guest)
- **Request Body**:
```json
{
  "eventId": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
  "files": [
    {
      "filename": "wedding_photo.jpg",
      "mimeType": "image/jpeg",
      "sizeBytes": 14500000
    }
  ]
}
```
- **Response `200 OK`**:
```json
{
  "uploads": [
    {
      "fileId": "file_a1b2c3d4e5",
      "uploadId": "r2_mp_upload_token_9988",
      "partUrls": [
        "https://r2.cloudflarestorage.com/yaadein/events/...?partNumber=1",
        "https://r2.cloudflarestorage.com/yaadein/events/...?partNumber=2"
      ],
      "confirmUrl": "/api/v1/media/confirm-upload",
      "chunkSize": 8388608
    }
  ]
}
```

### `POST /media/confirm-upload` (or `/media/confirm`)
Confirms completed upload, registers database record in `media` table, and triggers background thumbnailing and face indexing.

- **Auth**: Bearer Token OR Guest Headers
- **Request Body**:
```json
{
  "eventId": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
  "idempotencyKey": "9a8b7c6d5e...",
  "r2ObjectKey": "events/e3b0c442-98fc-11ee-b9d1-0242ac120002/originals/file_a1b2c3d4e5.jpg",
  "r2UploadId": "r2_mp_upload_token_9988",
  "faceConsent": true
}
```
- **Response `202 Accepted`**:
```json
{
  "id": "med_1122334455-uuid",
  "eventId": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
  "uploadedBy": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "type": "photo",
  "status": "ready",
  "url": "https://cdn.yaadein.com/events/e3b0/originals/file_a1b2c3d4e5.jpg",
  "thumbnailUrl": "https://cdn.yaadein.com/events/e3b0/thumbs/file_a1b2c3d4e5.webp",
  "fileSizeBytes": 14500000,
  "mimeType": "image/jpeg",
  "width": 4032,
  "height": 3024,
  "durationSeconds": null,
  "albumIds": [],
  "createdAt": "2026-08-22T14:15:00.000Z"
}
```

### `DELETE /media/{media_id}`
Deletes a specific photo or video from the event.

- **Auth**: Required (Event Host / Admin)
- **Response `204 No Content`**

---

## 5. Live Gallery & Infinite Scroll

### `GET /events/{id_or_slug}/gallery`
Fetches a cursor-paginated grid of visible media, associated albums, and total counts. Supports infinite scrolling.

- **Auth**: Public
- **Query Parameters**:
  - `limit`: Integer (default: `30`, max `100`)
  - `cursor`: UUID string of the last item for pagination offset
  - `albumId`: Optional UUID to filter by album
  - `search`: Optional string query
- **Response `200 OK`**:
```json
{
  "media": [
    {
      "id": "med_1122334455",
      "eventId": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
      "type": "photo",
      "status": "ready",
      "url": "https://cdn.yaadein.com/events/e3b0/originals/img1.jpg",
      "thumbnailUrl": "https://cdn.yaadein.com/events/e3b0/thumbs/img1.webp",
      "fileSizeBytes": 3400000,
      "width": 1920,
      "height": 1080,
      "albumIds": [],
      "createdAt": "2026-08-22T14:15:00.000Z"
    }
  ],
  "albums": [
    {
      "id": "alb_sangeet_uuid",
      "eventId": "e3b0c442-98fc-11ee-b9d1-0242ac120002",
      "name": "Sangeet Night",
      "type": "static",
      "emoji": "📁",
      "mediaCount": 42,
      "createdAt": "2026-08-22T12:00:00.000Z"
    }
  ],
  "totalCount": 156,
  "nextCursor": "med_1122334455"
}
```

---

## 6. AI Face Recognition & Search

### `POST /events/{id_or_slug}/face-search`
Uploads a selfie photo to detect face embeddings and search the event gallery using pgvector cosine similarity.

- **Auth**: Public
- **Request Format**: `multipart/form-data`
- **Form Fields**:
  - `image`: Binary file (`image/jpeg` or `image/png`)
- **Response `200 OK`**:
```json
{
  "mediaIds": [
    "med_1122334455",
    "med_9988776655",
    "med_4433221100"
  ]
}
```

---

## 7. Albums Management

### `GET /events/{event_id}/albums`
Fetches all albums created for an event.

- **Auth**: Public
- **Response `200 OK`**: Array of `AlbumResponse` objects.

### `POST /events/{event_id}/albums`
Creates a static album (with list of media IDs) or a dynamic album (with filter criteria).

- **Auth**: Required (`Bearer <JWT>`, Host)
- **Request Body (Static Album)**:
```json
{
  "name": "Haldi Ceremony",
  "type": "static",
  "mediaIds": ["med_1122334455", "med_9988776655"]
}
```
- **Response `201 Created`**: `AlbumResponse` object.

### `GET /events/{event_id}/albums/{album_id}`
Returns all media items belonging to a specific album.

- **Auth**: Public
- **Response `200 OK`**: Array of `MediaResponse` objects.

---

## 8. Downloads & Background Exports

### `GET /media/{event_id}/{media_id}/download`
Redirects directly to a short-lived presigned CDN download URL for the original high-resolution photo/video.

- **Auth**: Public / Host
- **Response `307 Temporary Redirect`**: Redirect to R2 download URL.

### `POST /events/{event_id}/exports`
Triggers background ZIP compilation of all event media.

- **Auth**: Required (`Bearer <JWT>`, Host)
- **Request Body**:
```json
{
  "scope": "full_event"
}
```
- **Response `202 Accepted`**:
```json
{
  "exportId": "exp_11223344-uuid",
  "status": "queued"
}
```

---

## 10. Standard Error Responses

All API errors return a standard JSON error structure with corresponding HTTP status codes:

```json
{
  "detail": "Descriptive error message explaining the failure"
}
```

| HTTP Status | Error Type | Description |
| :--- | :--- | :--- |
| `400 Bad Request` | Validation / Slug Conflict | Invalid parameter format or slug collision. |
| `401 Unauthorized` | Missing / Invalid Token | JWT expired, invalid, or missing Bearer token. |
| `403 Forbidden` | Permission Denied | Attempting to modify an event owned by another host. |
| `404 Not Found` | Resource Missing | Event, media, or user profile does not exist. |
| `422 Unprocessable Entity` | Pydantic Schema Error | Payload body fields missing or invalid data types. |
| `500 Server Error` | Internal Server Error | Storage or database exception. |
