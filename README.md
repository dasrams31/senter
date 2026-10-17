# Senter

A search engine for the Tor network. A polite .onion crawler indexes pages
around the clock into SQLite FTS5; a Flask UI serves search over the index.

## Components

- `crawler.py` — long-running worker. Pulls URLs from a persistent frontier
  queue, fetches via Tor SOCKS5, extracts title/text/outbound .onion links,
  upserts into FTS5. All state in `senter.db` (WAL), so it resumes after
  restart. Politeness: per-host delay, per-host page cap, max depth.
- `app.py` — Flask search UI (`/`, `/search?q=`, `/add`, stats).
- `schema.sql` — pages, pages_fts, frontier, hosts.

## Run

```
python -m venv venv && ./venv/bin/pip install flask "requests[socks]"
./venv/bin/python crawler.py   # worker
./venv/bin/python app.py       # web UI on 127.0.0.1:18100
```

Deploy behind a Tor hidden service (`HiddenServicePort 80 127.0.0.1:18100`).
