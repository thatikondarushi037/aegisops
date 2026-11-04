"""Execute exported Code nodes; live n8n routing is a separate verification."""
import json
from pathlib import Path
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests
import monitor_simulator as simulator

WORKFLOW = json.loads((Path(__file__).resolve().parents[1] / "workflows/aegisops-v0.16.0.json").read_text())


def code(name, payload):
    node = next(n for n in WORKFLOW["nodes"] if n["name"] == name)
    if not shutil.which("node"):
        pytest.skip("Node.js required to execute n8n Code nodes")
    script = "const $json=" + json.dumps(payload) + "; const run=()=>{" + node["parameters"]["jsCode"] + "}; console.log(JSON.stringify(run()[0].json));"
    return json.loads(subprocess.run(["node"], input=script, text=True, capture_output=True, check=True, timeout=10).stdout)


@pytest.mark.parametrize("body", [None, [], {}, {"service":" "},
    {"service":"x","error_rate":101,"latency":0},
    {"service":"x","error_rate":"5","latency":0},
    {"service":"x","error_rate":5,"latency":-1},
    {"service":"x","error_rate":5,"latency":1.5}])
def test_webhook_rejects_malformed(body):
    result = code("Validate alert", {"body":body})
    assert result["valid"] is False and result["statusCode"] == 422
    assert "payload" not in result


def test_webhook_whitelists_payload():
    body = {"service":"demo","error_rate":15,"latency":900}
    assert code("Validate alert", {"body":dict(body, authorization="private")}) == {"valid":True,"payload":body}


@pytest.mark.parametrize("status", [200, 201])
def test_records_incident_and_status(status):
    assert code("Sanitize delivery result", {"statusCode":status,"body":{"id":42}}) == {
        "statusCode":status,"incident_id":42,"api_status":status,"delivery":"accepted"}


def test_failure_sanitization_and_bounded_workflow():
    result = code("Sanitize delivery result", {"error":"secret credentials and private URL"})
    assert result["statusCode"] == 502
    assert "secret" not in json.dumps(result)
    http = next(n for n in WORKFLOW["nodes"] if n["type"].endswith(".httpRequest"))
    assert http["retryOnFail"] and http["maxTries"] == 3
    assert http["parameters"]["options"]["timeout"] == 10000
    assert http["parameters"]["url"] == "http://host.docker.internal:8001/incidents"
    assert "credentials" not in http
    assert WORKFLOW["active"] is False


@pytest.mark.parametrize("status,category", [
    (401, "backend_authorization_failed"),
    (403, "backend_authorization_failed"),
    (503, "backend_transient_failure"),
    (429, "backend_transient_failure"),
])
def test_preserves_safe_failure_details(status, category):
    result = code("Sanitize delivery result", {
        "error": {"httpCode": str(status), "message": "private credentials"},
    })
    assert result["api_status"] == status
    assert result["error_category"] == category
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("failures,expected_calls", [(2,3),(20,4)])
def test_simulator_transient_delivery(monkeypatch, failures, expected_calls):
    calls = []
    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            status = 503 if len(calls) <= failures else 201
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"incident_id":42}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(simulator, "API_URL", f"http://127.0.0.1:{server.server_port}/webhook")
    monkeypatch.setattr("urllib3.util.retry.Retry.sleep", lambda *_: None)
    payload = {"service":"retry-demo","error_rate":15,"latency":900}
    try:
        if failures > 3:
            with pytest.raises(requests.RequestException):
                simulator.send_metrics(payload)
        else:
            assert simulator.send_metrics(payload)["incident_id"] == 42
        assert calls == [payload] * expected_calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
