"""Configure a separate local dashboard login; never prints credentials."""
import argparse
import getpass
from pathlib import Path
import secrets

from dotenv import dotenv_values
from dashboard_auth import password_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", help="Store a generated login privately in ignored .env.dashboard-login")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    paths = [root / ".env", root / ".env.docker"]
    values = [dotenv_values(path) for path in paths]
    existing = {value.get("DASHBOARD_PASSWORD_HASH") for value in values if value.get("DASHBOARD_PASSWORD_HASH")}
    if len(existing) > 1:
        raise SystemExit("Dashboard hashes differ between local environment files; reconcile locally.")
    if any("DASHBOARD_PASSWORD_HASH" in value and not value["DASHBOARD_PASSWORD_HASH"] for value in values):
        raise SystemExit("Remove empty dashboard hash entries before configuring.")
    if existing:
        hashed = next(iter(existing))
    else:
        password = secrets.token_urlsafe(24) if args.generate else getpass.getpass("New dashboard password (at least 12 characters): ")
        if len(password) < 12 or len(password) > 512:
            raise SystemExit("Use 12 to 512 characters.")
        if not args.generate and password != getpass.getpass("Confirm dashboard password: "):
            raise SystemExit("Passwords do not match.")
        if any(password == value.get(key) for value in values for key in ("AEGISOPS_OPERATOR_TOKEN", "AEGISOPS_N8N_TOKEN")):
            raise SystemExit("Use a separate dashboard password, not an API token.")
        hashed = password_hash(password)
        if args.generate:
            private = root / ".env.dashboard-login"
            with private.open("x", encoding="utf-8") as output:
                output.write(password + "\n")
    for path, value in zip(paths, values):
        with path.open("a", encoding="utf-8") as output:
            if "DASHBOARD_PASSWORD_HASH" not in value:
                output.write(f"\n# Local browser login (separate from API credentials)\nDASHBOARD_PASSWORD_HASH='{hashed}'\n")
            if "DASHBOARD_ORIGIN" not in value:
                output.write("DASHBOARD_ORIGIN=http://127.0.0.1:8001\n")
    print("Dashboard login configured in ignored environment files. Restart the API to apply.")
    if args.generate:
        print("Generated login, if newly created, is in the private .env.dashboard-login file. Do not share it.")


if __name__ == "__main__":
    main()
