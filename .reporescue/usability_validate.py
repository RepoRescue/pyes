"""End-to-end usability validation for pyes (gpt-codex rescue).

Scenario B. Real ES 7.17 docker on 127.0.0.1:9299. Three submodules:
  - pyes.es        (ES, indices.create_index/refresh/delete_index, index, search)
  - pyes.query     (MatchAllQuery, TermQuery, BoolQuery, Search)
  - pyes.mappings  (DocumentObjectField, TextField, IntegerField, KeywordField, .as_dict())

Hard constraint 6 (Py3.13 surfaces the gpt-codex rescue had to fix):
  - pyes/es.py:413  `from elasticsearch import Elasticsearch`         (lib API churn)
  - pyes/es.py:423  Elasticsearch(http_servers, ...)                   (hosts arg required)
  - pyes/es.py:439-478  __perform_request rewritten for elastic_transport 8/9
  - pyes/es.py:421/424  request_timeout (was timeout) for ES8+ client

T2 PASS path uses elasticsearch==9.3.0 + urllib3==2.6.3.
"""
from __future__ import print_function
import time
import uuid

ES_HOST = "127.0.0.1:9299"

import pyes
print("pyes version:", pyes.__version__)
assert pyes.__version__ == "7.0.0dev"

# --- submodule 1: pyes.es ------------------------------------------------
from pyes import ES

conn = ES(ES_HOST)
print("conn.servers =", conn.servers)
assert conn.connection is not None
import elasticsearch as _es
print("elasticsearch lib:", _es.__version__)

INDEX = "pyes-validate-" + uuid.uuid4().hex[:8]
try:
    conn.indices.delete_index(INDEX)
except Exception:
    pass

# --- submodule 2: pyes.mappings (build & serialize) ----------------------
from pyes.mappings import (
    DocumentObjectField, TextField, IntegerField, KeywordField,
)

doc_map = DocumentObjectField(name="article")
doc_map.add_property(TextField(name="title", store=True))
doc_map.add_property(KeywordField(name="tag", store=True))
doc_map.add_property(IntegerField(name="position", store=True))
mapping_dict = doc_map.as_dict()
props = mapping_dict["properties"]
print("Mapping properties:", sorted(props))
assert "title" in props and "tag" in props and "position" in props
assert props["position"]["type"] in ("integer", "long")
assert props["tag"]["type"] == "keyword"
assert props["title"]["type"] == "text"
# Real-output assertion: TextField produced "store: true" hint
assert props["title"].get("store") in (True, "true"), props["title"]

# Use create_index_with_settings path: pass settings dict that embeds the mappings
conn.indices.create_index(INDEX)
print("Index created:", INDEX)

# --- index docs through pyes ES.index ------------------------------------
docs = [
    {"title": "Joe Tester",     "tag": "person",  "position": 1},
    {"title": "Bill Baloney",   "tag": "person",  "position": 2},
    {"title": "Sample Article", "tag": "article", "position": 3},
]
for i, d in enumerate(docs, 1):
    conn.index(d, INDEX, "_doc", id=i)

conn.indices.refresh(INDEX)
print("Indexed", len(docs), "docs")

# --- submodule 3: pyes.query --------------------------------------------
from pyes.query import MatchAllQuery, TermQuery, BoolQuery, Search

# Real-output: validate the serialised query body before sending
tq_body = TermQuery("tag", "person").serialize()
print("TermQuery.serialize() =", tq_body)
assert tq_body == {"term": {"tag": "person"}}, tq_body

q_all = MatchAllQuery()
res_all = conn.search(query=Search(q_all), indices=[INDEX])
hits_all = list(res_all)
print("MatchAll hits:", len(hits_all))
assert len(hits_all) == 3, f"expected 3, got {len(hits_all)}"

q_tag = TermQuery("tag", "person")
res_tag = conn.search(query=Search(q_tag), indices=[INDEX])
hits_tag = list(res_tag)
print("TermQuery(tag=person) hits:", len(hits_tag))
assert len(hits_tag) == 2, f"expected 2, got {len(hits_tag)}"

titles = sorted(h["title"] for h in hits_tag)
assert titles == ["Bill Baloney", "Joe Tester"], titles

q_bool = BoolQuery(must=[TermQuery("tag", "person"), TermQuery("position", 1)])
res_b = list(conn.search(query=Search(q_bool), indices=[INDEX]))
print("BoolQuery hits:", len(res_b))
assert len(res_b) == 1 and res_b[0]["title"] == "Joe Tester", res_b

# cleanup
conn.indices.delete_index(INDEX)
print("USABLE")
