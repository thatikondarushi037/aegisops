# v1.0.0 local release verification

Verification date: 2026-11-06. This records a local release candidate, not a
production certification. No commit, push or tag was created during this work.

## Git baseline and scope

`main` and remote `refs/heads/main` both resolved to
`00df6be8f5c6a7955f1f1c5c6775695570699c0f`. The annotated v0.18.0 tag object
is `369e1fa1dc91afb9f6bef5e1848443be07bf857e`, exists on the remote and peels
locally to the same assistant commit. Thus the assistant milestone is
committed, pushed and tagged. There was no tracked working-tree diff at entry.
Pre-existing untracked `agents/`, `cleanup_duplicates.sql` and
`tests/test_metrics_agent.py` remain outside the release. Nothing in those
paths was edited, deleted or staged.

Release changes are the README, this report, the technical demo guide,
architecture trade-offs, sanitized synthetic result JSON and screenshot,
two explicit verification scripts, Docker build-context exclusions and a
browser-test selector/output-directory improvement. Application code,
credentials, migrations and workflow definitions are unchanged.

## Automated verification

| Check | Passed | Failed | Skipped | Scope |
| --- | ---: | ---: | ---: | --- |
| Tracked Python regression | 156 | 0 | 2 | 28.66 s; generated schemas only in native `aegisops_test` |
| Final complete local Python suite | 159 | 0 | 2 | 25.68 s; includes the three preserved untracked metrics tests |
| Fresh Python environment regression | 156 | 0 | 2 | 25.46 s; same test DB isolation; one upstream TestClient deprecation warning |
| Opt-in real Ollama worker and assistant tests | 2 | 0 | 0 | 26.25 s; real runbooks/models, isolated test schemas |
| Unrelated local metrics experiment, separately | 3 | 0 | 0 | Preserved untracked; excluded from release scope |
| Node frontend tests | 6 | 0 | 0 | Status labels, safe text rendering, error handling, timeouts and citations |
| Chromium dashboard smoke after correction | 7 check groups | 0 | 0 | Login/session, filters, saved history, injection, job states, stale-data recovery, mobile, polling and logout |
| Live synthetic complete chain | 2 runs | 0 | 0 | Both new service names, real n8n, database, worker, Ollama, UI and assistant |

The two default Python skips are explicitly opt-in real-model smoke tests;
both were run separately and passed. Counts in different rows are separate
runs, not unique test totals. Tracked Python tests cover authentication/API
contracts, constraints and migrations, concurrent deduplication, scheduling,
retry/lease recovery, dashboard filtering/pagination and assistant bounded
retrieval/citations, missing records, malformed model output and safe rendering.

The first Chromium dashboard rerun failed because a strict locator assumed
exactly one completed job. The new synthetic job made two. The test now
checks the first matching completed badge, and the full browser smoke passed.
No application defect was hidden or application data reset. Browser output
can now be directed to an ignored directory with `AEGISOPS_SCREENSHOT_DIR`;
historical screenshots were preserved.

`pip check` passed in existing Python, fresh Python and isolated container
environments. `pip-audit 2.10.1 -r requirements.txt --no-deps --disable-pip`
queried the advisory service for **34 pinned dependencies: 0 known advisories**.
This is not a container/OS vulnerability audit or a guarantee of safety.
The scanner was installed into ignored `.env.release-tools`; its JSON output
is private. No application dependency was changed.

The repository secret helper checks tracked/release paths for the actual
configured long credentials and selected private-key/GitHub/AWS patterns.
It prints filenames only on failure and found no matches. It is a bounded
current-file scan, not full Git-history, entropy, PII or image OCR analysis.
Published new screenshots were visually reviewed for credentials/personal
information. `git diff --check` and Compose configuration validation passed.

## Active environment and data preservation

The deployed `aegisops-api-1` publishes only `127.0.0.1:8001`; the independent
`aegisops-worker-1` uses the Compose `postgres:17` database with no published
DB port. Existing n8n publishes only `127.0.0.1:5678` and is outside this
Compose project. Ollama runs on the Windows host. Models used are
`qwen2.5:3b` and `nomic-embed-text`.

Native Python `.env` points at `localhost:5432/aegisops`. That is a separate
database target from Compose's `db:5432/aegisops`. Regression tests use native
`aegisops_test`; live demonstration snapshots run inside the deployed API
against its actual Compose database. Native Alembic was at `d150b8e2a731`.
No existing service was restarted or reconfigured, including unrelated local
containers. No volume or existing database was deleted or cleared.

For each live demo the helper SELECTed every deployed incident,
investigation and job before/after, keyed by ID, and required exact equality
for every pre-existing row. All existing rows matched. New rows were checked
as exactly one incident, one automatic initial job and one investigation.

## Live end-to-end evidence

| Run | Incident | Investigation | Downstream API statuses | Job | Assistant |
| --- | ---: | ---: | --- | --- | --- |
| First synthetic service | 55 | 2 | 201, then 200; same ID | completed | grounded; saved investigation cited |
| Fresh synthetic service | 56 | 3 | 201, then 200; same ID | completed | grounded; saved investigation cited |

Both went through the already-published n8n workflow, authenticated FastAPI,
PostgreSQL queue, actual Ollama/RAG worker, saved result, actual Chromium
dashboard rendering and session-authenticated assistant retrieval. Each
investigation saved two metric evidence entries and
`requires_human_approval=true`. The incident remained open and had exactly
one `automatic_initial` job. The assistant selected real saved facts rather
than an invented result. The helper checks assistant citations through its
HTTP contract and the dashboard visually; interactive assistant rendering
also has existing milestone screenshots and automated rendering tests.

Initial counts were 50 incidents, 1 investigation and 1 job; final counts
were **52 incidents, 3 investigations and 3 jobs**. These two fictional demo
records are the only intended deployed data additions and remain available.
The sanitized [latest result](local-demo-result.json) records the second run;
the [current screenshot](screenshots/v1-demo-detail.png) shows its saved state.
Root cause was not established; runbook suggestions are not verified facts.

## Clean-start reproducibility

Verified without disturbing the existing deployment:

- Created ignored `.env.release-venv` with Python 3.14.5 and installed all
  pinned requirements successfully, then ran the complete tracked regression.
- Created a separate Compose project `aegisops-release-check`, separate
  network, fresh PostgreSQL volume and disposable credentials, with API
  publication at `127.0.0.1:18081`. Existing application credentials were not
  copied into this project.
- Built separate API/worker images from the current Dockerfile. The dependency
  layer used Docker cache; this was not a cache-free Linux dependency build.
- Applied the entire Alembic chain to its empty database, ending at
  `d150b8e2a731`. Started isolated API and worker. Container `pip check` passed;
  liveness returned 200, an unauthenticated incident request returned 401,
  and dashboard assets returned 200.
- The temporary project is stopped after verification; its newly created
  volume is retained. The ignored temporary Compose configuration remains
  local. No `down -v` or destructive cleanup was used.

The README's setup was reviewed against configuration and code. The existing
deployed login, workflow, models and assistant were exercised live. A new
n8n installation/import, fresh n8n credential creation/publication and a fresh
dashboard-password initialization were **not** repeated in the isolated
project. Models were already installed; a first-time model download and
offline installation were not tested. The isolated worker started against
an empty queue; real processing was verified in test schemas and in the
existing deployment instead. These limits prevent calling this a complete
blank-workstation certification.

## Release decision

No failing application regression or incomplete assistant milestone blocks
this local release candidate. Remaining validation gaps are the fresh n8n,
dashboard initialization, first model download and cache-free Linux build
items above. They must remain disclosed; a claim of fully tested clean-start
installation would require completing them. Shared-password local HTTP,
process-local sessions, open-service-only deduplication and imperfect runbook
relevance remain intentional limitations.

Before publishing, review the staged allowlist and this scope, then explicitly
commit/tag if accepted. Suggested commit:
`release: prepare AegisOps v1.0.0 local demonstration release`.
Suggested annotated tag: `v1.0.0`. Neither action is automatic.
