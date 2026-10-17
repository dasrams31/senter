-- Senter search engine storage. WAL mode for concurrent crawler + web reads.
-- All state lives here so a VM reset loses nothing: the frontier is the resume point.

CREATE TABLE IF NOT EXISTS pages(
  url        TEXT PRIMARY KEY,
  title      TEXT NOT NULL DEFAULT '',
  text       TEXT NOT NULL DEFAULT '',
  fetched_at INTEGER NOT NULL DEFAULT 0,
  status     INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(url, title, text);

CREATE TABLE IF NOT EXISTS frontier(
  url        TEXT PRIMARY KEY,
  status     TEXT NOT NULL DEFAULT 'queued', -- queued | fetching | done | failed
  next_fetch INTEGER NOT NULL DEFAULT 0,     -- unix ts, for retries
  fails      INTEGER NOT NULL DEFAULT 0,
  depth      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_frontier_pick ON frontier(status, next_fetch);

CREATE TABLE IF NOT EXISTS hosts(
  host       TEXT PRIMARY KEY,
  last_hit   INTEGER NOT NULL DEFAULT 0
);
