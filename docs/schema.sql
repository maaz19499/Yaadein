-- Enable the pgvector extension for face embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. USERS: Only registered people who log in (hosts, photographers, admins)
CREATE TABLE users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone           text UNIQUE NOT NULL,
  password_hash   text NOT NULL, -- Added for self-rolled auth
  name            text,
  role            text CHECK (role IN ('host', 'photographer', 'admin')),
  auth_provider   text,
  created_at      timestamptz DEFAULT now()
);

-- 2. EVENTS: The single most important tenant boundary
CREATE TABLE events (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  host_id              uuid REFERENCES users(id),
  slug                 text UNIQUE NOT NULL,
  face_search_enabled  boolean DEFAULT false,
  plan                 text CHECK (plan IN ('basic', 'premium', 'professional')),
  storage_expires_at   timestamptz,
  is_wedding           boolean DEFAULT false,
  created_at           timestamptz DEFAULT now()
);

-- 3. GUESTS: Unauthenticated event attendees session tracker
CREATE TABLE guests (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id          uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  guest_session_id  uuid NOT NULL,
  name              text,
  phone             text,
  first_seen_at     timestamptz DEFAULT now(),
  last_seen_at      timestamptz DEFAULT now(),
  UNIQUE (event_id, guest_session_id)
);

-- 4. MEDIA: Partitioned by event_id hash
CREATE TABLE media (
  id                 uuid DEFAULT gen_random_uuid(),
  event_id           uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  uploaded_by        uuid REFERENCES users(id),
  guest_session_id   uuid,
  type               text CHECK (type IN ('image', 'video')),
  r2_object_key      text NOT NULL,
  idempotency_key    text NOT NULL,
  status             text CHECK (status IN ('pending_verify', 'scanning', 'processing', 'visible', 'rejected', 'duplicate')),
  file_size_bytes    bigint,
  mime_type          text,
  checksum           text,
  phash              bit(64), -- Added for perceptual duplicate detection
  width              int,
  height             int,
  duration_seconds   int,
  thumbnail_url      text,
  created_at         timestamptz DEFAULT now(),
  PRIMARY KEY (event_id, id),
  UNIQUE (event_id, idempotency_key),
  CHECK (uploaded_by IS NOT NULL OR guest_session_id IS NOT NULL),
  FOREIGN KEY (event_id, guest_session_id) REFERENCES guests(event_id, guest_session_id) ON DELETE SET NULL
) PARTITION BY HASH (event_id);

-- Create index on event_id + created_at to support fast gallery sorting and overage count checks
CREATE INDEX ON media (event_id, created_at DESC);

-- 5. PAYMENTS: Transaction and upgrade audit trail
CREATE TABLE payments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
  event_id        uuid REFERENCES events(id) ON DELETE SET NULL,
  plan            text,
  amount          numeric,
  status          text CHECK (status IN ('pending', 'success', 'failed', 'refunded')),
  upgrade_trigger text,
  created_at      timestamptz DEFAULT now()
);

-- 6. FACE CONSENTS: Privacy opt-in anchors for DPDP Act compliance
CREATE TABLE face_consents (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id            uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  guest_session_id    uuid NOT NULL,
  guest_name          text,
  consent_given_at    timestamptz NOT NULL,
  consent_revoked_at  timestamptz,
  purge_executed_at   timestamptz,
  FOREIGN KEY (event_id, guest_session_id) REFERENCES guests(event_id, guest_session_id) ON DELETE CASCADE
);

-- 7. FACE CLUSTERS: Groupings of distinct faces per event
CREATE TABLE face_clusters (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id                  uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  matched_guest_session_id  uuid,
  matched_guest_name        text,
  cover_thumbnail_url       text
);

-- 8. FACE EMBEDDINGS: Abstract float vector representations for pgvector searches
CREATE TABLE face_embeddings (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id             uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  media_id             uuid NOT NULL,
  embedding            vector(512),
  cluster_id           uuid REFERENCES face_clusters(id) ON DELETE SET NULL,
  uploader_consent_id  uuid NOT NULL REFERENCES face_consents(id) ON DELETE CASCADE,
  purge_at             timestamptz NOT NULL,
  created_at           timestamptz DEFAULT now(),
  FOREIGN KEY (event_id, media_id) REFERENCES media(event_id, id) ON DELETE CASCADE
);

-- Index for pgvector searches (restricted per event_id inside the query filter)
CREATE INDEX ON face_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON face_embeddings (event_id, cluster_id);

-- 9. GALLERY CACHE: Pre-built gallery JSON payload to offload database reads
CREATE TABLE gallery_cache (
  event_id        uuid PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  cached_payload  jsonb,
  refreshed_at    timestamptz
);

-- 10. QR CODES: Funnel analytics
CREATE TABLE qr_codes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  scan_count      int DEFAULT 0,
  unique_visitors int DEFAULT 0
);

-- 11. EXPORTS: Async Celery ZIP archive jobs tracking
CREATE TABLE exports (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  requested_by  uuid REFERENCES users(id) ON DELETE SET NULL,
  scope         text CHECK (scope IN ('single', 'album', 'full_event')),
  status        text CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
  download_url  text
);

-- 12. ALBUMS: Static/dynamic collections, partitioned by event_id hash
CREATE TABLE albums (
  id                  uuid DEFAULT gen_random_uuid(),
  event_id            uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name                text NOT NULL,
  type                text CHECK (type IN ('static', 'dynamic')),
  dynamic_filters     jsonb, -- e.g. {"face_cluster_ids": ["uuid1", "uuid2"]}
  created_at          timestamptz DEFAULT now(),
  PRIMARY KEY (event_id, id)
) PARTITION BY HASH (event_id);

-- 13. ALBUM_MEDIA: Many-to-many junction, partitioned by event_id hash
CREATE TABLE album_media (
  event_id            uuid NOT NULL,
  album_id            uuid NOT NULL,
  media_id            uuid NOT NULL,
  created_at          timestamptz DEFAULT now(),
  PRIMARY KEY (event_id, album_id, media_id),
  FOREIGN KEY (event_id, album_id) REFERENCES albums(event_id, id) ON DELETE CASCADE,
  FOREIGN KEY (event_id, media_id) REFERENCES media(event_id, id) ON DELETE CASCADE
) PARTITION BY HASH (event_id);

-- Automatically initialize 64 partitions for the partitioned tables
DO $$
DECLARE
    i int;
BEGIN
    FOR i IN 0..63 LOOP
        EXECUTE format('CREATE TABLE media_part_%s PARTITION OF media FOR VALUES WITH (MODULUS 64, REMAINDER %s);', i, i);
        EXECUTE format('CREATE TABLE albums_part_%s PARTITION OF albums FOR VALUES WITH (MODULUS 64, REMAINDER %s);', i, i);
        EXECUTE format('CREATE TABLE album_media_part_%s PARTITION OF album_media FOR VALUES WITH (MODULUS 64, REMAINDER %s);', i, i);
    END LOOP;
END;
$$;
