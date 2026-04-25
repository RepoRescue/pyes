"""Step 7 bug-hunt: probe areas pyes's unit tests likely don't cover.

1. Connect to a port where nothing listens (refused).
2. Index unicode and round-trip via pyes high-level API.
3. Repeated ES() instantiation (state leak / monkey-patch corruption).
4. Known 3.13 trap: pyes.utils.imports still does `import imp` (gpt-codex did NOT fix).
5. Direct use of underlying conn.connection.info() — does the rescue still
   work when downstream code reaches into the elasticsearch client directly?
"""
from __future__ import print_function
import uuid
from pyes import ES
from pyes.query import MatchAllQuery, Search

ES_HOST = "127.0.0.1:9299"

# (1) refused-port behaviour: pyes builds connection lazily; a real op should fail
print("--- BUG-1: dead port ---")
try:
    bad = ES("127.0.0.1:9298")
    bad.indices.create_index("must-not-be-created")
    print("BUG-1 NOT-FOUND: dead port silently accepted!")
except Exception as e:
    print("BUG-1 OK: dead port raises", type(e).__name__)

# (2) Unicode round trip via pyes
print("--- BUG-2: unicode round-trip ---")
conn = ES(ES_HOST)
INDEX = "pyes-bug-" + uuid.uuid4().hex[:8]
try:
    conn.indices.delete_index(INDEX)
except Exception:
    pass
conn.indices.create_index(INDEX)
title = "测试 — Καλημέρα — أهلا"
conn.index({"title": title}, INDEX, "_doc", id=1)
conn.indices.refresh(INDEX)
hits = list(conn.search(query=Search(MatchAllQuery()), indices=[INDEX]))
got = hits[0]["title"]
assert got == title, (got, title)
print("BUG-2 OK: round-trip preserves multi-script unicode")

# (3) repeated ES() instantiation
print("--- BUG-3: 5x ES() ---")
conns = [ES(ES_HOST) for _ in range(5)]
for c in conns:
    h = list(c.search(query=Search(MatchAllQuery()), indices=[INDEX]))
    assert len(h) == 1
print("BUG-3 OK: 5x parallel ES() handles all return correct results")

# (4) The 3.13 imp trap
print("--- BUG-4: pyes.utils.imports import ---")
trap_found = False
try:
    import pyes.utils.imports  # noqa
    print("BUG-4 NOT-FOUND: pyes.utils.imports loaded cleanly")
except ModuleNotFoundError as e:
    if "imp" in str(e):
        trap_found = True
        print("BUG-4 FOUND: pyes/utils/imports.py:17 still has `import imp` ->", e)
    else:
        raise

# (5) direct underlying client access
print("--- BUG-5: conn.connection.info() (direct ES client) ---")
direct_bug = False
try:
    info = conn.connection.info()
    print("BUG-5 NOT-FOUND: direct info() worked:", info["version"]["number"])
except TypeError as e:
    if "headers" in str(e) and "perform_request" in str(e):
        direct_bug = True
        print("BUG-5 FOUND: gpt-codex's __perform_request monkey-patch missing kwargs ->", e)
    else:
        raise

conn.indices.delete_index(INDEX)
print(f"BUGHUNT_DONE; trap_found={trap_found} direct_bug={direct_bug}")
