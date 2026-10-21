-- h3-swap-api D1 schema (CONTRACT section 8, v1.2 and v1.3 additions).
-- Apply: npx wrangler d1 execute h3-swap --remote --file=schema.sql
--
-- Already applied an earlier version? Run these once instead:
--   ALTER TABLE workers RENAME COLUMN vast_id TO provider_ref;   -- only if vast_id exists
--   ALTER TABLE jobs ADD COLUMN worker_id TEXT;
--   ALTER TABLE jobs ADD COLUMN message TEXT;
--   CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id);
--   CREATE TABLE IF NOT EXISTS provider_state (provider TEXT PRIMARY KEY, cooldown_until TEXT, last_error TEXT);

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT,
  balance_cents INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);

-- key_hash = lowercase hex SHA-256 of the raw API key (the Bearer token).
CREATE TABLE IF NOT EXISTS api_keys (
  key_hash   TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id             TEXT PRIMARY KEY,
  user_id        TEXT NOT NULL REFERENCES users(id),
  status         TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  duration_s     INTEGER NOT NULL,
  reserved_cents INTEGER NOT NULL,
  charged_cents  INTEGER NOT NULL DEFAULT 0,
  source_key     TEXT NOT NULL,
  output_key     TEXT,
  error          TEXT,
  attempts       INTEGER NOT NULL DEFAULT 0,
  gpu_seconds    REAL,
  wall_seconds   REAL,
  created_at     TEXT NOT NULL,
  started_at     TEXT,   -- start of the current claim (reset when a job is released)
  finished_at    TEXT,
  worker_id      TEXT,   -- worker id holding the claim (v1.2), NULL when queued
  message        TEXT    -- JSON of the queue message, kept so the job can be requeued
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id);

-- One row per worker.
-- instance_id  = worker id (w-<12 hex>), reported by the worker as instance_id.
-- provider_ref = Vast contract id or Salad container name (NULL until stored).
CREATE TABLE IF NOT EXISTS workers (
  instance_id       TEXT PRIMARY KEY,
  provider          TEXT NOT NULL,
  provider_ref      TEXT,
  state             TEXT NOT NULL CHECK (state IN ('booting', 'idle', 'busy')),
  created_at        TEXT NOT NULL,
  last_heartbeat_at TEXT,
  idle_seconds      INTEGER NOT NULL DEFAULT 0,
  jobs_done         INTEGER NOT NULL DEFAULT 0
);

-- Per-provider cooldown after a create failure or a boot failure (CONTRACT 9b).
CREATE TABLE IF NOT EXISTS provider_state (
  provider       TEXT PRIMARY KEY,
  cooldown_until TEXT,
  last_error     TEXT
);
