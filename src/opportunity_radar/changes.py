"""Fixed descriptive calculations; no opportunity score or causal inference."""
from __future__ import annotations

import statistics
from collections import defaultdict

from src.opportunity_radar.contracts import number, visible


def pct(current, previous):
    return None if current is None or previous in (None, 0) else (current / previous - 1) * 100


def slope(values, window):
    if len(values) < window:
        return None
    ys = values[-window:]
    center = (window - 1) / 2
    return sum((i - center) * value for i, value in enumerate(ys)) / sum((i - center) ** 2 for i in range(window))


def series_changes(values):
    values = [number(v) for v in values]
    if not values or any(v is None for v in values):
        return {}
    current = values[-1]
    out = {"level": current, "delta": current - values[-2] if len(values) > 1 else None,
           "observation_count": len(values), "window_basis": "SOURCE_OBSERVATIONS_NOT_CALENDAR_DAYS"}
    for window in (1, 3, 5, 7, 10, 20, 30):
        out[f"change_{window}d"] = pct(current, values[-window-1]) if len(values) > window else None
    for window in (20, 60, 250):
        out[f"percentile_{window}d"] = 100 * sum(v <= current for v in values[-window:]) / window if len(values) >= window else None
    for window in (20, 60):
        out[f"new_high_{window}d"] = current > max(values[-window-1:-1]) if len(values) > window else None
    out["new_low_20d"] = current < min(values[-21:-1]) if len(values) > 20 else None
    for window in (3, 10, 20):
        out[f"slope_{window}d"] = slope(values, window)
    a, b = out["slope_3d"], out["slope_20d"]
    out["acceleration_3d_vs_20d"] = a-b if a is not None and b is not None else None
    returns = [pct(b, a) for a, b in zip(values[-21:-1], values[-20:])] if len(values) >= 21 else []
    out["historical_volatility"] = statistics.stdev(returns) if returns and all(v is not None for v in returns) else None
    deviation = statistics.stdev(values[-20:]) if len(values) >= 20 else None
    out["zscore_20"] = (current-statistics.mean(values[-20:]))/deviation if deviation else None
    out["change_label"] = "PRICE_INFLECTION_CANDIDATE" if a is not None and b is not None and a*b < 0 else None
    return out


def latest_changes(rows, cutoff):
    groups = defaultdict(list)
    for row in rows:
        if visible(row, cutoff):
            key = tuple(row.get(k) for k in ("signal_type", "entity", "metric", "source", "unit", "currency"))
            if row["value"] is None:
                key += (row["observation_id"],)
            groups[key].append(row)
    result = []
    for group in groups.values():
        # Retain the version visible at this cutoff, never a later revision.
        versions = {}
        for row in sorted(group, key=lambda r: (r["first_seen_at"], r["observation_id"])):
            versions[row["source_date"]] = row
        ordered = sorted(versions.values(), key=lambda r: r["source_date"])
        latest = dict(ordered[-1])
        latest["as_of_valid"] = True
        numeric = [r["value"] for r in ordered]
        latest["changes"] = series_changes(numeric) if all(v is not None for v in numeric) else {}
        latest["facts"] = dict(latest["facts"])
        if latest["signal_type"] == "COMMODITY_PRICE":
            latest["facts"].update({k: v for k, v in latest["changes"].items() if k in latest["facts"]})
            latest["facts"]["latest_value"] = latest["value"]
        if numeric and all(v is not None for v in numeric):
            previous = numeric[-2] if len(numeric) > 1 else None
            current = numeric[-1]
            computed = {"current": current, "previous": previous, "current_value": current,
                        "previous_value": previous, "delta": current-previous if previous is not None else None,
                        "change_abs": current-previous if previous is not None else None,
                        "change_pct": pct(current, previous), "percentile": latest["changes"].get("percentile_20d"),
                        "historical_percentile": latest["changes"].get("percentile_20d"),
                        "zscore": latest["changes"].get("zscore_20"), "trend_5d": slope(numeric, 5),
                        "trend_20d": slope(numeric, 20)}
            latest["facts"].update({k: v for k, v in computed.items() if k in latest["facts"]})
            metric = latest.get("metric")
            if metric in latest["facts"]:
                latest["facts"][metric] = current
            basis = latest["facts"].get("period_basis")
            if latest["signal_type"] == "REVENUE_PROFIT_MARGIN" and len(numeric) >= 3 and basis and all(r["facts"].get("period_basis") == basis for r in ordered[-3:]):
                field = {"revenue_yoy": "revenue_acceleration", "profit_yoy": "profit_acceleration"}.get(metric)
                if field:
                    latest["facts"][field] = numeric[-1]-2*numeric[-2]+numeric[-3]
        if latest["signal_type"] == "VALUATION_FUNDAMENTAL_DIVERGENCE":
            latest["facts"]["divergence_candidate"] = divergence(number(latest["facts"].get("fundamental_delta")), number(latest["facts"].get("return_5d")))
        latest["history_references"] = [r["observation_id"] for r in ordered]
        result.append(latest)
    return sorted(result, key=lambda r: r["observation_id"])


def transition(previous, current):
    if previous["signal_type"] != current["signal_type"] or previous["entity"] != current["entity"]:
        raise ValueError("TRANSITION_ENTITY_MISMATCH")
    if previous["source_date"] >= current["source_date"]:
        raise ValueError("TRANSITION_TIME_ORDER")
    a, b = previous["facts"].get("current_stage"), current["facts"].get("current_stage")
    return {"previous_stage": a, "current_stage": b, "transition_date": current["source_date"],
            "state_transition": a != b if a and b else None,
            "evidence": [previous["observation_id"], current["observation_id"]]}


def fundamental_changes(current, previous, older):
    out = {}
    for metric in ("revenue_yoy", "profit_yoy", "gross_margin", "cash_flow"):
        a, b, c = (number(row.get(metric)) for row in (current, previous, older))
        out[metric + "_delta"] = a-b if a is not None and b is not None else None
        out[metric + "_acceleration"] = a-2*b+c if all(v is not None for v in (a, b, c)) else None
    return out


def divergence(fundamental_delta, return_5d):
    if fundamental_delta is None or return_5d is None:
        return None
    if fundamental_delta > 0 and abs(return_5d) <= 1:
        return "FUNDAMENTAL_UP_PRICE_FLAT"
    if fundamental_delta > 0 and return_5d < -1:
        return "FUNDAMENTAL_UP_PRICE_DOWN"
    if fundamental_delta < 0 and return_5d > 1:
        return "FUNDAMENTAL_DOWN_PRICE_UP"
    return None
