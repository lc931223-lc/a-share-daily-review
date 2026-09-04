import argparse
import json
import sys

from src.services.import_service import ReviewImportError, import_review


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导入标准化 A 股每日复盘 JSON")
    parser.add_argument("json_file")
    parser.add_argument("--database")
    parser.add_argument("--archive-dir")
    args = parser.parse_args()
    try:
        result = import_review(args.json_file, args.database, args.archive_dir)
    except (OSError, ReviewImportError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
