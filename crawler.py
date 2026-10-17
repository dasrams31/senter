"""Senter crawler: discovers .onion pages through Tor and indexes them.

Runs forever as a systemd service. All state is in SQLite (WAL), so a VM
restart simply resumes the frontier where it left off.
"""
import re
import sqlite3
import time
import urllib.parse
from html.parser import HTMLParser

import requests

DB = "/home/hatch/workspace/senter/senter.db"
TOR_PROXY = "socks5h://127.0.0.1:9050"
MAX_DEPTH = 3
MAX_PAGES_PER_HOST = 500
POLITE_DELAY = 5          # seconds between hits to the same host
REQ_TIMEOUT = 30
MAX_BYTES = 2 * 1024 * 1024
IDLE_SLEEP = 10
ONION_RE = re.compile(r"^https?://([a-z2-7]{16}|[a-z2-7]{56})\.onion(?::\d+)?(/.*)?$", re.I)

SEEDS = [
    # own network first - guaranteed friendly
    "http://pekaheqjbfgs3neiuyllbenxw7yimcfjainydksvko3ywvzzdtygh4id.onion/",
    "http://aeterramwgvpn4cfqyv5hjwxx7dlo4adpwyvfufrhxw5jtwxac3o6zad.onion/",
    "http://xuwuednndnfv4pvzaoyyrkhr3ektwysvrdqrpua6avrnjpxk4juqd6id.onion/",
    "http://kt7i7eh5fmhhshnxvfi5ksjcvcvbgaqxyexkngezn6ppoo7gjdbvxkyd.onion/",
    "http://e4xctjlb7tmlceor3o5u73pyewkfnbq3xoe5e3bpdu6tyhasefp7i7qd.onion/",
    "http://c36lfiotrstasgwcozyrkyrnklkvavblspdw5n3vsicto77c6xc6snad.onion/",
    "http://7dk2mu57tewvohy756lomgwpaqgre7x5jg47fwgqlwc3k5avcihbxlid.onion/",
    "http://cedbjajfwaups32l6qxoqyqacypgso7ol5sdn5lusjbeh7dxd4xbjtid.onion/",
]


class TextExtractor(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self._in_title = False
        self.chunks = []
        self.links = []
        self._skip = 0  # inside script/style

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(urllib.parse.urljoin(self.base, v.strip()))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        else:
            s = data.strip()
            if s:
                self.chunks.append(s)


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    c = db()
    with open("/home/hatch/workspace/senter/schema.sql") as f:
        c.executescript(f.read())
    for u in SEEDS:
        c.execute("INSERT OR IGNORE INTO frontier(url, depth) VALUES(?, 0)", (u,))
    c.commit()
    c.close()


def norm_onion(link):
    link = link.split("#")[0]
    m = ONION_RE.match(link)
    if not m:
        return None
    host = m.group(0).split("/")[2].lower()
    path = m.group(2) or "/"
    return "http://%s%s" % (host, path)


def pick(c):
    now = int(time.time())
    row = c.execute(
        "SELECT url, depth FROM frontier WHERE status='queued' "
        "OR (status='failed' AND fails < 3 AND next_fetch <= ?) "
        "ORDER BY next_fetch LIMIT 1", (now,)).fetchone()
    return row


def polite_wait(c, host):
    row = c.execute("SELECT last_hit FROM hosts WHERE host=?", (host,)).fetchone()
    if row:
        wait = POLITE_DELAY - (time.time() - row[0])
        if wait > 0:
            time.sleep(wait)
    c.execute("INSERT OR REPLACE INTO hosts(host, last_hit) VALUES(?, ?)",
              (host, int(time.time())))
    c.commit()


def crawl_one(c, url, depth):
    host = urllib.parse.urlparse(url).netloc.lower()
    polite_wait(c, host)
    c.execute("UPDATE frontier SET status='fetching' WHERE url=?", (url,))
    c.commit()

    n_host = c.execute("SELECT COUNT(*) FROM pages WHERE url LIKE ?",
                       ("http://" + host + "%",)).fetchone()[0]
    if n_host >= MAX_PAGES_PER_HOST:
        c.execute("UPDATE frontier SET status='done' WHERE url=?", (url,))
        c.commit()
        return "host-cap"

    sess = requests.Session()
    sess.trust_env = False  # ignore hatch-egress-proxy env vars; Tor only
    sess.proxies = {"http": TOR_PROXY, "https": TOR_PROXY}
    try:
        r = sess.get(url, timeout=REQ_TIMEOUT, stream=True,
                     headers={"User-Agent": "Senter/1.0 (+tor onion crawler)"})
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            raise ValueError("skip %s %s" % (r.status_code, r.headers.get("Content-Type")))
        raw = b""
        for chunk in r.iter_content(65536):
            raw += chunk
            if len(raw) > MAX_BYTES:
                break
        html = raw.decode("utf-8", "replace")
    except Exception as e:
        fails = c.execute("SELECT fails FROM frontier WHERE url=?", (url,)).fetchone()[0]
        c.execute("UPDATE frontier SET status='failed', fails=?, next_fetch=? WHERE url=?",
                  (fails + 1, int(time.time()) + 3600 * (fails + 1), url))
        c.commit()
        return "fetch-fail %s" % e

    p = TextExtractor(url)
    try:
        p.feed(html)
    except Exception:
        pass
    title = re.sub(r"\s+", " ", p.title).strip()[:200]
    text = re.sub(r"\s+", " ", " ".join(p.chunks))[:20000]
    now = int(time.time())

    c.execute("INSERT OR REPLACE INTO pages(url, title, text, fetched_at, status)"
              " VALUES(?, ?, ?, ?, 200)", (url, title, text, now))
    c.execute("DELETE FROM pages_fts WHERE url=?", (url,))
    c.execute("INSERT INTO pages_fts(url, title, text) VALUES(?, ?, ?)", (url, title, text))

    added = 0
    if depth < MAX_DEPTH:
        for link in p.links:
            n = norm_onion(link)
            if n:
                try:
                    c.execute("INSERT OR IGNORE INTO frontier(url, depth) VALUES(?, ?)",
                              (n, depth + 1))
                    added += c.total_changes
                except sqlite3.IntegrityError:
                    pass
    c.execute("UPDATE frontier SET status='done' WHERE url=?", (url,))
    c.commit()
    return "ok title=%r links+%d" % (title[:40], added)


def main():
    init()
    c = db()
    while True:
        try:
            row = pick(c)
            if not row:
                time.sleep(IDLE_SLEEP)
                continue
            url, depth = row
            print(time.strftime("%H:%M:%S"), url, "->", crawl_one(c, url, depth), flush=True)
        except Exception as e:
            print("loop error:", e, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
