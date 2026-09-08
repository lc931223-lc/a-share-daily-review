from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.formal_review.persistence import import_record, import_inbox


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and import a ChatGPT formal review v3 record.")
    parser.add_argument("path", nargs="?")
    parser.add_argument("--inbox", action="store_true")
    args = parser.parse_args(argv)
    if args.inbox:
        results = import_inbox(ROOT)
        print(json.dumps(results, ensure_ascii=False))
        return 2 if any(row["status"] == "REJECTED" for row in results) else 0
    if not args.path:
        parser.error("path or --inbox required")
    payload = json.loads(sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8"))
    print(json.dumps(import_record(ROOT, payload), ensure_ascii=False))
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
