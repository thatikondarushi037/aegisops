"""Append generated local credentials without displaying or replacing secrets."""
from pathlib import Path
import secrets

from dotenv import dotenv_values


def main():
    paths = [Path(__file__).resolve().parent / name for name in (".env", ".env.docker")]
    values = [dotenv_values(path) for path in paths]
    tokens = {}
    for key in ("AEGISOPS_OPERATOR_TOKEN", "AEGISOPS_N8N_TOKEN"):
        existing = {v[key] for v in values if v.get(key)}
        if len(existing) > 1:
            raise SystemExit(f"{key} differs between environment files; reconcile locally first.")
        tokens[key] = next(iter(existing)) if existing else secrets.token_urlsafe(48)
    if tokens["AEGISOPS_OPERATOR_TOKEN"] == tokens["AEGISOPS_N8N_TOKEN"]:
        raise SystemExit("Operator and n8n credentials must differ.")
    for path, current in zip(paths, values):
        if any(key in current and not current[key] for key in tokens):
            raise SystemExit("Remove empty authentication entries locally before running setup.")
    for path, current in zip(paths, values):
        additions = [f"{key}={value}" for key, value in tokens.items() if key not in current]
        if additions:
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n# AegisOps local API authentication\n" + "\n".join(additions) + "\n")
    print("Local authentication configured. Secrets remain in ignored environment files.")


if __name__ == "__main__":
    main()
