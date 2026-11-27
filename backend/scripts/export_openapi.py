"""Write (or check) the committed OpenAPI spec at ``docs/openapi.json``.

The committed spec is the contract generated clients (the MCP server, and
anything else built from the API) are checked against in CI, so it must be
regenerated whenever a route, parameter or schema changes:

    cd backend && python scripts/export_openapi.py          # rewrite
    cd backend && python scripts/export_openapi.py --check  # CI: fail if stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SPEC_PATH = BACKEND.parent / "docs" / "openapi.json"
# The deployed version is a build arg; keep the snapshot version-independent.
SNAPSHOT_VERSION = "0.0.0-snapshot"


def render() -> str:
    sys.path.insert(0, str(BACKEND))
    from app.main import app

    spec = json.loads(json.dumps(app.openapi()))
    spec["info"]["version"] = SNAPSHOT_VERSION
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()

    current = render()
    if args.check:
        committed = SPEC_PATH.read_text() if SPEC_PATH.exists() else ""
        if committed != current:
            print(
                f"{SPEC_PATH.relative_to(BACKEND.parent)} is out of date with the API. "
                "Run: cd backend && python scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        print("OpenAPI spec is up to date.")
        return 0
    SPEC_PATH.write_text(current)
    print(f"Wrote {SPEC_PATH.relative_to(BACKEND.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
