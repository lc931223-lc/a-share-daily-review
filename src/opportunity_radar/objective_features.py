"""Audited existing-FactStore price windows. Missing valuation stays missing."""
import hashlib
import json
import math
from datetime import datetime

import pandas as pd

from src.market_packet.trading_calendar import load_trading_calendar
from src.opportunity_radar.contracts import SHANGHAI, number, stamp, visible, evidence_eligible
from src.opportunity_radar.storage import ObservationStore, archive_json

FEATURES = "stock_return_1d stock_return_5d stock_return_20d stock_return_60d sector_return_20d relative_return_20d earnings_revision_20d revenue_revision_20d margin_revision valuation_change_20d pe_ttm pe_forward pb ps valuation_percentile fundamental_change_score price_reaction_score".split()


def price_features(rows, expected_days):
    output = {k: None for k in FEATURES}
    output.update(amount=None, turnover_rate=None, price_source_date=None,
                  price_basis="COMPOUNDED_EXCHANGE_PCT_CHG_NOT_TOTAL_RETURN", missing_windows=[])
    by_day = {}
    conflicts = set()
    for row in rows:
        day = str(row["trade_date"])[:10]
        if day not in expected_days:
            continue
        value = number(row.get("pct_chg"))
        if day in by_day and by_day[day] != value:
            conflicts.add(day)
        by_day[day] = value
    for window in (1, 5, 20, 60):
        days = expected_days[-window:]
        if len(days) != window or any(d in conflicts or by_day.get(d) is None or by_day[d] <= -100 for d in days):
            output["missing_windows"].append(window)
            continue
        output[f"stock_return_{window}d"] = 100*(math.prod(1+by_day[d]/100 for d in days)-1)
    current = next((r for r in reversed(rows) if str(r["trade_date"])[:10] == expected_days[-1]), None) if expected_days else None
    if current and expected_days[-1] not in conflicts:
        output.update(price_source_date=expected_days[-1], amount=number(current.get("amount")),
                      turnover_rate=number(current.get("turnover_rate")))
    output["conflicting_days"] = sorted(conflicts)
    return output


def divergence_label(fundamental_pct, return20, valuation_percentile=None):
    if fundamental_pct is None or return20 is None:
        return None
    if valuation_percentile is not None and valuation_percentile >= 90 and return20 >= 20:
        return "HIGH_EXPECTATION_RISK"
    if fundamental_pct > 5:
        return "FUNDAMENTALS_UP_PRICE_LAGGING" if return20 <= 5 else "FUNDAMENTALS_UP_PRICE_CONFIRMED"
    if fundamental_pct < -5 and return20 >= -5:
        return "FUNDAMENTALS_DOWN_PRICE_NOT_PRICED"
    if abs(fundamental_pct) <= 5 and return20 >= 20:
        return "FUNDAMENTALS_FLAT_PRICE_OVERHEATED"
    return None


def collect_price_evidence(root, day, snapshot):
    """An archive captured today is admissible today only, even for old OHLCV."""
    from src.opportunity_radar.enrichment import observation
    now = datetime.now(SHANGHAI)
    calendar = load_trading_calendar(day, cache_root=root / "data/reference")
    dates = sorted(r.cal_date.isoformat() for r in calendar if r.is_open and (r.cal_date < day if snapshot == "MORNING" else r.cal_date <= day))[-60:]
    if not dates:
        return [], {"source": "FACTSTORE_PRICE_WINDOWS", "status": "UNAVAILABLE", "reason": "CALENDAR_UNAVAILABLE"}
    # Reuse the existing daily repository, including its source credentials/cache.
    # Never fill a missing day with an earlier partition or compress suspended days.
    from src.inflection.history import DailyHistoryRepository
    from datetime import date
    history_health = DailyHistoryRepository(root).ensure_range(date.fromisoformat(dates[0]), date.fromisoformat(dates[-1]))
    history = [r for r in ObservationStore(root).all() if visible(r, now) and evidence_eligible(r)]
    relevant = [r for r in history if r.get("stock_code") and r["signal_type"] in {"TECHNOLOGY_BREAKTHROUGH", "REVENUE_PROFIT_MARGIN", "EXPECTATION_REVISION", "CUSTOMER_AND_ORDER"}]
    codes = {r["stock_code"][:6] for r in relevant if r["stock_code"][:6].isdigit()}
    prices, dependencies = [], []
    columns = ["trade_date", "ts_code", "pct_chg", "amount", "turnover_rate"]
    for source_day in dates:
        paths = sorted((root / "data/facts/dataset=stock_daily_ohlcv" / f"trade_date={source_day}").glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not paths:
            continue
        path = paths[0]
        frame = pd.read_parquet(path, columns=columns)
        frame = frame[frame.ts_code.str[:6].isin(codes)]
        prices.extend(json.loads(frame.to_json(orient="records")))
        dependencies.append({"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    seen = datetime.now(SHANGHAI).isoformat()
    archive = archive_json(root, "price_windows", {"retrieved_at": seen, "source_date": dates[-1],
        "first_seen_policy": "CAPTURED_NOW_NO_HISTORICAL_FIRST_SEEN_ASSUMPTION", "dependencies": dependencies, "rows": prices})
    base = {"source": "EXISTING_FACTSTORE_DAILY", "source_tier": 2, "source_path": archive.relative_to(root).as_posix(),
        "url": None, "first_seen_at": seen, "provenance": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "kind": "DERIVED_FROM_EXISTING_FACTSTORE_CAPTURED_NOW"}}
    output = []
    for code in sorted(codes):
        own = [r for r in relevant if r["stock_code"][:6] == code]
        facts = price_features([r for r in prices if r["ts_code"][:6] == code], dates)
        fundamentals = [r for r in own if r["facts"].get("fundamental_change_pct") is not None
                        and (day-stamp(r["published_at"]).date()).days <= 180]
        fundamental = max(fundamentals, key=lambda r: (r["published_at"], r["metric"] == "reported_earnings"), default=None)
        delta = fundamental["facts"]["fundamental_change_pct"] if fundamental else None
        facts.update(fundamental_delta=delta, fundamental_change_basis="REPORTED_YOY_NOT_EXPECTATION",
                     fundamental_observation_id=fundamental["observation_id"] if fundamental else None)
        recent = [r for r in own if r["signal_type"] == "EXPECTATION_REVISION" and dates[-20] <= r["source_date"] <= dates[-1]] if len(dates) >= 20 else []
        for metric, field in (("earnings_revision", "earnings_revision_20d"), ("revenue_revision", "revenue_revision_20d"), ("gross_margin_revision", "margin_revision")):
            matching = [r for r in recent if r["facts"].get("expectation_metric") == metric]
            if matching:
                facts[field] = max(matching, key=lambda r: r["published_at"])["facts"]["revision_pct"]
        ret = facts["stock_return_20d"]
        facts.update(fundamental_change_score=max(0, min(100, 50+delta/2)) if delta is not None else None,
                     price_reaction_score=max(0, min(100, 50+ret)) if ret is not None else None,
                     divergence_candidate=divergence_label(delta, ret),
                     observation_mode="DERIVED_CURRENT_AS_OF", historical_backfill=False,
                     evidence_scope="DESCRIPTIVE_FUNDAMENTALS_PRICE_COMPARISON_NOT_UNDERVALUATION")
        facts["missing_data"] = [f for f in FEATURES if facts.get(f) is None]
        if facts["price_source_date"] is None:
            continue
        item = max(own, key=lambda r: r["published_at"])
        output.append(observation(base, "VALUATION_FUNDAMENTAL_DIVERGENCE", code, "fundamental_price_features", None, seen,
            facts, source_date=dates[-1], event_date=dates[-1], stock_code=code, stock_name=item.get("stock_name"), theme=item.get("theme"),
            body_evidence="Existing FactStore exchange percentage changes; underlying rows and partition hashes are in source_path."))
    return output, {"source": "FACTSTORE_PRICE_WINDOWS", "status": "PARTIAL" if output else "UNAVAILABLE", "rows": len(output),
                    "source_date": dates[-1], "history_health": history_health,
                    "reason": "PE_FORWARD_AND_VALUATION_VINTAGES_UNAVAILABLE_NO_SECOND_QUOTE_DATABASE"}
