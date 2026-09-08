"""Whitelisted structured conditions; prose is never guessed."""

import math
import operator

METRICS = {
    "auction_gap_pct": "auction_gap_pct",
    "auction_amount_percentile": "auction_amount_percentile_20d",
    "post_0920_price_change": "price_change_0920_0925_pct",
    "post_0920_order_growth": "post_0920_order_growth",
    "sector_positive_ratio": "positive_gap_ratio",
    "leader_strength": "leader_strength",
    "capacity_strength": "capacity_strength",
    "relative_strength": "auction_gap_pct",
    "holds_auction_price": "holds_auction_price",
    "holds_previous_close": "holds_previous_close",
}
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}


def evaluate(check, entity, comparison=None, *, window="auction"):
    metric = check.get("metric")
    if metric not in METRICS or check.get("operator") not in OPS or "threshold" not in check:
        return "unverified", "UNSUPPORTED_CONDITION"
    if check.get("evidence_level") == "D":
        return "unverified", "TIER_D_NOT_HARD_EVIDENCE"
    if check.get("time_window", "auction") != window:
        return "unverified", "PENDING_TIME_WINDOW"
    if metric.startswith("holds_") and window != "post_open":
        return "unverified", "PENDING_TIME_WINDOW"
    value = (entity or {}).get(METRICS[metric])
    if metric == "relative_strength":
        other = (comparison or {}).get("auction_gap_pct")
        value = value - other if value is not None and other is not None else None
    if value is None:
        return "unverified", "MISSING_METRIC"
    if metric == "post_0920_order_growth" and not (entity or {}).get("source_contract_reference"):
        return "unverified", "ORDER_DIRECTION_UNAVAILABLE"
    try:
        if not math.isfinite(float(value)) or not math.isfinite(float(check["threshold"])):
            return "unverified", "INVALID_METRIC"
        passed = OPS[check["operator"]](float(value), float(check["threshold"]))
    except (ValueError, TypeError):
        return "unverified", "INVALID_METRIC"
    return (
        "confirmed" if passed else "invalidated"
    ), f"{metric}={value} {check['operator']} {check['threshold']}"
