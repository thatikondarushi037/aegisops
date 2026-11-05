# Local project demonstration

This is a technical application walkthrough. It contains no interview
questions, study answers or company-specific preparation.

## Before the demonstration

Allow model warm-up time before starting the 3–5 minute walkthrough; model
latency varies. Open these tabs, using the existing private logins:

- Dashboard: http://127.0.0.1:8001/dashboard
- API documentation: http://127.0.0.1:8001/docs
- n8n editor: http://127.0.0.1:5678 (existing workflow; do not reimport)

```powershell
docker compose ps
ollama list
Invoke-RestMethod http://127.0.0.1:8001/
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

The API, database and one worker should be running, n8n's secure alert
workflow published, and `qwen2.5:3b` plus `nomic-embed-text` installed.
The dashboard password is in ignored `.env.dashboard-login`; do not display
that file, tokens, container environment dumps or private execution output.

## 3–5 minute script

1. **0:00–0:40:** Show the [architecture](architecture.md). Explain that n8n
   delivers alerts, FastAPI owns validation/authentication, PostgreSQL owns
   durable state, and the separate worker keeps inference off ingestion.
2. **0:40–1:20:** Show the n8n webhook → validation → authenticated HTTP →
   sanitized response flow. Keep credential dialogs closed. Send twice:

   ```powershell
   $service = 'demo-synthetic-' + [guid]::NewGuid().ToString('N').Substring(0,12)
   $body = @{service=$service; error_rate=15; latency=1200} | ConvertTo-Json
   $url = 'http://127.0.0.1:5678/webhook/aegisops-v016-alert'
   Invoke-RestMethod -Method Post -Uri $url -ContentType application/json -Body $body
   Invoke-RestMethod -Method Post -Uri $url -ContentType application/json -Body $body
   ```

   Example payload: `{"service":"demo-synthetic-example","error_rate":15,"latency":1200}`.
   Expect downstream `api_status` 201 then 200 and the same incident ID.
   Retain `$service` to filter the dashboard. Each fresh service adds one
   fictional record; do not delete old records or reset jobs for the demo.
3. **1:20–2:30:** In Incidents, filter by the exact service and open its detail.
   Show observed 15% error rate and 1200 ms latency, one open incident, one
   automatic job, and `pending → running → completed`. Fast completion can
   skip visible intermediate states. Retries can return a job to pending;
   exhausted attempts end in failed. Wait for the real completed state.
4. **2:30–3:20:** Show the saved investigation, evidence, confidence, hypothesis
   and human approval requirement. Unknown is a valid root-cause result.
   Runbook suggestions require validation; no remediation runs automatically.
5. **3:20–4:30:** Click **Ask assistant about this incident**. Ask “What
   happened to incident ID?” with the actual numeric ID, then “What evidence
   supports its investigation?” and “What does our runbook recommend
   checking?” Open a returned investigation citation and distinguish saved
   observations from hypotheses. For missing data use “What happened to
   incident 999999?”; expect a not-found response rather than invented evidence.
6. **4:30–5:00:** Explain open-service deduplication, durable retry/recovery,
   read-only assistant constraints and the local deployment boundary. Repeat
   with a fresh `$service` when another complete run is needed.

## Repeated automated verification

With local Playwright/Chromium available, the explicit helper performs the
live chain, checks citations through the assistant API, verifies actual
dashboard rendering, captures a synthetic screenshot and compares all
pre-existing deployed rows. It intentionally creates one fictional incident,
job and investigation per run and writes a sanitized result report:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_local_release.py
```

Playwright is optional tooling, not an application dependency. For a new
tooling installation, install it privately with `python -m pip install
--target .env.dashboard-qa playwright`, then use its Python module to install
Chromium (set `PYTHONPATH` to that directory). The helper expects the private
generated dashboard password file and the standard local ports.

## Recovery without resetting data

- **Ollama unavailable:** Check `ollama list`, start the local Ollama service
  (`ollama serve` only if it is not already running), then recheck `/api/tags`.
  Inspect the dashboard's job state. Due retries resume within the attempt
  limit. An exhausted failed job is not automatically reset: use a fresh
  synthetic service after restoring inference. The assistant can show an
  explicitly degraded retrieved-facts answer. Do not present it as a successful
  live model run.
- **n8n unavailable:** Check its existing container and restart only that
  known container if necessary. Open the editor, verify publication and the
  selected ingestion credential. Retry the same payload after an ambiguous
  response to use open-service deduplication. Never reset n8n's volume or
  encryption key. A direct operator-authenticated API submission is a partial
  fallback only; label the n8n segment unverified in that run.
- **Worker stopped:** `docker compose --profile worker up -d worker`. It can
  claim any older due job first. Allow expired leases to recover normally.
  Do not clear jobs, run SQL repairs or reset attempts to speed up the demo.
- **API restart/session expired:** Sign in again. Browser sessions and chat
  history are process-local; PostgreSQL investigations survive restart.

See [verified results and remaining limits](release-verification.md) and
[component responsibilities and engineering trade-offs](architecture.md).
