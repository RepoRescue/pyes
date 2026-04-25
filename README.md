# pyes — Modernized for Python 3.13 + Elasticsearch 7.x/9.x

> **Honest upfront:** if you are starting a new project, **use the official
> [`elasticsearch-py`](https://github.com/elastic/elasticsearch-py) client.**
> `pyes` was the popular high-level Python ES wrapper from 2010 to ~2018, but
> it has been deprecated by the community in favour of `elasticsearch-py` +
> `elasticsearch-dsl`. This fork exists for **one reason only**: legacy
> codebases still importing `from pyes import ES` that need to keep running
> on Python 3.13 against modern Elasticsearch clusters. If that is you, read on.

This is a maintenance fork produced by [RepoRescue](https://github.com/RepoRescue),
upgrading the abandoned upstream (last release 0.99.x, ~2018, ES 1.x/2.x era)
to work against:

- **Python 3.13** (CPython, no `imp` / `cgi` / `distutils`)
- **`elasticsearch` 9.3.0** Python client (with the 8.x/9.x transport refactor)
- **`elastic-transport` 8+** (`response.meta.status` / `response.body` API)
- live **Elasticsearch 7.17 and 9.x** clusters

The high-level `pyes.ES / pyes.query / pyes.mappings` API is preserved
1-to-1, so existing call sites keep working.

---

## Install

```bash
# 1. Have an Elasticsearch instance reachable (7.17 LTS or 9.x both work)
docker run -d --name es -p 9200:9200 \
  -e "discovery.type=single-node" -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:7.17.20

# 2. Install pyes from this fork (see Caveat below for the .pth fallback)
git clone https://github.com/RepoRescue/pyes-rescue.git
cd pyes-rescue
python3.13 -m venv .venv && source .venv/bin/activate
pip install elasticsearch==9.3.0 urllib3==2.6.3 six
# Editable install currently fails (see "Known caveat" — packaging only, library works)
echo "$PWD" > .venv/lib/python3.13/site-packages/pyes.pth
```

## Quick start (≤15 lines)

```python
from pyes import ES
from pyes.query import MatchAllQuery, TermQuery, Search

conn = ES("http://localhost:9200")
conn.indices.create_index("demo")
conn.index({"title": "hello", "tag": "greet"}, "demo", "_doc", id=1)
conn.index({"title": "world", "tag": "greet"}, "demo", "_doc", id=2)
conn.indices.refresh("demo")

hits = list(conn.search(query=Search(MatchAllQuery()), indices=["demo"]))
assert len(hits) == 2
hit = list(conn.search(query=Search(TermQuery("tag.keyword", "greet")), indices=["demo"]))
assert {h["title"] for h in hit} == {"hello", "world"}
print("OK")
```

This script (and a 50-doc syslog scenario in `.reporescue/scenario_validate.py`)
both pass green against ES 7.17 — see the validation section below.

---

## What was actually broken under Python 3.13 + modern ES, and what this fork fixes

Upstream `pyes` was written against `elasticsearch-py` ≤2.x, which exposed
`(status, headers, data)` tuples from `perform_request` and accepted a flat
`hosts` list. Both contracts changed in the 8.x client refactor, and Python
3.13 also dropped `imp`. Concretely:

| File / line | Break | Fix in this fork |
|---|---|---|
| `pyes/es.py:423` | `Elasticsearch(http_servers, ...)` — newer client treats positional arg as something else, host list silently ignored, every request hits `localhost:9200` | Pass `hosts=http_servers` explicitly + rename `timeout=` → `request_timeout=` |
| `pyes/es.py:439-478` | Legacy `__perform_request` returned/expected `(status, headers, data)` tuples; `elastic-transport` 8+ returns `ApiResponse` with `.meta.status / .meta.headers / .body` | Rewritten to the new triple, plus `Content-Type` header injection via `headers=` kwarg |
| `pyes/utils/compat.py:24`, `pyes/five.py:20` | `import imp` → `ModuleNotFoundError` on Py3.13 | Replaced with `importlib.reload` |
| `pyes/utils/__init__.py:44` | `uuid.UUID().get_bytes()` removed in Py3 | Replaced with `.bytes` + `.decode('ascii')` |
| `pyes/convert_errors.py` | new error class names in `elasticsearch` 8.x | Mapping table updated |

> Trivia for benchmark readers: `claude-sonnet` missed the `pyes/es.py:423`
> hosts-passing fix and only made T2 unit tests pass while leaving real ES
> connections broken; `gpt-codex` (this fork) and `minimax` both got it right.
> That is exactly the kind of regression the unit-test-only T2 cannot catch.

---

## Validation evidence

This fork was end-to-end exercised against a live Elasticsearch 7.17
container, not just unit tests. See `.reporescue/`:

- **`usability_validate.py`** — clean Py3.13 venv → import sanity (`pyes.ES`,
  `pyes.query.{MatchAllQuery,TermQuery,BoolQuery}`, `pyes.mappings.{TextField,
  KeywordField,IntegerField}`) → create index → 3 docs → 4 query types →
  exact-title assertions. Result: **PASS**.
- **`scenario_validate.py`** — Path B "downstream developer reads README and
  writes a log-search service": indexes 50 syslog-style docs, runs
  `TermQuery`, `BoolQuery(must=[…])`, paginates 5 pages of 10, asserts exact
  expected counts (`ERROR=19`, `ERROR+billing=5`). Result: **PASS**.
- **`bug_hunt.py`** — adversarial probes (dead port, multi-script Unicode,
  repeated `ES()` instantiation, latent-import paths, direct underlying
  client access). Two **latent bugs** found, see next section.

---

## Known caveats — please read before using in production

This fork made the documented happy path work. Two issues remain, neither
on the default load graph but both real:

### 1. `pip install -e .` fails (packaging gap, library itself works)

`pyes/__init__.py:7` declares:

```python
VERSION = (7, 0, 0 , 'dev')   # note the extra space before the comma
```

`setup.py` joins this with `'.'` after splitting on `', '`, producing the
PEP-440-illegal string `'7.0.0 dev'`, which modern build backends reject:

```
packaging.version.InvalidVersion: '7.0.0 dev'
```

None of the rescue models (gpt-codex / minimax / sonnet) fixed this. The
recommended workaround is the `.pth` file shown in the install section.
Library functionality is unaffected.

### 2. `pyes/utils/imports.py:17` still does `import imp as _imp`

```
ModuleNotFoundError: No module named 'imp'
```

This is **not** on the default import graph (`from pyes import ES` does not
load it), but any caller of `pyes.utils.imports.symbol_by_name` /
`find_module` will crash on Py3.13. If you do not use those helpers, you
will not hit it. Easy three-line fix in a downstream PR.

### 3. `conn.connection.info()` direct-call mismatch

`elasticsearch` ≥8 client now passes `headers=`, `endpoint_id=`,
`otel_span=` kwargs through to `perform_request`. The `ES.__perform_request`
monkey-patch in `pyes/es.py` still has the signature
`(method, url, params=None, body=None)` and raises:

```
TypeError: ES.__perform_request() got an unexpected keyword argument 'headers'
```

The pyes-level high-level methods (`conn.index`, `conn.search`,
`conn.indices.*`) all go through `_send_request` and **sidestep** this
patch, so they work fine. But if your code reaches into
`conn.connection.<low-level>` directly, you will hit it. Trivial to fix
by accepting `**kwargs` in the patch.

---

## What this fork is **not**

- Not a replacement for `elasticsearch-py` / `elasticsearch-dsl`.
- Not feature-complete for ES 9.x — only the surfaces stressed by the
  validation scenarios (index management, document CRUD, `MatchAllQuery`,
  `TermQuery`, `BoolQuery`, pagination, `Search` envelope) were verified.
- Not maintained on a release schedule. PRs welcome but do not expect
  upstream-style attention.

If your dependency on pyes is only one or two call sites, **the cheapest
long-term fix is migrating those call sites to `elasticsearch-py` directly**.
This fork buys you time, not forever.

---

## Provenance

- Upstream: [aparo/pyes](https://github.com/aparo/pyes), BSD-3-Clause.
- Modernization patch: produced by [RepoRescue](https://github.com/RepoRescue),
  rescue model `gpt-codex`, see `UPGRADE_REPORT.md` and the original
  unified diff in `outputs/gpt-codex/pyes/pyes.src.patch` of the
  RepoRescue benchmark.
- This README and the `.reporescue/` validation scripts are part of the
  RepoRescue release pack.

## License

BSD-3-Clause, inherited from upstream. See `LICENSE`.
