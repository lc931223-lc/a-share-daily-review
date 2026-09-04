from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_previous_review(trade_date: date) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = sorted((PROJECT_ROOT / "data" / "json" / "reviews").glob("*.json"))
    previous = None
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload_date = date.fromisoformat(str(payload.get("date")))
        except Exception:
            continue
        if payload_date < trade_date and (previous is None or payload_date > previous[0]):
            previous = (payload_date, path, payload)
    if previous is None:
        return {}, {}
    _, path, payload = previous
    previous_review = {
        "source_path": str(path),
        "date": payload.get("date"),
        "themes": [
            {
                "name": item.get("name"),
                "score": (item.get("scores") or {}).get("total_score"),
                "rating": (item.get("scores") or {}).get("rating"),
                "stage": item.get("stage"),
            }
            for item in payload.get("main_themes", [])
        ],
        "stocks": [
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "theme": item.get("theme"),
                "role": item.get("role"),
            }
            for item in payload.get("stocks", [])
        ],
    }
    tomorrow_context = {
        "source_path": str(path),
        "checks": payload.get("tomorrow_checks", []),
        "changes_vs_previous_day": payload.get("changes_vs_previous_day", {}),
    }
    return previous_review, tomorrow_context
