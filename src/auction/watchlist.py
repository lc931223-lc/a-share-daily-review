from __future__ import annotations

from collections import Counter
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable

from src.market_packet.trading_calendar import TradingCalendarDay, load_trading_calendar


def normalize_ts_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if "." in text:
        code, exchange = text.split(".", 1)
        exchange = "SH" if exchange in {"SH", "SS"} else exchange
        return f"{code.zfill(6)}.{exchange}" if exchange in {"SH", "SZ", "BJ"} else None
    code = text[-6:].zfill(6)
    if code.startswith(("6", "5")):
        exchange = "SH"
    elif code.startswith(("8", "9")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"{code}.{exchange}"


def compose_watchlist(
    *,
    target_date: date,
    previous_trade_date: date,
    review: dict[str, Any],
    packet: dict[str, Any],
    historical_codes: Iterable[str] = (),
    min_size: int = 100,
    max_size: int = 200,
) -> dict[str, Any]:
    candidates: dict[str, dict[str, Any]] = {}

    def add(code: Any, *, name: Any = None, theme: Any = None, role: Any = None, reason: str, priority: int) -> None:
        ts_code = normalize_ts_code(code)
        if ts_code is None:
            return
        item = candidates.setdefault(ts_code, {
            "ts_code": ts_code,
            "stock_name": str(name or ""),
            "themes": [],
            "roles": [],
            "reasons": [],
            "priority": priority,
        })
        if name and not item["stock_name"]:
            item["stock_name"] = str(name)
        if theme and str(theme) not in item["themes"]:
            item["themes"].append(str(theme))
        if role and str(role) not in item["roles"]:
            item["roles"].append(str(role))
        if reason not in item["reasons"]:
            item["reasons"].append(reason)
        item["priority"] = min(item["priority"], priority)

    review_stocks = review.get("stocks") or []
    for stock in review_stocks:
        add(
            stock.get("code") or stock.get("stock_code"),
            name=stock.get("name") or stock.get("stock_name"),
            theme=stock.get("theme"), role=stock.get("role"),
            reason="official_review_stock", priority=10,
        )

    theme_names = {str(item.get("name")) for item in review.get("main_themes") or [] if item.get("name")}
    packet_stocks = packet.get("stocks") or []
    stock_by_code = {normalize_ts_code(item.get("stock_code") or item.get("code")): item for item in packet_stocks}
    stock_by_name = {str(item.get("stock_name") or item.get("name")): item for item in packet_stocks}
    for check in review.get("tomorrow_checks") or []:
        key = check.get("entity_key")
        matched = stock_by_code.get(normalize_ts_code(key)) or stock_by_name.get(str(key))
        if matched:
            add(matched.get("stock_code"), name=matched.get("stock_name"), reason="tomorrow_check", priority=15)
        elif str(check.get("entity_type") or "").lower() == "stock":
            add(key, reason="tomorrow_check", priority=15)

    for stock in packet_stocks:
        code = stock.get("stock_code") or stock.get("code")
        name = stock.get("stock_name") or stock.get("name")
        themes = stock.get("themes") or []
        for theme in themes:
            if str(theme) in theme_names:
                add(code, name=name, theme=theme, reason="theme_member", priority=20)
        if stock.get("limit_up"):
            add(code, name=name, reason="previous_limit_up", priority=25)
        if (stock.get("continuous_board_count") or stock.get("board_count") or 0) >= 2:
            add(code, name=name, reason="previous_continuous_board", priority=22)

    for stock in packet.get("leader_candidates") or []:
        add(
            stock.get("stock_code"), name=stock.get("stock_name"),
            role="objective_candidate", reason="objective_role_candidate", priority=30,
        )

    announcements = packet.get("announcements") or {}
    for item in announcements.get("risk_announcements") or []:
        add(item.get("stock_code"), name=item.get("stock_name"), reason="risk_announcement", priority=18)

    for code in historical_codes:
        add(code, reason="historical_tracking", priority=35)

    amount_ranked = sorted(
        packet_stocks,
        key=lambda item: float(item.get("amount") or 0),
        reverse=True,
    )
    for stock in amount_ranked[:60]:
        themes = stock.get("themes") or [None]
        for theme in themes:
            add(stock.get("stock_code"), name=stock.get("stock_name"), theme=theme, reason="top_amount", priority=40)
    if len(candidates) < min_size:
        for stock in amount_ranked:
            themes = stock.get("themes") or [None]
            for theme in themes:
                add(stock.get("stock_code"), name=stock.get("stock_name"), theme=theme, reason="objective_pool_fill", priority=50)
            if len(candidates) >= min_size:
                break

    ordered = sorted(candidates.values(), key=lambda item: (item["priority"], item["ts_code"]))[:max_size]
    reason_counts = Counter(reason for item in ordered for reason in item["reasons"])
    quality = "PASS" if min_size <= len(ordered) <= max_size else "PARTIAL"
    return {
        "schema_version": "auction_watchlist.1",
        "trade_date": target_date.isoformat(),
        "previous_trade_date": previous_trade_date.isoformat(),
        "stock_count": len(ordered),
        "min_size": min_size,
        "max_size": max_size,
        "quality_status": quality,
        "composition": dict(sorted(reason_counts.items())),
        "stocks": ordered,
    }


def build_watchlist_from_files(
    target_date: date,
    *,
    root: Path,
    calendar_days: list[TradingCalendarDay] | None = None,
    min_size: int = 100,
    max_size: int = 200,
) -> dict[str, Any]:
    days = calendar_days or load_trading_calendar(target_date, cache_root=root / "data" / "reference")
    previous = [item.cal_date for item in days if item.is_open and item.cal_date < target_date]
    if not previous:
        raise RuntimeError(f"No previous A-share trading day before {target_date.isoformat()}")
    previous_trade_date = max(previous)
    review_path = root / "data" / "official_reviews" / f"{previous_trade_date.isoformat()}.json"
    if not review_path.exists():
        review_path = root / "data" / "json" / "reviews" / f"{previous_trade_date.isoformat()}.json"
    packet_path = root / "data" / "market_packets" / f"{previous_trade_date.isoformat()}.json"
    review = _read_json(review_path, {})
    packet = _read_json(packet_path, {"stocks": []})
    tracking_path = root / "data" / "auction_watchlists" / "historical_tracking.json"
    tracking = _read_json(tracking_path, [])
    if isinstance(tracking, dict):
        tracking = tracking.get("stocks") or tracking.get("codes") or []
    tracking_codes = [item.get("ts_code") if isinstance(item, dict) else item for item in tracking]
    result = compose_watchlist(
        target_date=target_date, previous_trade_date=previous_trade_date,
        review=review, packet=packet, historical_codes=tracking_codes,
        min_size=min_size, max_size=max_size,
    )
    result["sources"] = {
        "official_review": review_path.relative_to(root).as_posix() if review_path.exists() else None,
        "market_packet": packet_path.relative_to(root).as_posix() if packet_path.exists() else None,
        "historical_tracking": tracking_path.relative_to(root).as_posix() if tracking_path.exists() else None,
    }
    output_dir = root / "data" / "auction_watchlists"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"auction_watchlist_{target_date.isoformat()}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["output_path"] = str(output_path)
    return result


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
