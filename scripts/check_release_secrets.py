"""Check tracked/release files without printing secret values. Not a full DLP scan."""
from pathlib import Path
import re
import subprocess

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
files = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")) - {""}
files.update(["README.md", "docs/interview-demo.md", "docs/release-verification.md",
              "docs/local-demo-result.json", "docs/screenshots/v1-demo-detail.png",
              "scripts/verify_local_release.py", "scripts/check_release_secrets.py"])
secrets = set()
for name in [".env", ".env.docker"]:
    for key, value in dotenv_values(ROOT / name).items():
        if value and len(value) >= 12 and any(k in key for k in ["PASSWORD", "TOKEN", "SECRET", "KEY"]):
            secrets.add(value.encode())
private = ROOT / ".env.dashboard-login"
if private.exists():
    secrets.add(private.read_bytes().strip())
patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"AKIA[A-Z0-9]{16}"]
failures = []
for name in sorted(files):
    path = ROOT / name
    if not path.is_file():
        continue
    data = path.read_bytes()
    if any(secret in data for secret in secrets) or any(re.search(pattern, data) for pattern in patterns):
        failures.append(name)
if failures:
    raise SystemExit("Potential secrets in: " + ", ".join(failures))
print(f"PASS: {len(files)} tracked/release paths checked; no known deployment secrets or selected credential patterns.")
