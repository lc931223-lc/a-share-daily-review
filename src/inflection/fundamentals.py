from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
CATEGORY_POINTS = {
    "earnings": ("earnings", 10), "order": ("order_customer_capacity", 7),
    "contract": ("order_customer_capacity", 7), "customer": ("order_customer_capacity", 7),
    "product": ("order_customer_capacity", 5), "capacity": ("order_customer_capacity", 6),
    "restructuring": ("policy_capital", 5), "buyback": ("policy_capital", 4),
    "increase_holding": ("policy_capital", 4),
}


def load_fundamental_features(root: Path, target: date) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cutoff = datetime.combine(target, time(15, 5), SHANGHAI_TZ)
    packet = _read_json(root / "data" / "market_packets" / f"{target.isoformat()}.json", {})
    records = list((packet.get("announcements") or {}).get("records") or [])
    by_code: dict[str, list[dict[str, Any]]] = {}
    future_rejected = 0
    for item in records:
        published = _parse_datetime(item.get("published_at"))
        if published is None or published > cutoff:
            future_rejected += 1
            continue
        code = _with_suffix(item.get("stock_code"))
        if code:
            by_code.setdefault(code, []).append(item)
    result = {code: _score_catalysts(items) for code, items in by_code.items()}
    status = "AVAILABLE" if records else "UNAVAILABLE"
    return result, {"status": status, "record_count": len(records), "future_rejected": future_rejected}


def _score_catalysts(items: list[dict[str, Any]]) -> dict[str, Any]:
    components = {"earnings": 0, "price_supply": 0, "order_customer_capacity": 0, "policy_capital": 0}
    accepted = []
    for item in items:
        if item.get("confirmed_fact") is False or item.get("quality_status") in {"INVALID", "UNAVAILABLE"}:
            continue
        component, points = CATEGORY_POINTS.get(str(item.get("category") or ""), (None, 0))
        if component:
            components[component] = max(components[component], points)
            accepted.append(item)
    score = min(30, sum(components.values()))
    main = accepted[0] if accepted else None
    return {
        "fundamental_inflection_score": score,
        "score_components": components,
        "main_catalyst": main.get("title") if main else None,
        "catalyst_stage": _stage(main) if main else None,
        "evidence_level": main.get("evidence_level") if main else None,
        "catalysts": accepted,
    }


def _stage(item: dict[str, Any]) -> str:
    category = str(item.get("category") or "")
    if category == "earnings": return "REALIZED"
    if category in {"order", "contract", "customer", "capacity"}: return "VALIDATING"
    return "EXPECTATION"


def _parse_datetime(value: Any) -> datetime | None:
    if not value: return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(SHANGHAI_TZ) if parsed.tzinfo else parsed.replace(tzinfo=SHANGHAI_TZ)
    except ValueError:
        return None


def _with_suffix(value: Any) -> str | None:
    code = str(value or "").split(".", 1)[0]
    if len(code) != 6: return None
    return f"{code}.{'SH' if code.startswith(('5', '6')) else 'BJ' if code.startswith(('4', '8', '9')) else 'SZ'}"


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
