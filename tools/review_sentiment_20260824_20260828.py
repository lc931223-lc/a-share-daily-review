from __future__ import annotations

import json

from a_share_sentiment_engine import json_safe, run_engine


def main() -> int:
    result, json_path, report_path = run_engine(
        "20260824",
        "20260828",
        generated_at="2026-08-30",
    )
    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    print(f"JSON saved to {json_path}")
    if report_path:
        print(f"Report saved to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
