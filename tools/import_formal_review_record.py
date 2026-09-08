from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.formal_review.support import validate_formal_review_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and import a ChatGPT formal review v3 record.")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    source = Path(args.path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_formal_review_record(payload, schema_root=ROOT)
    trade_date = str(payload["date"])
    target_dir = ROOT / "data" / "formal_reviews"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{trade_date}.json"
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        existing_canonical = json.dumps(
            existing, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if hashlib.sha256(existing_canonical).digest() != hashlib.sha256(canonical).digest():
            raise RuntimeError(f"formal review already exists with different content: {target}")
        print(f"formal_review={target}")
        print("status=UNCHANGED")
        return 0
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    print(f"formal_review={target}")
    print("status=IMPORTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
