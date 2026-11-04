"""Write the API's OpenAPI schema to apps/web/openapi.json, the source the web app generates its API types from.

Usage (in apps/backend): python -m scripts.export_openapi
Then in apps/web: npm run gen:api. CI fails when the committed schema or types are out of date.
"""

import json
from pathlib import Path

from app.main import app

TARGET = Path(__file__).resolve().parents[2] / "web" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    # The version is baked in at release time; keep it out so the file only changes when the API does
    schema["info"]["version"] = "dev"
    # LF on every OS: CI regenerates this on Linux and diffs it against the committed file
    TARGET.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
