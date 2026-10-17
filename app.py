"""Senter - a search engine for the Tor network. Flask UI over the crawl index."""
import re
import sqlite3
import time

from flask import Flask, request, render_template_string, redirect, url_for

DB = "/home/hatch/workspace/senter/senter.db"
PER_PAGE = 15

app = Flask(__name__)

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Senter - Search the Tor network</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b0d11;--panel:#11141a;--line:rgba(255,255,255,.09);
--text:#eceff4;--muted:#9aa4b4;--faint:#5d6675;--gold:#c9a86a;
--mono:ui-monospace,Menlo,Consolas,monospace;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
body{background:#0b0d11 url(/static/bg.jpg) center/cover fixed;color:var(--text);
font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;background:rgba(5,7,10,.55);
pointer-events:none;z-index:0}
.wrap,.add,.result{position:relative;z-index:1}
a{color:inherit;text-decoration:none}
.wrap{max-width:680px;margin:0 auto;padding:0 22px;min-height:100vh;display:flex;flex-direction:column}
header.top{display:flex;justify-content:space-between;align-items:center;padding:26px 0}
.brand{font-family:var(--mono);font-size:13px;letter-spacing:.2em;color:var(--gold);
text-transform:uppercase;font-weight:700}
.stats{font-family:var(--mono);font-size:11px;color:var(--faint)}
.hero{padding:8vh 0 30px;text-align:center}
.hero h1{font-size:clamp(40px,9vw,64px);font-weight:800;letter-spacing:-.03em;margin-bottom:8px}
.hero h1 span{color:var(--gold)}
.hero p{color:var(--muted);font-size:15px}
form.search{display:flex;gap:10px;margin:26px 0 8px}
form.search input{flex:1;background:rgba(10,13,18,.82);border:1px solid var(--line);color:var(--text);
border-radius:12px;padding:15px 18px;font-size:16px;outline:none;min-width:0}
form.search input:focus{border-color:var(--gold)}
form.search button{background:var(--gold);color:#0b0d11;border:none;border-radius:12px;
padding:0 26px;font-weight:800;font-size:15px;cursor:pointer}
.hint{text-align:center;color:var(--faint);font-size:12.5px;font-family:var(--mono)}
.result{border-top:1px solid var(--line);padding:20px 2px}
.result h2{font-size:17px;font-weight:700;margin-bottom:4px}
.result h2 a:hover{color:var(--gold)}
.result .url{font-family:var(--mono);font-size:11.5px;color:var(--gold);word-break:break-all;
margin-bottom:6px}
.result .snip{color:var(--muted);font-size:13.5px}
.meta{font-family:var(--mono);font-size:12px;color:var(--faint);padding:18px 2px}
.pager{display:flex;gap:12px;padding:10px 2px 30px}
.pager a{border:1px solid var(--line);border-radius:8px;padding:8px 18px;font-size:14px}
.pager a:hover{border-color:var(--gold)}
.add{border:1px solid var(--line);border-radius:14px;padding:24px;margin:30px 0;background:rgba(13,16,22,.82)}
.add h2{font-size:15px;margin-bottom:6px}
.add p{color:var(--muted);font-size:13.5px;margin-bottom:14px}
.add form{display:flex;gap:10px}
.add input{flex:1;background:var(--bg);border:1px solid var(--line);color:var(--text);
border-radius:10px;padding:12px 14px;font-size:14px;font-family:var(--mono);min-width:0}
.add button{background:transparent;color:var(--gold);border:1px solid var(--gold);
border-radius:10px;padding:0 20px;font-weight:700;cursor:pointer}
.msg{border:1px solid var(--gold);color:var(--gold);border-radius:10px;padding:12px 16px;
font-size:13.5px;margin:16px 0}
footer{margin-top:auto;padding:26px 0 34px;text-align:center;color:var(--faint);
font-size:12px;font-family:var(--mono)}
footer code{color:var(--muted);font-size:11px}
@media(max-width:520px){
.hero{padding:5vh 0 20px}
.hero h1{font-size:38px}
form.search{flex-direction:column}
form.search button{padding:15px}
form.search input{font-size:16px}
.add form{flex-direction:column}
.add button{padding:13px}
.result h2{font-size:16px}
.wrap{padding:0 16px}}

</style></head><body><div class="wrap">
<header class="top"><a class="brand" href="/">Senter</a>
<span class="stats">{{ stats }}</span></header>
<main>
{% if not q %}
<div class="hero"><h1>Search the <span>dark</span></h1>
<p>An index of .onion sites, crawled through Tor.</p></div>
{% endif %}
<form class="search" action="/search" method="get">
<input name="q" value="{{ q|e }}" placeholder="Search onion sites..." autocomplete="off">
<button type="submit">Search</button></form>
{% if not q %}<div class="hint">e.g. chat &middot; pastebin &middot; forum &middot; hosting</div>{% endif %}
{% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
{% if q %}<div class="meta">{{ total }} result{{ 's' if total != 1 }} for &ldquo;{{ q|e }}&rdquo;
({{ took }}s)</div>{% endif %}
{% for r in results %}<div class="result">
<h2><a href="{{ r.url }}">{{ r.title or r.url }}</a></h2>
<div class="url">{{ r.url }}</div>
<div class="snip">{{ r.snip }}</div></div>{% endfor %}
{% if pages > 1 %}<div class="pager">
{% if page > 1 %}<a href="/search?q={{ q|urlencode }}&p={{ page-1 }}">&larr; Prev</a>{% endif %}
{% if page < pages %}<a href="/search?q={{ q|urlencode }}&p={{ page+1 }}">Next &rarr;</a>{% endif %}
</div>{% endif %}
<div class="add"><h2>Know an onion site?</h2>
<p>Paste its address and the crawler will pick it up.</p>
<form action="/add" method="post">
<input name="url" placeholder="http://....onion/" autocomplete="off">
<button type="submit">Add</button></form></div>
</main>
<footer>senter &middot; crawled via tor<br>
<span style="font-size:11px;opacity:.75">donate <code>0x62A098898048c79FF14De07F3BE9310398E5eCF8</code></span></footer>
</div></body></html>"""


def get_db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def stats_line(c):
    n = c.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    q = c.execute("SELECT COUNT(*) FROM frontier WHERE status IN ('queued','failed')").fetchone()[0]
    return "%d indexed \u00b7 %d queued" % (n, q)


@app.route("/")
def index():
    c = get_db()
    s = stats_line(c)
    c.close()
    return render_template_string(PAGE, q="", results=[], total=0, pages=0,
                                   page=1, took=0, stats=s, msg="")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()[:200]
    page = max(1, int(request.args.get("p", "1") or 1))
    c = get_db()
    s = stats_line(c)
    results, total, took = [], 0, 0
    if q:
        # sanitize FTS5 query: quote phrases, drop operators
        terms = re.findall(r"[a-z0-9]+", q.lower())
        if terms:
            match = " ".join('"%s"' % t for t in terms[:10])
            t0 = time.time()
            try:
                total = c.execute(
                    "SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH ?",
                    (match,)).fetchone()[0]
                rows = c.execute(
                    "SELECT url, title, snippet(pages_fts, 2, '<b>', '</b>', '...', 24) AS snip "
                    "FROM pages_fts WHERE pages_fts MATCH ? "
                    "ORDER BY rank LIMIT ? OFFSET ?",
                    (match, PER_PAGE, (page - 1) * PER_PAGE)).fetchall()
                results = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
            took = round(time.time() - t0, 2)
    c.close()
    pages = (total + PER_PAGE - 1) // PER_PAGE
    return render_template_string(PAGE, q=q, results=results, total=total,
                                   pages=pages, page=page, took=took, stats=s, msg="")


@app.route("/add", methods=["POST"])
def add():
    url = request.form.get("url", "").strip()[:500]
    c = get_db()
    msg = ""
    if re.match(r"^https?://[a-z2-7]{16}([a-z2-7]{40})?\.onion", url, re.I):
        host = url.split("/")[2].lower()
        clean = "http://" + host + "/"
        c.execute("INSERT OR IGNORE INTO frontier(url, depth) VALUES(?, 0)", (clean,))
        c.commit()
        msg = "Added to the crawl queue: %s" % clean
    else:
        msg = "That does not look like a valid .onion address."
    s = stats_line(c)
    c.close()
    return render_template_string(PAGE, q="", results=[], total=0, pages=0,
                                   page=1, took=0, stats=s, msg=msg)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=18100, threaded=True)
