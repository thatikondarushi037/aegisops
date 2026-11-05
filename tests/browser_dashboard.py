"""Explicit, read-only Chromium smoke against an already running local API.

Run with Playwright installed (or in ignored .env.dashboard-qa).
The generated dashboard login is read privately; no credentials are printed.
"""
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / ".env.dashboard-qa").exists():
    sys.path.insert(0, str(ROOT / ".env.dashboard-qa"))
from playwright.sync_api import sync_playwright, expect


def main():
    base = "http://127.0.0.1:8001"
    password = (ROOT / ".env.dashboard-login").read_text(encoding="utf-8").strip()
    screenshots = Path(os.getenv("AEGISOPS_SCREENSHOT_DIR", str(ROOT / "docs/screenshots")))
    screenshots.mkdir(exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as p:
        binaries = list((Path.home() / "AppData/Local/ms-playwright").glob("chromium-*/chrome-win*/chrome.exe"))
        browser = p.chromium.launch(headless=True, **({"executable_path": str(binaries[-1])} if binaries else {}))
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        browser_auth = []
        page.on("request", lambda request: browser_auth.append(request.headers.get("authorization")))
        page.goto(base + "/dashboard")
        expect(page.locator("#login")).to_be_visible()
        page.screenshot(path=str(screenshots / "v0.17-login.png"), full_page=True)
        page.locator("#password").fill(password)
        page.locator("#login-submit").click()
        expect(page.locator("#workspace")).to_be_visible()
        expect(page.locator("#stat-total")).not_to_have_text("—")
        assert page.locator("#password").input_value() == ""
        cookie = next(c for c in context.cookies() if c["name"] == "aegisops_dashboard")
        assert cookie["httpOnly"] and cookie["sameSite"] == "Strict"
        assert "aegisops_dashboard" not in page.evaluate("document.cookie")
        assert page.evaluate("localStorage.length + sessionStorage.length") == 0
        summary = page.request.get(base + "/dashboard/api/overview").json()
        assert page.locator("#stat-total").inner_text() == str(summary["total_incidents"])
        page.screenshot(path=str(screenshots / "v0.17-overview-desktop.png"), full_page=True)
        checks.append("login, HttpOnly session, real PostgreSQL aggregates, no browser Bearer or storage")

        page.locator('[data-view="incidents"]').click()
        page.locator("#service-filter").fill("v016-live-")
        page.locator('#incident-filters button[type="submit"]').click()
        expect(page.locator("#incident-table tbody tr")).to_have_count(1)
        page.wait_for_timeout(8500)
        expect(page.locator("#service-filter")).to_have_value("v016-live-")
        expect(page.locator("#incident-table tbody tr")).to_have_count(1)
        page.locator("#incident-table .service-button").click()
        expect(page.locator("#detail-dialog")).to_be_visible()
        expect(page.locator("#detail-content .investigation")).to_have_count(1)
        expect(page.locator("#detail-content")).to_contain_text("Human approval required")
        page.screenshot(path=str(screenshots / "v0.17-incident-detail.png"), full_page=True)
        checks.append("filters persist through automatic refresh; saved AI evidence, hypothesis and history")

        incident = page.request.get(base + "/dashboard/api/incidents?service=v016-live-").json()["items"][0]
        history_url = base + f"/dashboard/api/incidents/{incident['id']}/history?limit=5&offset=0"
        history = page.request.get(history_url).json()
        history["items"][0]["suspected_root_cause"] = '<img src=x onerror="window.dashboardCompromised=true">'
        history["items"][0]["evidence"] = ['<script>window.dashboardCompromised=true</script>']
        page.locator("#close-detail").click()
        page.route("**/dashboard/api/incidents/*/history?*", lambda route: route.fulfill(json=history))
        page.locator("#incident-table .service-button").click()
        expect(page.locator("#detail-content")).to_contain_text("<img src=x")
        assert page.locator("#detail-content img, #detail-content script").count() == 0
        assert page.evaluate("window.dashboardCompromised === undefined")
        page.locator("#close-detail").click()
        page.unroute("**/dashboard/api/incidents/*/history?*")
        checks.append("adversarial AI response remains literal text; no DOM injection or script execution")

        page.locator('[data-view="automation"]').click()
        expect(page.locator("#job-table .badge.completed").first).to_be_visible()
        expect(page.locator("#automation-view")).to_contain_text("n8n execution history is not available")
        page.screenshot(path=str(screenshots / "v0.17-automation.png"), full_page=True)
        page.route("**/dashboard/api/overview", lambda route: route.fulfill(status=503, json={"detail": "PRIVATE_BACKEND_DETAIL"}))
        page.locator("#refresh").click()
        expect(page.locator("#data-error")).to_be_visible()
        expect(page.locator("#refresh-status")).to_contain_text("Stale data")
        assert "PRIVATE_BACKEND_DETAIL" not in page.locator("body").inner_text()
        page.unroute("**/dashboard/api/overview")
        page.locator("#refresh").click()
        expect(page.locator("#data-error")).to_be_hidden()
        checks.append("real completed job status; sanitized backend failure, stale-data indicator and recovery")

        page.locator('[data-view="incidents"]').click()
        page.locator("#service-filter").fill("no-such-service-dashboard-smoke")
        page.locator('#incident-filters button[type="submit"]').click()
        expect(page.locator("#incident-table")).to_contain_text("No incidents to display")
        page.locator('[data-view="overview"]').click()
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("#stat-total")).not_to_have_text("—")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(screenshots / "v0.17-overview-mobile.png"), full_page=True)
        checks.append("empty state and 390px mobile layout without page overflow")

        requests_before = []
        page.on("request", lambda req: requests_before.append(req.url) if "/dashboard/api/overview" in req.url else None)
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true,get:()=>true}); document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(9000)
        assert not requests_before
        page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
        checks.append("polling pauses when the page is hidden")
        page.locator("#logout").click()
        expect(page.locator("#login")).to_be_visible()
        assert page.request.get(base + "/dashboard/api/overview").status == 401
        assert page.locator("#recent-table").inner_text() == ""
        assert not any(browser_auth)
        assert not errors, "Browser runtime errors occurred"
        checks.append("CSRF-protected logout revokes the session and clears displayed data; no page errors")
        browser.close()
    result = {"checks": checks, "screenshots": 5, "viewport": ["1440x1080", "390x844"]}
    (ROOT / ".env.dashboard-qa/browser-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
