from __future__ import annotations

import statistics
from typing import Any

from src.auction.analysis import anomaly_labels


def build_daily_summary(
    checkpoint_rows: list[dict[str, Any]],
    *,
    previous_close: float | None,
    previous_day_amount: float | None,
    historical_auction_amounts: list[float],
    previous_day_volume: float | None = None,
    process_rows: list[dict[str, Any]] | None = None,
    historical_auction_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = {
        str(row.get("checkpoint_time")): row
        for row in checkpoint_rows
        if row.get("match_price") is not None
    }
    final = rows.get("09:25:00")
    auction_price = _number(final, "match_price")
    auction_volume = _number(final, "matched_volume")
    auction_amount = _number(final, "matched_amount")
    history = [
        float(value)
        for value in historical_auction_amounts
        if value is not None and float(value) > 0
    ]
    count = len(history)

    ratio_5d = _ratio(auction_amount, statistics.fmean(history[-5:])) if count >= 5 else None
    ratio_20d = _ratio(auction_amount, statistics.fmean(history[-20:])) if count >= 20 else None
    percentile_60d = (
        _percent_rank(auction_amount, history[-60:])
        if count >= 45 and auction_amount is not None
        else None
    )
    auction_to_previous = _ratio(auction_amount, previous_day_amount)
    post_0920 = _ratio(auction_amount, _amount(rows.get("09:20:00")))
    last_2min = _ratio(auction_amount, _amount(rows.get("09:23:00")))
    amount_0924 = _amount(rows.get("09:24:00"))
    last_1min = (
        ((auction_amount - amount_0924) / amount_0924)
        if auction_amount is not None and amount_0924
        else None
    )
    price_0920 = _number(rows.get("09:20:00"), "match_price")
    price_0915 = _number(rows.get("09:15:00"), "match_price")
    price_0924 = _number(rows.get("09:24:00"), "match_price")
    process = sorted(process_rows or [], key=lambda row: str(row.get("source_data_time") or ""))
    post_process = [row for row in process if "09:20:00" <= _time_text(row) <= "09:25:00"]
    unmatched = [
        float(row["unmatched_volume"])
        for row in post_process
        if row.get("unmatched_volume") is not None
    ]
    process_prices = [
        float(row["match_price"]) for row in post_process if row.get("match_price") is not None
    ]
    order_growth = _window_growth(process, "unmatched_volume", "09:20:00", "09:25:00")
    last_3m_order_growth = _window_growth(process, "unmatched_volume", "09:22:00", "09:25:00")
    last_1m_order_growth = _window_growth(process, "unmatched_volume", "09:24:00", "09:25:00")
    last_30s_order_growth = _window_growth(process, "unmatched_volume", "09:24:30", "09:25:00")
    records = historical_auction_records or [
        {"auction_amount": value} for value in historical_auction_amounts
    ]
    history_metrics = _historical_metrics(auction_amount, auction_volume, records)

    components = {
        "ratio_20d": _score_ratio_20d(ratio_20d),
        "percentile_60d": _score_percentile(percentile_60d),
        "previous_day_share": _score_previous_share(auction_to_previous),
        "post_0920_growth": _score_post_growth(post_0920),
        "late_growth": _score_late_growth(last_1min, last_2min),
        "price_confirmation": _score_price_confirmation(price_0920, auction_price),
    }
    available = [value for value in components.values() if value is not None]
    score = int(sum(available))
    coverage = len(available) / len(components)
    gap_pct = (
        ((auction_price / previous_close) - 1) * 100
        if auction_price is not None and previous_close
        else None
    )
    quality = "PASS" if coverage == 1.0 and count >= 60 else "PARTIAL"
    result = {
        "trade_date": final.get("trade_date")
        if final
        else (checkpoint_rows[0].get("trade_date") if checkpoint_rows else None),
        "ts_code": final.get("ts_code")
        if final
        else (checkpoint_rows[0].get("ts_code") if checkpoint_rows else None),
        "stock_name": final.get("stock_name")
        if final
        else (checkpoint_rows[0].get("stock_name") if checkpoint_rows else None),
        "prev_close": previous_close,
        "auction_price": auction_price,
        "auction_gap_pct": gap_pct,
        "price_0915": price_0915,
        "price_0920": price_0920,
        "price_0924": price_0924,
        "price_0925": auction_price,
        "price_change_0915_0920_pct": _change_pct(price_0920, price_0915),
        "price_change_0920_0925_pct": _change_pct(auction_price, price_0920),
        "post_0920_price_stability": _stability(process_prices),
        "auction_vol": auction_volume,
        "auction_amount": auction_amount,
        "auction_vwap": auction_price,
        "prev_day_amount": previous_day_amount,
        "auction_to_prev_day_amount": auction_to_previous,
        "auction_volume_to_prev_day_volume": _ratio(auction_volume, previous_day_volume),
        "avg_auction_amount_5d": statistics.fmean(history[-5:]) if count >= 5 else None,
        "avg_auction_amount_20d": statistics.fmean(history[-20:]) if count >= 20 else None,
        "avg_auction_amount_60d": statistics.fmean(history[-60:]) if count >= 60 else None,
        "auction_amount_ratio_5d": ratio_5d,
        "auction_amount_ratio_20d": ratio_20d,
        "auction_amount_percentile_60d": percentile_60d,
        "post_0920_amount_growth": post_0920,
        "last_2min_amount_growth": last_2min,
        "last_1min_amount_growth": last_1min,
        "pre_920_cancel_ratio": None,
        "pre_920_cancel_ratio_status": "N/A_SOURCE_CANNOT_SEPARATE_CANCELLATION",
        "post_0920_order_growth": order_growth,
        "post_0920_order_decay": max(0.0, -order_growth) if order_growth is not None else None,
        "last_3m_order_growth": last_3m_order_growth,
        "last_1min_order_growth": last_1m_order_growth,
        "last_30s_order_growth": last_30s_order_growth,
        "unmatched_direction": "unavailable",
        "unmatched_stability": _stability(unmatched),
        **history_metrics,
        "baseline_observation_count_5d": min(count, 5),
        "baseline_observation_count_20d": min(count, 20),
        "baseline_observation_count_60d": min(count, 60),
        "baseline_quality_status": "PASS"
        if count >= 60
        else ("PARTIAL" if count else "UNAVAILABLE"),
        "similar_history_sample_size": len(records),
        "similar_history_outcome_count": sum(
            row.get("post_open_30m_return") is not None for row in records
        ),
        "similar_history_positive_rate": _positive_rate(records),
        "auction_volume_anomaly_score": score,
        "score_components": components,
        "score_component_coverage": coverage,
        "quality_status": quality,
        "open_price_validation_source": None,
        "open_price_error_pct": None,
        "conflict_status": "not_validated",
        "schema_version": "auction_daily_summary.1",
    }
    result["anomaly_labels"] = anomaly_labels(result)
    return result


def _historical_metrics(amount, volume, records):
    result = {}
    for horizon in (5, 10, 20):
        sample = records[-horizon:]
        amounts = [
            float(row["auction_amount"]) for row in sample if row.get("auction_amount") is not None
        ]
        volumes = [
            float(row["auction_vol"]) for row in sample if row.get("auction_vol") is not None
        ]
        result[f"auction_amount_percentile_{horizon}d"] = (
            _percent_rank(amount, amounts)
            if amount is not None and len(amounts) >= horizon
            else None
        )
        result[f"auction_amount_zscore_{horizon}d"] = (
            _zscore(amount, amounts) if amount is not None and len(amounts) >= horizon else None
        )
        result[f"auction_volume_percentile_{horizon}d"] = (
            _percent_rank(volume, volumes)
            if volume is not None and len(volumes) >= horizon
            else None
        )
        result[f"auction_volume_zscore_{horizon}d"] = (
            _zscore(volume, volumes) if volume is not None and len(volumes) >= horizon else None
        )
    return result


def _window_growth(rows, field, start, end):
    eligible = [
        row for row in rows if start <= _time_text(row) <= end and row.get(field) is not None
    ]
    if len(eligible) < 2:
        return None
    first, last = float(eligible[0][field]), float(eligible[-1][field])
    return last / first - 1 if first else None


def _time_text(row):
    value = str(row.get("source_data_time") or row.get("snapshot_time") or "")
    return value[11:19] if len(value) >= 19 else value[-8:]


def _change_pct(current, previous):
    return (current / previous - 1) * 100 if current is not None and previous else None


def _stability(values):
    if len(values) < 2:
        return None
    average = statistics.fmean(values)
    if average == 0:
        return None
    return max(0.0, min(1.0, 1 - statistics.pstdev(values) / abs(average)))


def _zscore(value, history):
    if len(history) < 2:
        return None
    deviation = statistics.pstdev(history)
    return (value - statistics.fmean(history)) / deviation if deviation else 0.0


def _positive_rate(records):
    values = [
        float(row["post_open_30m_return"])
        for row in records
        if row.get("post_open_30m_return") is not None
    ]
    return sum(value > 0 for value in values) / len(values) if values else None


def _number(row: dict[str, Any] | None, key: str) -> float | None:
    if not row or row.get(key) is None:
        return None
    return float(row[key])


def _amount(row: dict[str, Any] | None) -> float | None:
    return _number(row, "matched_amount")


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _percent_rank(value: float, history: list[float]) -> float:
    return round(sum(item <= value for item in history) / len(history) * 100, 6)


def _score_ratio_20d(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 1:
        return 0
    if value < 1.5:
        return 1
    if value < 2:
        return 2
    if value < 3:
        return 3
    if value < 5:
        return 4
    return 5


def _score_percentile(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 50:
        return 0
    if value < 70:
        return 1
    if value < 85:
        return 2
    if value < 95:
        return 3
    return 4


def _score_previous_share(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 0.002:
        return 0
    if value < 0.005:
        return 1
    if value < 0.01:
        return 2
    return 3


def _score_post_growth(value: float | None) -> int | None:
    if value is None:
        return None
    if value <= 1:
        return 0
    if value < 1.25:
        return 1
    if value < 1.75:
        return 2
    return 3


def _score_late_growth(last_1min: float | None, last_2min: float | None) -> int | None:
    if last_1min is None and last_2min is None:
        return None
    value = max(last_1min or 0, (last_2min - 1) if last_2min is not None else 0)
    if value < 0.1:
        return 0
    if value < 0.25:
        return 1
    if value < 0.5:
        return 2
    return 3


def _score_price_confirmation(start: float | None, final: float | None) -> int | None:
    if start is None or final is None:
        return None
    change = final / start - 1
    if change < -0.002:
        return 0
    if change <= 0.002:
        return 1
    return 2
