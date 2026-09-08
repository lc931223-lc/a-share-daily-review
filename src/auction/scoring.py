from __future__ import annotations

from typing import Any

COMPONENT_MAX = {
    "market_environment": 10,
    "mainline_match": 15,
    "catalyst_credibility": 15,
    "auction_strength": 25,
    "order_structure": 15,
    "stock_role": 10,
    "historical_pattern": 10,
}


def score_stock(
    summary: dict[str, Any],
    watch_stock: dict[str, Any],
    previous_context: dict[str, Any],
    sector: dict[str, Any] | None,
    refreshed_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    prior_stock = _prior_stock(previous_context, summary.get("ts_code"))
    prior_theme = _prior_theme(previous_context, (watch_stock.get("themes") or [None])[0])
    relevant_evidence = _relevant_evidence(refreshed_evidence, summary, watch_stock, prior_stock)
    components = {
        "market_environment": _market_component(sector),
        "mainline_match": _mainline_component(prior_theme, sector),
        "catalyst_credibility": _catalyst_component(prior_stock, prior_theme, relevant_evidence),
        "auction_strength": _auction_component(summary, sector),
        "order_structure": _order_component(summary),
        "stock_role": _role_component(prior_stock),
        "historical_pattern": _history_component(summary),
    }
    gross = round(sum(float(item["score"] or 0) for item in components.values()), 4)
    available = sum(item["available_max_score"] for item in components.values())
    risks = _risk_deductions(summary, prior_stock, prior_theme, sector, relevant_evidence)
    deduction = min(20, sum(item["deduction"] for item in risks))
    return {
        "gross_score": gross,
        "risk_deduction": deduction,
        "final_score": round(max(0, gross - deduction), 4),
        "score_available": f"{gross:g}/{available} available",
        "available_max_score": available,
        "missing_score_components": _missing_components(components),
        "components": components,
        "risks": risks,
        "evidence_validation": _evidence_validation(
            components["auction_strength"], prior_stock, prior_theme, relevant_evidence
        ),
        "candidate_only": True,
    }


def _component(score, maximum, reason, fields, confidence, *, available_maximum=None):
    return {
        "score": None if score is None else round(max(0, min(maximum, score)), 4),
        "max_score": maximum,
        "available_max_score": (
            0
            if score is None
            else maximum
            if available_maximum is None
            else available_maximum
        ),
        "reason": reason,
        "input_fields": fields,
        "confidence": confidence,
    }


def _market_component(sector):
    if not sector or sector.get("positive_gap_ratio") is None:
        return _component(None, 10, "market/sector auction breadth unavailable", [], "NONE")
    ratio = float(sector["positive_gap_ratio"])
    score = ratio * 7 + min(3, max(0, float(sector.get("post_0920_positive_ratio") or 0) * 3))
    return _component(
        score,
        10,
        "current sector breadth and post-09:20 participation",
        ["positive_gap_ratio", "post_0920_positive_ratio"],
        "MEDIUM",
    )


def _mainline_component(theme, sector):
    if not theme:
        return _component(
            None, 15, "stock is not linked to an exact previous-day formal mainline", [], "NONE"
        )
    prior_score = theme.get("mainline_score")
    breadth = sector.get("positive_gap_ratio") if sector else None
    values = []
    if prior_score is not None:
        values.append(min(5, max(0, float(prior_score) / 100 * 5)))
    if breadth is not None:
        values.append(float(breadth) * 10)
    if not values:
        return _component(
            None, 15, "previous mainline exists but comparable fields are unavailable", [], "LOW"
        )
    return _component(
        sum(values),
        15,
        "previous mainline score plus current sector auction breadth",
        ["mainline_score", "positive_gap_ratio"],
        "MEDIUM",
    )


def _catalyst_component(stock, theme, evidence):
    factors = (stock or {}).get("factors") or (theme or {}).get("factors") or []
    levels = [str(item.get("evidence_level")) for item in factors if item.get("evidence_level")]
    levels.extend(
        str(item.get("evidence_level")) for item in evidence if item.get("evidence_level")
    )
    if not levels:
        return _component(None, 15, "no inherited or refreshed catalyst evidence", [], "NONE")
    best = min(levels, key=lambda level: "ABCD".find(level) if level in "ABCD" else 99)
    score = {"A": 15, "B": 11, "C": 7, "D": 0}.get(best)
    return _component(
        score,
        15,
        f"best evidence level is {best}; D-level evidence receives no hard-validation score",
        ["factor_ids", "evidence_level", "verified"],
        "HIGH" if best == "A" else "MEDIUM" if best in {"B", "C"} else "LOW",
    )


def _auction_component(summary, sector):
    parts = {}
    gap = summary.get("auction_gap_pct")
    if gap is not None:
        value = float(gap)
        parts["price_performance"] = (
            max(0, 2 + value * 2 / 3)
            if value <= 0
            else 2 + value
            if value <= 3
            else max(0, 5 - (value - 3) * 0.75)
        )
    stability = summary.get("post_0920_price_stability")
    if stability is not None:
        parts["post_0920_stability"] = float(stability) * 8
    percentile = summary.get("auction_amount_percentile_20d") or summary.get(
        "auction_amount_percentile_60d"
    )
    if percentile is not None:
        parts["auction_volume"] = float(percentile) / 100 * 7
    if sector and sector.get("positive_gap_ratio") is not None:
        parts["sector_synchronization"] = float(sector["positive_gap_ratio"]) * 5
    available = {
        "price_performance": 5,
        "post_0920_stability": 8,
        "auction_volume": 7,
        "sector_synchronization": 5,
    }
    if not parts:
        return _component(None, 25, "auction strength inputs unavailable", [], "NONE")
    score = sum(parts.values())
    reason = "price is capped at 5 points; post-09:20 stability, self-history volume and sector synchronization dominate"
    result = _component(
        score,
        25,
        reason,
        list(parts),
        "HIGH" if sum(available[key] for key in parts) >= 20 else "MEDIUM",
        available_maximum=sum(available[key] for key in parts),
    )
    result["subcomponents"] = {
        key: {
            "score": round(parts[key], 4) if key in parts else None,
            "max_score": maximum,
            "status": "AVAILABLE" if key in parts else "N/A",
        }
        for key, maximum in available.items()
    }
    return result


def _order_component(summary):
    parts = {}
    direction = summary.get("unmatched_direction")
    if direction in {"buy", "sell"}:
        parts["post_0920_direction"] = 5 if direction == "buy" else 0
    stability = summary.get("unmatched_stability")
    if stability is not None:
        parts["post_0920_stability"] = float(stability) * 5
    last_minute = summary.get("last_1min_order_growth")
    if last_minute is not None and direction == "buy":
        parts["last_1min_strengthening"] = max(0, min(3, (float(last_minute) + 0.1) * 7.5))
    elif last_minute is not None and direction == "sell":
        parts["last_1min_strengthening"] = 0
    cancel = summary.get("pre_920_cancel_ratio")
    if cancel is not None:
        parts["abnormal_cancel_penalty"] = max(0, 2 * (1 - float(cancel)))
    if not parts:
        return _component(
            None,
            15,
            "source does not provide confirmed buy/sell split or usable order structure",
            [],
            "NONE",
        )
    maximums = {
        "post_0920_direction": 5,
        "post_0920_stability": 5,
        "last_1min_strengthening": 3,
        "abnormal_cancel_penalty": 2,
    }
    result = _component(
        sum(parts.values()),
        15,
        "only source-supported order fields are scored; unavailable direction and cancellation receive N/A",
        list(parts),
        "MEDIUM",
        available_maximum=sum(maximums[key] for key in parts),
    )
    result["subcomponents"] = {
        key: {
            "score": round(parts[key], 4) if key in parts else None,
            "max_score": maximum,
            "status": "AVAILABLE" if key in parts else "N/A",
        }
        for key, maximum in maximums.items()
    }
    return result


def _role_component(stock):
    if not stock or not stock.get("role"):
        return _component(None, 10, "exact previous-day formal stock role unavailable", [], "NONE")
    role = str(stock["role"]).lower()
    aliases = {
        "龙头": 10,
        "leader": 10,
        "中军": 9,
        "capacity": 9,
        "趋势核心": 8,
        "trend_core": 8,
        "情绪股": 7,
        "sentiment_core": 7,
        "补涨": 6,
        "catch_up": 6,
        "跟风": 2,
        "follower": 2,
    }
    score = aliases.get(role, 4)
    return _component(
        score,
        10,
        f"role inherited from exact previous-day official review: {stock['role']}",
        ["role", "role_detail", "position_status"],
        "HIGH",
    )


def _history_component(summary):
    sample = int(summary.get("similar_history_sample_size") or 0)
    outcome_coverage = int(summary.get("similar_history_outcome_count") or 0)
    if sample < 20 or outcome_coverage < 20:
        return _component(
            None,
            10,
            f"similar history with 09:30-10:00 outcomes is insufficient ({outcome_coverage}/{sample})",
            ["similar_history_sample_size", "similar_history_outcome_count"],
            "NONE",
        )
    win_rate = float(summary.get("similar_history_positive_rate") or 0)
    return _component(
        win_rate * 10,
        10,
        "positive rate of comparable historical auction and first-30-minute samples",
        ["similar_history_positive_rate", "similar_history_sample_size"],
        "MEDIUM",
    )


def _risk_deductions(summary, stock, theme, sector, evidence):
    risks = []

    def add(kind, points, reason):
        risks.append({"risk_type": kind, "deduction": points, "reason": reason})

    gap = summary.get("auction_gap_pct")
    percentile = summary.get("auction_amount_percentile_20d") or summary.get(
        "auction_amount_percentile_60d"
    )
    if gap is not None and float(gap) >= 7 and percentile is not None and float(percentile) >= 95:
        add("GIANT_HIGH_OPEN", 3, "gap >= 7% and auction amount percentile >= 95")
    if (
        (theme or {}).get("lifecycle") in {"加速", "加速期", "主升期"}
        and gap is not None
        and float(gap) >= 3
    ):
        add("CONTINUOUS_ACCELERATION", 3, "accelerating prior lifecycle with another >=3% gap")
    if (
        summary.get("post_0920_order_decay") is not None
        and float(summary["post_0920_order_decay"]) >= 0.3
    ):
        add("ORDER_DECAY", 3, "post-09:20 unmatched order magnitude decayed by at least 30%")
    if percentile is not None and float(percentile) < 35 and gap is not None and float(gap) >= 2:
        add(
            "INSUFFICIENT_AUCTION_VOLUME",
            2,
            "price is strong but self-history auction volume percentile is below 35",
        )
    if sector and sector.get("structure_status") in {"LEADER_ONLY", "HIGH_OPEN_REVERSAL_RISK"}:
        add("SECTOR_DIVERGENCE", 3, f"sector structure is {sector['structure_status']}")
    if (
        sector
        and sector.get("leader_strength") is not None
        and float(sector["leader_strength"]) >= 55
        and sector.get("capacity_strength") is not None
        and float(sector["capacity_strength"]) < 40
    ):
        add("LEADER_CAPACITY_DIVERGENCE", 3, "leader strength is not confirmed by capacity core")
    levels = [
        str(item.get("evidence_level"))
        for item in ((stock or {}).get("factors") or (theme or {}).get("factors") or [])
    ]
    if levels and all(level == "D" for level in levels):
        add("RUMOR_DRIVEN", 4, "all inherited catalyst evidence is D-level")
    risk_text = " ".join(str(item) for item in evidence)
    for key, kind, points in (
        ("监管", "REGULATORY", 4),
        ("减持", "DECREASE_HOLDING", 4),
        ("解禁", "UNLOCK", 3),
        ("澄清", "CLARIFICATION", 3),
        ("业绩", "EARNINGS_RISK", 3),
    ):
        if key in risk_text:
            add(kind, points, f"refreshed evidence contains {key}")
    if any(key in risk_text for key in ("风险提示", "风险警示", "公告风险")):
        add("ANNOUNCEMENT_RISK", 4, "refreshed official evidence contains an announcement risk")
    if summary.get("quality_status") != "PASS":
        add("DATA_MISSING", 2, "auction summary is incomplete")
    return risks


def _prior_stock(context, code):
    return next((row for row in context.get("stocks") or [] if row.get("ts_code") == code), None)


def _prior_theme(context, name):
    return next(
        (row for row in context.get("mainlines") or [] if row.get("mainline_name") == name), None
    )


def _missing_components(components):
    missing = []
    for name, item in components.items():
        if item["score"] is None:
            missing.append(name)
            continue
        for sub_name, sub in (item.get("subcomponents") or {}).items():
            if sub.get("score") is None:
                missing.append(f"{name}.{sub_name}")
    return missing


def _relevant_evidence(records, summary, watch_stock, prior_stock):
    code = str(summary.get("ts_code") or "")
    name = str(summary.get("stock_name") or "")
    themes = {
        str(value)
        for value in (watch_stock.get("themes") or [])
        + ([prior_stock.get("theme")] if prior_stock and prior_stock.get("theme") else [])
    }
    result = []
    for row in records:
        row_code = str(row.get("ts_code") or row.get("stock_code") or "")
        related = {str(value) for value in row.get("related_themes") or []}
        title = str(row.get("title") or "")
        if (row_code and row_code == code) or (name and name in title) or themes.intersection(related):
            result.append(row)
    return result


def _evidence_validation(auction_component, stock, theme, refreshed):
    factors = (stock or {}).get("factors") or (theme or {}).get("factors") or []
    available = auction_component.get("available_max_score") or 0
    ratio = (auction_component.get("score") or 0) / available if available else None
    market_validation = (
        "strengthened"
        if ratio is not None and ratio >= 0.65
        else "weakened"
        if ratio is not None and ratio <= 0.35
        else "mixed"
        if ratio is not None
        else "unverified"
    )
    hard_new = [
        row for row in refreshed if row.get("evidence_level") in {"A", "B", "C"}
    ]
    return {
        "inherited_factor_ids": [row.get("factor_id") for row in factors],
        "market_validation": market_validation,
        "new_fundamental_evidence": hard_new,
        "interpretation": (
            "auction data validates market-fund recognition only; inherited fundamentals are unchanged"
            if not hard_new
            else "new time-qualified evidence is listed separately from auction market validation"
        ),
    }
