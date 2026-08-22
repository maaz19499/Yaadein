-- Yaadein Database Schema & Row Level Security (RLS) Policies
-- Latest Version: 2026-08-22

-- ============================================================
-- 0. EXTENSIONS & CLEANUP
-- ============================================================
DROP TABLE IF EXISTS album_media CASCADE;
DROP TABLE IF EXISTS albums CASCADE;
DROP TABLE IF EXISTS exports CASCADE;
DROP TABLE IF EXISTS qr_codes CASCADE;
DROP TABLE IF EXISTS gallery_cache CASCADE;
DROP TABLE IF EXISTS face_embeddings CASCADE;
DROP TABLE IF EXISTS face_clusters CASCADE;
DROP TABLE IF EXISTS face_consents CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS media CASCADE;
DROP TABLE IF EXISTS guests CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- Enable pgvector extension for AI face embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. USERS: Profiles for registered users (hosts, photographers, admins)
-- ============================================================
CREATE TABLE users (
  id              uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  phone           text UNIQUE,
  name            text,
  role            text CHECK (role IN ('host', 'photographer', 'admin')),
  created_at      timestamptz DEFAULT now()
);

-- ============================================================
-- 2. EVENTS: Primary tenant boundary & event configuration
-- ============================================================
CREATE TABLE events (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  host_id              uuid REFERENCES users(id) ON DELETE SET NULL,
  slug                 text UNIQUE NOT NULL,
  name                 text,
  type                 text CHECK (type IN ('wedding', 'birthday', 'graduation', 'corporate', 'engagement', 'other')),
  date                 timestamptz,
  city                 text,
  cover_photo_url      text,
  status               text DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'archived')),
  plan                 text DEFAULT 'starter' CHECK (plan IN ('starter', 'basic', 'premium', 'elite', 'professional')),
  guest_pin            varchar(4),
  face_search_enabled  boolean DEFAULT false,
  storage_expires_at   timestamptz,
  upload_expires_at    timestamptz,
  face_clustered       boolean DEFAULT false,
  is_wedding           boolean DEFAULT false,
  created_at           timestamptz DEFAULT now()
);

CREATE INDEX idx_events_host_id ON events(host_id);
CREATE INDEX idx_events_slug ON events(slug);

-- ============================================================
-- 3. GUESTS: Unauthenticated event attendees session tracker
-- ============================================================
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

CREATE INDEX idx_guests_event_session ON guests(event_id, guest_session_id);

-- ============================================================
-- 4. MEDIA: Partitioned by event_id hash for multi-tenant scalability
-- ============================================================
CREATE TABLE media (
  id                 uuid DEFAULT gen_random_uuid(),
  event_id           uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  uploaded_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  guest_session_id   uuid,
  type               text CHECK (type IN ('photo', 'image', 'video')),
  r2_object_key      text NOT NULL,
  idempotency_key    text NOT NULL,
  status             text DEFAULT 'visible' CHECK (status IN ('pending_verify', 'scanning', 'processing', 'visible', 'rejected', 'duplicate')),
  file_size_bytes    bigint,
  mime_type          text,
  checksum           text,
  phash              bit(64), -- Perceptual hashing for duplicate detection
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

CREATE INDEX idx_media_event_created ON media (event_id, created_at DESC);

-- ============================================================
-- 5. PAYMENTS: Transaction and upgrade audit trail
-- ============================================================
CREATE TABLE payments (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id          text,
  order_id            text UNIQUE,
  amount              numeric,
  status              text CHECK (status IN ('pending', 'success', 'failed', 'refunded')),
  plan                text,
  user_id             uuid REFERENCES users(id) ON DELETE SET NULL,
  event_id            uuid REFERENCES events(id) ON DELETE SET NULL,
  razorpay_payment_id text,
  upgrade_trigger     text,
  created_at          timestamptz DEFAULT now()
);

CREATE INDEX idx_payments_user_id ON payments(user_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);

-- ============================================================
-- 6. FACE CONSENTS: Privacy opt-in anchors (DPDP / GDPR Compliance)
-- ============================================================
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

-- ============================================================
-- 7. FACE CLUSTERS: Groupings of distinct faces per event
-- ============================================================
CREATE TABLE face_clusters (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id                  uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  matched_guest_session_id  uuid,
  matched_guest_name        text,
  cover_thumbnail_url       text
);

-- ============================================================
-- 8. FACE EMBEDDINGS: Float vector representations for pgvector similarity
-- ============================================================
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

CREATE INDEX idx_face_embeddings_hnsw ON face_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_face_embeddings_event_cluster ON face_embeddings (event_id, cluster_id);

-- ============================================================
-- 9. GALLERY CACHE: Pre-built gallery payload cache
-- ============================================================
CREATE TABLE gallery_cache (
  event_id        uuid PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  cached_payload  jsonb,
  refreshed_at    timestamptz
);

-- ============================================================
-- 10. QR CODES: Funnel analytics
-- ============================================================
CREATE TABLE qr_codes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  scan_count      int DEFAULT 0,
  unique_visitors int DEFAULT 0
);

-- ============================================================
-- 11. EXPORTS: Async Celery ZIP archive jobs tracking
-- ============================================================
CREATE TABLE exports (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  requested_by  uuid REFERENCES users(id) ON DELETE SET NULL,
  scope         text CHECK (scope IN ('single', 'album', 'full_event')),
  status        text CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
  download_url  text,
  created_at    timestamptz DEFAULT now()
);

-- ============================================================
-- 12. ALBUMS: Static / Dynamic collections (Partitioned by event_id)
-- ============================================================
CREATE TABLE albums (
  id                  uuid DEFAULT gen_random_uuid(),
  event_id            uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name                text NOT NULL,
  type                text CHECK (type IN ('static', 'dynamic')),
  dynamic_filters     jsonb,
  created_at          timestamptz DEFAULT now(),
  PRIMARY KEY (event_id, id)
) PARTITION BY HASH (event_id);

-- ============================================================
-- 13. ALBUM_MEDIA: Many-to-many junction (Partitioned by event_id)
-- ============================================================
CREATE TABLE album_media (
  event_id            uuid NOT NULL,
  album_id            uuid NOT NULL,
  media_id            uuid NOT NULL,
  created_at          timestamptz DEFAULT now(),
  PRIMARY KEY (event_id, album_id, media_id),
  FOREIGN KEY (event_id, album_id) REFERENCES albums(event_id, id) ON DELETE CASCADE,
  FOREIGN KEY (event_id, media_id) REFERENCES media(event_id, id) ON DELETE CASCADE
) PARTITION BY HASH (event_id);

-- Initialize 64 partitions for media, albums, and album_media
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

-- ============================================================
-- 14. TRIGGER: Automatically sync Supabase Auth users to public.users
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.users (id, phone, name, role)
  VALUES (
    new.id,
    new.phone,
    new.raw_user_meta_data->>'name',
    COALESCE(new.raw_user_meta_data->>'role', 'host')
  )
  ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    phone = EXCLUDED.phone;
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 15. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================

-- Enable RLS across all tables
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE guests          ENABLE ROW LEVEL SECURITY;
ALTER TABLE media           ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_consents   ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_clusters   ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE gallery_cache   ENABLE ROW LEVEL SECURITY;
ALTER TABLE qr_codes        ENABLE ROW LEVEL SECURITY;
ALTER TABLE exports         ENABLE ROW LEVEL SECURITY;
ALTER TABLE albums          ENABLE ROW LEVEL SECURITY;
ALTER TABLE album_media     ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- USERS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Users can view own profile" 
  ON users FOR SELECT 
  TO authenticated 
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" 
  ON users FOR UPDATE 
  TO authenticated 
  USING (auth.uid() = id);

-- ------------------------------------------------------------
-- EVENTS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Public can view active events" 
  ON events FOR SELECT 
  TO anon, authenticated 
  USING (status IN ('active', 'pending'));

CREATE POLICY "Hosts can view own events" 
  ON events FOR SELECT 
  TO authenticated 
  USING (auth.uid() = host_id);

CREATE POLICY "Hosts can create events" 
  ON events FOR INSERT 
  TO authenticated 
  WITH CHECK (auth.uid() = host_id);

CREATE POLICY "Hosts can update own events" 
  ON events FOR UPDATE 
  TO authenticated 
  USING (auth.uid() = host_id);

CREATE POLICY "Hosts can delete own events" 
  ON events FOR DELETE 
  TO authenticated 
  USING (auth.uid() = host_id);

-- ------------------------------------------------------------
-- GUESTS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Anyone can register guest session" 
  ON guests FOR INSERT 
  TO anon, authenticated 
  WITH CHECK (true);

CREATE POLICY "Guests and hosts can view guests" 
  ON guests FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Guests can update own session" 
  ON guests FOR UPDATE 
  TO anon, authenticated 
  USING (true);

-- ------------------------------------------------------------
-- MEDIA Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Public can view visible media" 
  ON media FOR SELECT 
  TO anon, authenticated 
  USING (status = 'visible');

CREATE POLICY "Hosts can view all media for their events" 
  ON media FOR SELECT 
  TO authenticated 
  USING (
    EXISTS (SELECT 1 FROM events WHERE events.id = media.event_id AND events.host_id = auth.uid())
  );

CREATE POLICY "Guests and hosts can insert media" 
  ON media FOR INSERT 
  TO anon, authenticated 
  WITH CHECK (true);

CREATE POLICY "Hosts can update event media" 
  ON media FOR UPDATE 
  TO authenticated 
  USING (
    EXISTS (SELECT 1 FROM events WHERE events.id = media.event_id AND events.host_id = auth.uid())
  );

CREATE POLICY "Hosts can delete event media" 
  ON media FOR DELETE 
  TO authenticated 
  USING (
    EXISTS (SELECT 1 FROM events WHERE events.id = media.event_id AND events.host_id = auth.uid())
  );

-- ------------------------------------------------------------
-- PAYMENTS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Users can view own payments" 
  ON payments FOR SELECT 
  TO authenticated 
  USING (auth.uid() = user_id);

CREATE POLICY "Authenticated users can insert payments" 
  ON payments FOR INSERT 
  TO authenticated 
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own payments" 
  ON payments FOR UPDATE 
  TO authenticated 
  USING (auth.uid() = user_id);

-- ------------------------------------------------------------
-- FACE CONSENTS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Guests and hosts can insert consent" 
  ON face_consents FOR INSERT 
  TO anon, authenticated 
  WITH CHECK (true);

CREATE POLICY "Guests and hosts can view consent" 
  ON face_consents FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Guests can update consent" 
  ON face_consents FOR UPDATE 
  TO anon, authenticated 
  USING (true);

-- ------------------------------------------------------------
-- FACE CLUSTERS & EMBEDDINGS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Public can view face clusters" 
  ON face_clusters FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Public can view face embeddings" 
  ON face_embeddings FOR SELECT 
  TO anon, authenticated 
  USING (true);

-- ------------------------------------------------------------
-- GALLERY CACHE & QR CODES Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Public can view gallery cache" 
  ON gallery_cache FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Public can view qr codes" 
  ON qr_codes FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Public can update qr code scans" 
  ON qr_codes FOR UPDATE 
  TO anon, authenticated 
  USING (true);

-- ------------------------------------------------------------
-- ALBUMS & ALBUM_MEDIA Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Public can view albums" 
  ON albums FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Hosts can manage albums" 
  ON albums FOR ALL 
  TO authenticated 
  USING (
    EXISTS (SELECT 1 FROM events WHERE events.id = albums.event_id AND events.host_id = auth.uid())
  );

CREATE POLICY "Public can view album media" 
  ON album_media FOR SELECT 
  TO anon, authenticated 
  USING (true);

CREATE POLICY "Hosts can manage album media" 
  ON album_media FOR ALL 
  TO authenticated 
  USING (
    EXISTS (SELECT 1 FROM events WHERE events.id = album_media.event_id AND events.host_id = auth.uid())
  );

-- ------------------------------------------------------------
-- EXPORTS Table Policies
-- ------------------------------------------------------------
CREATE POLICY "Hosts can view own exports" 
  ON exports FOR SELECT 
  TO authenticated 
  USING (auth.uid() = requested_by);

CREATE POLICY "Hosts can create exports" 
  ON exports FOR INSERT 
  TO authenticated 
  WITH CHECK (auth.uid() = requested_by);