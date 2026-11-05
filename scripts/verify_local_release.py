"""Explicit live synthetic demo. Adds one incident/job/result; never deletes data.

Run from the repository root against the existing loopback deployment.
Credentials are read privately. Output contains only synthetic IDs and states.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8001"


def snapshot():
    code = """import json
from database import engine
from sqlalchemy import text
with engine.connect() as c:
 print(json.dumps({t:c.execute(text('SELECT row_to_json(r) FROM '+t+' r ORDER BY id')).scalars().all() for t in ['incidents','investigations','investigation_jobs']}))
"""
    result = subprocess.run(["docker", "compose", "exec", "-T", "api", "python", "-c", code],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main():
    before = snapshot()
    service = "demo-synthetic-" + uuid4().hex[:12]
    payload = {"service": service, "error_rate": 15, "latency": 1200}
    deliveries = []
    for expected in [201, 200]:
        r = requests.post("http://127.0.0.1:5678/webhook/aegisops-v016-alert", json=payload, timeout=45)
        r.raise_for_status()
        data = r.json()
        assert data["api_status"] == expected, data
        deliveries.append(data)
    incident_id = deliveries[0]["incident_id"]
    assert deliveries[1]["incident_id"] == incident_id
    session = requests.Session()
    session.headers["Origin"] = BASE
    r = session.post(BASE + "/dashboard/login", json={"password": (ROOT / ".env.dashboard-login").read_text().strip()}, timeout=15)
    r.raise_for_status()
    session.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    def get(path):
        r = session.get(BASE + "/dashboard/api" + path, timeout=15)
        r.raise_for_status()
        return r.json()
    deadline = time.monotonic() + 420
    while True:
        detail = get(f"/incidents/{incident_id}")
        status = detail["job"]["status"]
        if status in {"completed", "failed"} or time.monotonic() > deadline:
            break
        print(json.dumps({"incident_id": incident_id, "job": status}), flush=True)
        time.sleep(5)
    assert status == "completed", status
    history = get(f"/incidents/{incident_id}/history")
    assert history["total"] == 1
    investigation = history["items"][0]
    assert investigation["evidence"] and investigation["requires_human_approval"]
    listing = get("/incidents?service=" + service)
    assert listing["total"] == 1 and listing["items"][0]["id"] == incident_id
    r = session.post(BASE + "/dashboard/api/assistant", json={"message": f"What evidence supports incident {incident_id}?", "incident_id": incident_id}, timeout=90)
    r.raise_for_status()
    answer = r.json()["answer"]
    assert any(f["investigation_id"] == investigation["id"] for f in answer["facts"])
    # Verify the actual record is rendered in Chromium, with no login captured.
    sys.path.insert(0, str(ROOT / ".env.dashboard-qa"))
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as p:
        binaries = list((Path.home() / "AppData/Local/ms-playwright").glob("chromium-*/chrome-win*/chrome.exe"))
        browser = p.chromium.launch(headless=True, **({"executable_path": str(binaries[-1])} if binaries else {}))
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.goto(BASE + "/dashboard")
        page.locator("#password").fill((ROOT / ".env.dashboard-login").read_text().strip())
        page.locator("#login-submit").click()
        expect(page.locator("#workspace")).to_be_visible()
        page.locator('[data-view="incidents"]').click()
        page.locator("#service-filter").fill(service)
        page.locator('#incident-filters button[type="submit"]').click()
        expect(page.locator("#incident-table tbody tr")).to_have_count(1)
        page.locator("#incident-table .service-button").click()
        expect(page.locator("#detail-content")).to_contain_text(service)
        page.screenshot(path=str(ROOT / "docs/screenshots/v1-demo-detail.png"), full_page=True)
        browser.close()
    after = snapshot()
    for table, rows in before.items():
        current = {r["id"]: r for r in after[table]}
        assert all(current.get(row["id"]) == row for row in rows), table + " existing rows changed"
    new = {t: [r for r in after[t] if r["id"] not in {x["id"] for x in before[t]}] for t in before}
    assert all(len(rows) == 1 for rows in new.values())
    assert new["incidents"][0]["status"] == "open"
    assert new["investigation_jobs"][0]["trigger"] == "automatic_initial"
    session.post(BASE + "/dashboard/logout", timeout=15).raise_for_status()
    report = {"service": service, "incident_id": incident_id, "investigation_id": investigation["id"],
              "api_statuses": [d["api_status"] for d in deliveries], "job": status,
              "assistant": answer["status"], "saved_evidence_entries": len(investigation["evidence"]),
              "human_approval_required": True, "existing_rows_unchanged": True,
              "before_counts": {t: len(r) for t, r in before.items()},
              "after_counts": {t: len(r) for t, r in after.items()}}
    (ROOT / "docs/local-demo-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
