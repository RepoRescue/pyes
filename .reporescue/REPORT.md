# pyes — Usability Validation (gpt-codex)

**Selected rescue**: gpt-codex (T2 PASS, srconly PASS)
**Scenario type**: B (End-user library API)
**Real-world use**: pyes is a high-level Python wrapper around the
elasticsearch-py client. People used it to talk to Elasticsearch clusters
with a Django-ORM-like API (`ES("host:9200").indices.create_index(...)`
+ `pyes.query` + `pyes.mappings`). Last upstream release ~2018, ES 7.x era.

## Step 0: Import sanity
```
repos/rescue_gpt-codex/pyes/venv-t2/bin/python -c "import pyes" → OK (pyes 7.0.0dev)
from pyes import ES                                              → OK
from pyes.query import MatchAllQuery, TermQuery, BoolQuery       → OK
from pyes.mappings import TextField, KeywordField, IntegerField  → OK
```

## Step 4: Install + core feature (clean venv)
- `python3.13 -m venv /tmp/pyes-clean`
- `pip install elasticsearch==9.3.0 urllib3==2.6.3 six` → OK
- `pip install -e <rescue>` → **FAIL**
  - Build backend rejects setup.py: `packaging.version.InvalidVersion: '7.0.0 dev'`
  - Root cause: `pyes/__init__.py:7` declares `VERSION = (7, 0, 0 , 'dev')`
    (extra space before comma); `setup.py:21,32` regex splits on `", "` so
    the third token becomes `'0 '` (trailing space) → joined version is
    `'7.0.0 dev'`, which violates PEP 440.
  - gpt-codex did not fix this (neither did minimax/sonnet).
- Fallback (matches T2 wrapper): `.pth` file pointing at the rescue tree → OK
- Core feature (high-level pyes API): create index → index 3 docs → search
  via `MatchAllQuery / TermQuery / BoolQuery / Search` → assertions on
  exact returned titles → **PASS** against live ES 7.17 docker container.

## Hard constraint 6: Py3.13 surface stressed
| Surface | Evidence |
|---|---|
| elasticsearch-py 7.x→8/9 client refactor | pyes/es.py:413,420,423: `from elasticsearch import Elasticsearch`, `Elasticsearch(http_servers, ..., request_timeout=...)` (was `timeout=`) |
| elastic_transport 8+ `perform_request` API | pyes/es.py:439-478: `__perform_request` rewritten — `response.meta.status / response.meta.headers / response.body` triple replaced legacy `(status, headers, data)` tuple |
| collections.abc / six fallout | imported transitively via `pyes.utils.compat` (import OK) |
| Removed stdlib `imp` | pyes/utils/imports.py:17 still `import imp as _imp` → **gpt-codex did NOT fix** (see bug-hunt #4). Not on the default-load path so not fatal at top-level import. |

Diff-based confirmation (`outputs/gpt-codex/pyes/pyes.src.patch`): es.py and
convert_errors.py touched; utils/imports.py untouched.

## Beyond unit tests (constraint 3)
- T2 ran only `tests/test_scriptfields.py` (2 trivial tests on
  `ScriptFields.serialize()`); see validation/pyes/t2_gpt-codex.sh:43
- `grep -rn "create_index\|MatchAllQuery\|TermQuery\|conn.search" tests/`
  shows existing tests **require a live ES** (skipped in T2). Our
  validate.py drives a live ES 7.17 container — the canonical usage path
  not exercised by T2.

## Step 6: Downstream / Scenario
- Path A (downstream library, star ≥100, active): not attempted —
  pyes has been deprecated in favour of `elasticsearch-dsl` since ~2017,
  no live downstream importing pyes today.
- Path B (`scenario_validate.py`): 60-line "log search" business
  workflow — index 50 syslog-style docs, run TermQuery / BoolQuery /
  pagination, all via pyes high-level API → **PASS** with all
  assertions matching expected counts (`ERROR=19, ERROR+billing=5`).

## Step 7: Bug-hunt
Tried in `bug_hunt.py`:
1. Dead port: pyes raises `ConnectionError` ✅
2. Unicode (CN/GR/AR multi-script) round-trip ✅
3. Repeated `ES()` instantiation × 5: monkey-patch survives ✅
4. **FOUND**: `import pyes.utils.imports` → `ModuleNotFoundError: No module
   named 'imp'` (pyes/utils/imports.py:17). Latent — not on default
   import graph, but any caller of `symbol_by_name` / `find_module`
   crashes on Py3.13.
5. **FOUND**: `conn.connection.info()` (direct underlying ES client) →
   `TypeError: ES.__perform_request() got an unexpected keyword argument
   'headers'` (pyes/es.py:439). The monkey-patch signature
   `(method, url, params=None, body=None)` doesn't accept the
   `headers/endpoint_id/otel_span` kwargs that elasticsearch ≥7 client
   now passes. Doesn't break pyes's own high-level methods (they call
   `_send_request` which sidesteps the patched function), but bites any
   downstream that reaches into `conn.connection`.

## Verdict
STATUS: USABLE

Reason: All 8 hard constraints satisfied for the documented pyes API
surface (clean-venv install via `.pth` fallback succeeds, three distinct
submodules `pyes.es / pyes.query / pyes.mappings` all execute against a
real Elasticsearch 7.17 container, multiple Py3.13 break-points stressed
and proven fixed in es.py, README scenario passes). Two latent bugs
exist (uncovered by T2's 2-test suite) — flagged in bug_hunt for the
GitHub-org PR, but they don't block the documented happy path so the
fix is publishable.
