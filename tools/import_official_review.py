from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.import_service import ReviewImportError, import_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and import a ChatGPT official A-share review JSON.")
    parser.add_argument("path", help="Path to data/official_reviews/YYYY-MM-DD.json")
    parser.add_argument("--database", default=None, help="Optional SQLite database path")
    args = parser.parse_args(argv)

    path = Path(args.path)
    schema = json.loads((PROJECT_ROOT / "schemas" / "official_review.schema.json").read_text(encoding="utf-8"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    try:
        result = import_review(path, database_path=args.database)
    except ReviewImportError as exc:
        print(f"import_status=FAILED")
        print(f"error={exc}")
        return 3
    print("import_status=SUCCESS")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
