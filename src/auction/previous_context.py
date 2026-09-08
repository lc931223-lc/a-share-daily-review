from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.market_packet.trading_calendar import TradingCalendarDay


def load_previous_context(
    root: Path,
    target: date,
    calendar_days: list[TradingCalendarDay],
) -> dict[str, Any]:
    previous_days = sorted(
        item.cal_date for item in calendar_days if item.is_open and item.cal_date < target
    )
    if not previous_days:
        raise RuntimeError(f"No previous A-share trading day before {target.isoformat()}")
    previous = previous_days[-1]
    official_path = root / "data" / "official_reviews" / f"{previous.isoformat()}.json"
    legacy_path = root / "data" / "json" / "reviews" / f"{previous.isoformat()}.json"
    if not official_path.is_file() and legacy_path.is_file():
        official_path = legacy_path
    context_path = root / "data" / "review_context" / f"{previous.isoformat()}.json"
    market_path = root / "data" / "market_packets" / f"{previous.isoformat()}.json"

    official = _read_exact(official_path, previous)
    review_context = _read_exact(context_path, previous)
    market_packet = _read_exact(market_path, previous)
    official_status = _official_review_status(official)
    official_loaded = official_status == "FORMAL"
    return {
        "previous_trade_date": previous.isoformat(),
        "status": "AVAILABLE" if official_loaded else "DEGRADED",
        "report_status": "normal" if official_loaded else "degraded",
        "official_review_loaded": official_loaded,
        "official_review_status": official_status,
        "review_context_loaded": bool(review_context),
        "market_packet_loaded": bool(market_packet),
        "source_paths": {
            "official_review": _relative(root, official_path) if official_loaded else None,
            "review_context": _relative(root, context_path) if review_context else None,
            "market_packet": _relative(root, market_path) if market_packet else None,
        },
        "missing": [
            name
            for name, present in (
                ("official_review", official_loaded),
                ("review_context", bool(review_context)),
                ("market_packet", bool(market_packet)),
            )
            if not present
        ],
        "market": _market_context(official, review_context),
        "mainlines": [_theme_context(row) for row in official.get("main_themes") or []],
        "stocks": [_stock_context(row) for row in official.get("stocks") or []],
        "tomorrow_checks": official.get("tomorrow_checks") or [],
        "risk_events": official.get("risk_events") or [],
        "official_evidence": [_evidence_context(row) for row in official.get("evidence") or []],
        "official_review": official,
        "review_context": review_context,
        "market_packet": market_packet,
    }


def _market_context(official: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    environment = context.get("market_environment") or {}
    return {
        "market_regime": official.get("market_regime"),
        "index_state": official.get("indices") or [],
        "turnover": official.get("turnover") or environment.get("total_turnover"),
        "breadth": {
            "advancers": official.get("advancers") or environment.get("rise_count"),
            "decliners": official.get("decliners") or environment.get("fall_count"),
        },
        "risk_level": (official.get("sentiment_dashboard") or {}).get("loss_feedback"),
    }


def _theme_context(row: dict[str, Any]) -> dict[str, Any]:
    scores = row.get("scores") or {}
    drivers = [_driver(item) for item in row.get("drivers") or []]
    return {
        "mainline_name": row.get("name"),
        "mainline_score": scores.get("total_score"),
        "lifecycle": row.get("stage"),
        "ranking": row.get("rank_no") or row.get("rank"),
        "factor_ids": [item.get("factor_id") for item in drivers],
        "factors": drivers,
        "evidence_level": _best_level(drivers),
        "catalyst": row.get("catalyst") or row.get("delta_reason"),
        "industrial_evidence": row.get("industrial_evidence"),
        "capital_evidence": row.get("capital_evidence"),
        "risks": row.get("risks") or [],
    }


def _stock_context(row: dict[str, Any]) -> dict[str, Any]:
    drivers = [_driver(item) for item in row.get("drivers") or []]
    return {
        "ts_code": _with_suffix(row.get("code") or row.get("stock_code")),
        "stock_name": row.get("name") or row.get("stock_name"),
        "theme": row.get("theme"),
        "role": row.get("role"),
        "role_detail": row.get("role_detail"),
        "position_status": row.get("stage") or row.get("status"),
        "factor_ids": [item.get("factor_id") for item in drivers],
        "factors": drivers,
        "catalyst": row.get("catalyst"),
        "evidence_level": _best_level(drivers),
        "scores": row.get("scores") or {},
        "yesterday_signals": {
            key: row.get(key)
            for key in (
                "limit_up",
                "failed_limit_up",
                "intraday_pullback",
                "late_pullback",
                "big_bearish",
                "volume_state",
            )
            if row.get(key) is not None
        },
    }


def _driver(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "factor_id": row.get("code"),
        "name": row.get("name"),
        "evidence_level": row.get("evidence_level"),
    }


def _evidence_context(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": row.get("source"),
        "source_type": row.get("source_type"),
        "published_at": row.get("published_at"),
        "evidence_level": row.get("evidence_level"),
        "url": row.get("url") or row.get("reference"),
        "reference": row.get("reference") or row.get("url"),
        "verified": row.get("verified"),
        "title": row.get("title"),
    }


def _best_level(rows: list[dict[str, Any]]) -> str | None:
    levels = [str(row.get("evidence_level")) for row in rows if row.get("evidence_level")]
    return min(levels, key=lambda level: "ABCD".find(level)) if levels else None


def _read_exact(path: Path, expected: date) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = str(payload.get("date") or (payload.get("meta") or {}).get("trade_date") or "")[:10]
    if actual != expected.isoformat():
        raise ValueError(
            f"previous input date mismatch: expected={expected.isoformat()} actual={actual}"
        )
    return payload


def _official_review_status(payload: dict[str, Any]) -> str:
    if not payload:
        return "MISSING"
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    if any(marker in serialized for marker in ("模拟", "fixture", "sample data", "synthetic")):
        return "SIMULATED_REJECTED"
    data_kind = str((payload.get("meta") or {}).get("data_kind") or payload.get("data_kind") or "")
    if data_kind and data_kind.lower() not in {"real", "official"}:
        return "NON_FORMAL_REJECTED"
    return "FORMAL"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _with_suffix(value: Any) -> str | None:
    raw = str(value or "").upper()
    if "." in raw:
        return raw.replace(".SS", ".SH")
    code = raw.zfill(6)
    if len(code) != 6 or not code.isdigit():
        return None
    suffix = "SH" if code.startswith(("5", "6")) else "BJ" if code.startswith(("8", "9")) else "SZ"
    return f"{code}.{suffix}"
