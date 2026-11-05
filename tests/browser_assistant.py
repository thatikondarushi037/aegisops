"""Read-only live assistant demo with real local Ollama, no database mutations.

Requires the existing .env.dashboard-login and Playwright (the ignored
.env.dashboard-qa installation is supported). No credentials are printed.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".env.dashboard-qa"))
from playwright.sync_api import sync_playwright, expect


def main():
    output = ROOT / ".env.assistant-qa"
    output.mkdir(exist_ok=True)
    screenshots = ROOT / "docs/screenshots"
    password = (ROOT / ".env.dashboard-login").read_text(encoding="utf-8").strip()
    results = []
    errors = []
    with sync_playwright() as p:
        paths = list((Path.home() / "AppData/Local/ms-playwright").glob("chromium-*/chrome-win*/chrome.exe"))
        browser = p.chromium.launch(headless=True, **({"executable_path": str(paths[-1])} if paths else {}))
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        bearer_headers = []
        page.on("request", lambda req: bearer_headers.append(req.headers.get("authorization")))
        page.goto("http://127.0.0.1:8001/dashboard")
        page.locator("#password").fill(password)
        page.locator("#login-submit").click()
        expect(page.locator("#workspace")).to_be_visible()
        page.locator('[data-view="incidents"]').click()
        page.locator("#service-filter").fill("v016-live-")
        page.locator('#incident-filters button[type="submit"]').click()
        expect(page.locator("#incident-table tbody tr")).to_have_count(1)
        page.locator("#incident-table .service-button").click()
        expect(page.locator("#detail-content .ask-incident")).to_be_visible()
        page.locator(".ask-incident").click()
        expect(page.locator("#assistant-view")).to_be_visible()
        expect(page.locator("#assistant-context")).to_have_value("54")

        def ask(message):
            page.locator("#assistant-input").fill(message)
            with page.expect_response(lambda response: response.url.endswith("/dashboard/api/assistant") and response.request.method == "POST", timeout=80000) as waiting:
                page.locator("#assistant-send").click()
            response = waiting.value
            assert response.status == 200
            data = response.json()
            expect(page.locator("#assistant-send")).to_be_enabled(timeout=10000)
            answer = data["answer"]
            result = {"question": message, "status": answer["status"], "tools_used": answer["tools_used"],
                      "context_incident_id": answer["context_incident_id"],
                      "incident_ids": sorted({f["incident_id"] for f in answer["facts"] if f["incident_id"]}),
                      "investigation_ids": sorted({f["investigation_id"] for f in answer["facts"] if f["investigation_id"]}),
                      "runbook_sources": sorted({f["runbook_source"] for f in answer["facts"] if f["runbook_source"]}),
                      "facts": answer["facts"]}
            results.append(result)
            (output / "live-demo.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in result.items() if k != "facts"}), flush=True)
            return answer

        def capture(name, focus=None):
            page.locator('#assistant-messages').evaluate("el => {const last=el.querySelector('.assistant-turn:last-child');if(last)el.scrollTop+=last.getBoundingClientRect().top-el.getBoundingClientRect().top-12;}")
            if focus:
                page.locator('#assistant-messages').evaluate("(el,focus) => {const last=el.querySelector('.assistant-turn:last-child');const card=[...last.querySelectorAll('.assistant-fact')].find(x=>x.textContent.includes(focus));if(card)el.scrollTop+=card.getBoundingClientRect().top-el.getBoundingClientRect().top-12;}", focus)
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(screenshots / name), full_page=True)

        answer = ask("What happened to incident 54?")
        assert answer["status"] == "grounded", "Real Qwen selection did not validate"
        assert any(f["investigation_id"] == 1 for f in answer["facts"])
        assert any(f["incident_id"] == 54 for f in answer["facts"])
        source = page.get_by_role("button", name="Investigation 1 · incident 54 ↗", exact=True).first
        source.click()
        expect(page.locator("#detail-dialog")).to_be_visible()
        expect(page.locator("#investigation-1")).to_be_visible()
        page.locator("#close-detail").click()
        answer = ask("What evidence supports its investigation?")
        assert any("Error rate" in f["text"] or "Latency" in f["text"] for f in answer["facts"])
        capture("v0.18-assistant-evidence.png", "Saved evidence")
        answer = ask("What does our runbook recommend checking?")
        assert answer["status"] == "grounded"
        assert "search_runbooks" in answer["tools_used"]
        assert any(f["runbook_source"] for f in answer["facts"])
        capture("v0.18-assistant-runbooks.png", "Runbook passage")
        answer = ask("What is the difference between observed symptoms and suspected cause?")
        assert any("not a proven explanation" in f["text"] for f in answer["facts"])
        answer = ask("What happened to incident 999999?")
        assert any("does not exist" in f["text"] for f in answer["facts"])
        assert not any(f["incident_id"] for f in answer["facts"])
        answer = ask("What evidence is available for incident 49?")
        assert any("No saved investigation" in f["text"] for f in answer["facts"])
        assert not any(f["category"] == "hypothesis" for f in answer["facts"])
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        capture("v0.18-assistant-mobile.png", "No saved investigation")
        page.reload()
        expect(page.locator("#workspace")).to_be_visible()
        page.locator('[data-view="assistant"]').click()
        expect(page.locator(".assistant-turn")).to_have_count(6)
        summary = page.request.get('http://127.0.0.1:8001/dashboard/api/overview').json()
        answer = ask('Show me the latest critical incidents.')
        assert answer['status'] == 'grounded'
        assert str(summary['critical_incidents']) + ' incidents match' in answer['facts'][0]['text']
        answer = ask('Are any AI investigation jobs failing?')
        assert answer['status'] == 'grounded'
        assert str(summary['jobs']['failed']) + ' incidents match' in answer['facts'][0]['text']
        # Test malicious UI input via interception only; never store it in PostgreSQL.
        malicious = {"message": "Safety fixture", "answer": {"status": "degraded", "introduction": "Safety fixture",
                     "notice": "Untrusted text must remain literal.", "tools_used": ["get_incident"], "context_incident_id": None,
                     "facts": [{"id": "fixture", "category": "observation", "text": '<img src=x onerror="window.assistantCompromised=true"><script>evil()</script>', "source": "UI fixture", "incident_id": None, "investigation_id": None, "runbook_source": None}]}}
        page.route("**/dashboard/api/assistant", lambda route: route.fulfill(json=malicious) if route.request.method == "POST" else route.continue_())
        page.locator("#assistant-input").fill("Safety fixture")
        page.locator("#assistant-send").click()
        expect(page.locator("#assistant-messages")).to_contain_text("<img src=x")
        assert page.locator("#assistant-messages img, #assistant-messages script").count() == 0
        assert page.evaluate("window.assistantCompromised === undefined")
        page.unroute("**/dashboard/api/assistant")
        page.locator("#assistant-clear").click()
        expect(page.locator(".assistant-turn")).to_have_count(0)
        page.locator("#logout").click()
        expect(page.locator("#login")).to_be_visible()
        assert page.request.get("http://127.0.0.1:8001/dashboard/api/assistant").status == 401
        assert page.locator("#assistant-messages").inner_text().find("incident 54") == -1
        assert not any(bearer_headers)
        assert not errors, "Browser runtime errors detected"
        browser.close()
    print('PASS: real Qwen/RAG conversation, linked sources, nonexistent record, unavailable evidence, session history, mobile, injection safety, clear and logout.', flush=True)


if __name__ == "__main__":
    main()
