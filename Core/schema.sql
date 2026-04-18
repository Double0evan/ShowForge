-- users: discord members, pending guests, and merged records
CREATE TABLE IF NOT EXISTS users (
  id              INTEGER PRIMARY KEY,
  kind            TEXT NOT NULL CHECK(kind IN ('discord','pending','guest','merged')),
  discord_user_id TEXT UNIQUE,
  display_name    TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_normalized ON users(normalized_name);

-- inventory: unique items, code like N001 or S001
CREATE TABLE IF NOT EXISTS inventory_items (
  id           INTEGER PRIMARY KEY,
  item_code    TEXT NOT NULL UNIQUE,
  status       TEXT NOT NULL CHECK(status IN ('available','claimed','removed','claimed_removed')),
  post_mode    TEXT NOT NULL DEFAULT 'claim' CHECK(post_mode IN ('claim','display')),
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  published_at TEXT
);

-- voucher ledger: every +1/-1 is a row, never edited
CREATE TABLE IF NOT EXISTS voucher_ledger (
  id                 INTEGER PRIMARY KEY,
  user_id            INTEGER NOT NULL REFERENCES users(id),
  delta              INTEGER NOT NULL CHECK(delta IN (1,-1)),
  reason             TEXT NOT NULL CHECK(reason IN ('WINNER','GIVY','END_GIVY','CUSTOM_CHOICE','FREEBIE','STAFF_ADJUST')),
  winner_slot        INTEGER,
  note               TEXT,
  consumed_ledger_id INTEGER,
  created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_voucher_user_time ON voucher_ledger(user_id, created_at, id);

-- claims
CREATE TABLE IF NOT EXISTS claims (
  id                  INTEGER PRIMARY KEY,
  item_code           TEXT NOT NULL REFERENCES inventory_items(item_code),
  user_id             INTEGER NOT NULL REFERENCES users(id),
  voucher_spend_id    INTEGER REFERENCES voucher_ledger(id),
  source              TEXT NOT NULL CHECK(source IN ('reaction','staff','button')),
  reaction_message_id TEXT,
  reaction_emoji      TEXT,
  created_at          TEXT NOT NULL,
  removed_at          TEXT,
  removed_reason      TEXT
);

-- Partial unique index: only one active (non-removed) claim per item at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_item_active
  ON claims(item_code)
  WHERE removed_at IS NULL;

-- Per-show key/value state
CREATE TABLE IF NOT EXISTS show_state (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

-- Per-show settings (Discord thread IDs, etc.)
CREATE TABLE IF NOT EXISTS show_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Media asset locations (Discord attachment URLs)
CREATE TABLE IF NOT EXISTS media_assets (
  id                INTEGER PRIMARY KEY,
  item_code         TEXT NOT NULL,
  variant           TEXT NOT NULL CHECK(variant IN ('raw','watermarked')),
  rating            TEXT NOT NULL CHECK(rating IN ('sfw','nsfw')),
  source_channel_id TEXT NOT NULL,
  source_message_id TEXT NOT NULL,
  attachment_url    TEXT NOT NULL,
  filename          TEXT,
  content_type      TEXT,
  created_at        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_media_unique
  ON media_assets(item_code, variant, rating);
