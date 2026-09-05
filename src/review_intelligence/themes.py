from __future__ import annotations

from typing import Any

from src.review_intelligence.helpers import clamp, mean, number, ratio, stock_code


def compute_concentration(themes: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in themes if (number(row.get("amount")) or 0) > 0]
    amounts = sorted((number(row.get("amount")) or 0 for row in valid), reverse=True)
    limits = sorted((number(row.get("limit_up_count")) or 0 for row in themes), reverse=True)
    total_amount = sum(amounts)
    total_limits = sum(limits)
    top1_amount = ratio(sum(amounts[:1]), total_amount, scale=100)
    top3_amount = ratio(sum(amounts[:3]), total_amount, scale=100)
    top1_limit = ratio(sum(limits[:1]), total_limits, scale=100)
    top3_limit = ratio(sum(limits[:3]), total_limits, scale=100)
    breadth = mean([
        ratio(row.get("rise_count"), (number(row.get("rise_count")) or 0) + (number(row.get("fall_count")) or 0), scale=100)
        for row in themes[:3]
    ])
    capacity = mean([_capacity_share(row) for row in themes[:3]])
    components = {
        "top1_theme_amount_share": top1_amount,
        "top3_theme_amount_share": top3_amount,
        "top1_limit_up_share": top1_limit,
        "top3_limit_up_share": top3_limit,
        "top_theme_breadth": breadth,
        "core_capacity_share": capacity,
    }
    # Top-3 shares are structurally high in small universes, so Top-1 dominance carries more weight.
    weighted = [
        (top1_amount, 0.40), (top3_amount, 0.10), (top1_limit, 0.25),
        (top3_limit, 0.05), (breadth, 0.10), (capacity, 0.10),
    ]
    available_weight = sum(weight for value, weight in weighted if value is not None)
    score = sum(value * weight for value, weight in weighted if value is not None) / available_weight if available_weight else None
    label = "UNAVAILABLE" if score is None else "HIGH" if score >= 65 else "MEDIUM" if score >= 40 else "LOW"
    return {
        "theme_concentration_score": round(score, 2) if score is not None else None,
        "concentration_candidate": label,
        "feature_components": components,
        "available_component_weight": round(available_weight, 2),
    }


def score_themes(
    themes: list[dict[str, Any]],
    inflections: dict[str, dict[str, Any]],
    announcement_counts: dict[str, dict[str, int]],
    previous_review: dict[str, float],
    previous_scores: dict[str, float],
    five_day_scores: dict[str, float] | None = None,
    twenty_day_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    five_day_scores = five_day_scores or {}
    twenty_day_scores = twenty_day_scores or {}
    for raw in themes:
        name = str(raw.get("normalized_name") or raw.get("theme_name") or raw.get("name") or "").strip()
        if not name:
            continue
        rise = number(raw.get("rise_count"))
        fall = number(raw.get("fall_count"))
        breadth = ratio(rise, (rise or 0) + (fall or 0), scale=100)
        theme_return = number(raw.get("change_pct"))
        candidates = _candidate_rows(raw)
        leader_strength = _candidate_strength(raw.get("leader_candidates"), "leader_candidate_score", candidates)
        capacity_strength = _candidate_strength(raw.get("capacity_candidates"), "capacity_candidate_score", candidates)
        catch_up_strength = _candidate_strength(raw.get("catch_up_candidates"), "catch_up_candidate_score", candidates)
        trend_values = []
        for item in candidates:
            code = stock_code(item.get("stock_code") or item.get("ts_code"))
            if code and code in inflections:
                trend_values.append(inflections[code].get("trend_inflection_score"))
        trend_candidates = sorted(
            ({
                "ts_code": code, "stock_code": code, "stock_name": item.get("stock_name"),
                "change_pct": item.get("pct_chg"), "amount": item.get("amount"),
                "trend_inflection_score": item.get("trend_inflection_score"),
            } for code, item in inflections.items() if _matches_theme(item, name) and (number(item.get("trend_inflection_score")) or 0) >= 40),
            key=lambda item: -(number(item.get("trend_inflection_score")) or 0),
        )[:5]
        trend_values.extend(item.get("trend_inflection_score") for item in trend_candidates)
        trend_strength = max((number(value) or 0 for value in trend_values), default=None)
        catalyst = announcement_counts.get(name, {})
        score_parts = {
            "return": None if theme_return is None else clamp(50 + theme_return * 5),
            "breadth": breadth,
            "limit_up": clamp((number(raw.get("limit_up_count")) or 0) * 12),
            "roles": mean([leader_strength, capacity_strength, trend_strength, catch_up_strength]),
            "volume": None if number(raw.get("amount_change")) is None else clamp(50 + number(raw.get("amount_change")) * 50),
            "catalyst": clamp((catalyst.get("A", 0) * 15 + catalyst.get("B", 0) * 8)),
        }
        weights = {"return": .2, "breadth": .2, "limit_up": .15, "roles": .2, "volume": .15, "catalyst": .1}
        available = sum(weights[key] for key, value in score_parts.items() if value is not None)
        score = sum(value * weights[key] for key, value in score_parts.items() if value is not None) / available if available else None
        previous = number(previous_scores.get(name))
        previous_five = number(five_day_scores.get(name))
        previous_twenty = number(twenty_day_scores.get(name))
        row = dict(raw)
        row.update({
            "theme_name": name, "theme_return": theme_return,
            "top_stock_return": mean([row.get("change_pct") for row in raw.get("top_gainers") or []]),
            "theme_breadth": breadth,
            "theme_amount": number(raw.get("amount")), "theme_amount_change": number(raw.get("amount_change")),
            "leader_strength": leader_strength, "capacity_strength": capacity_strength,
            "trend_leader_strength": trend_strength, "catch_up_strength": catch_up_strength,
            "theme_volume_anomaly": _volume_label(raw.get("amount_change")),
            "theme_inflection_score": round(score, 2) if score is not None else None,
            "official_catalyst_count": sum(catalyst.values()), "evidence_A_count": catalyst.get("A", 0),
            "evidence_B_count": catalyst.get("B", 0), "previous_review_score": number(previous_review.get(name)),
            "score_change": score - previous if score is not None and previous is not None else None,
            "score_change_1d": score - previous if score is not None and previous is not None else None,
            "score_change_5d": score - previous_five if score is not None and previous_five is not None else None,
            "score_change_20d": score - previous_twenty if score is not None and previous_twenty is not None else None,
            "score_components": score_parts, "quality_status": "PASS" if available >= .8 else "PARTIAL",
            "trend_candidates": trend_candidates,
        })
        rows.append(row)
    return sorted(rows, key=lambda row: (-(row.get("theme_inflection_score") or -1), row["theme_name"]))


def theme_change_counts(current: list[dict[str, Any]], previous: dict[str, float]) -> dict[str, int]:
    current_scores = {row["theme_name"]: number(row.get("theme_inflection_score")) for row in current}
    return {
        "new": sum(name not in previous and (score or 0) >= 45 for name, score in current_scores.items()),
        "strengthening": sum(name in previous and score is not None and score - previous[name] >= 8 for name, score in current_scores.items()),
        "weakening": sum(name in previous and score is not None and score - previous[name] <= -8 for name, score in current_scores.items()),
    }


def _capacity_share(theme: dict[str, Any]) -> float | None:
    total = sum(number(row.get("amount")) or 0 for row in theme.get("top_gainers") or [])
    capacity = sum(number(row.get("amount")) or 0 for row in theme.get("capacity_candidates") or [])
    return ratio(capacity, total, scale=100)


def _candidate_rows(theme: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for field in ("top_gainers", "leader_candidates", "capacity_candidates", "catch_up_candidates", "trend_candidates"):
        for row in theme.get(field) or []:
            code = stock_code(row.get("stock_code") or row.get("ts_code"))
            if code:
                merged.setdefault(code, {}).update(row)
    return list(merged.values())


def _candidate_strength(rows: Any, score_key: str, fallback: list[dict[str, Any]]) -> float | None:
    source = rows or []
    values = [number(row.get(score_key)) for row in source]
    values = [value for value in values if value is not None]
    if values:
        return max(values)
    source_codes = {stock_code(row.get("stock_code")) for row in source}
    returns = [number(row.get("change_pct")) for row in fallback if stock_code(row.get("stock_code")) in source_codes]
    returns = [value for value in returns if value is not None]
    return clamp(50 + max(returns) * 5) if returns else None


def _volume_label(value: Any) -> str | None:
    parsed = number(value)
    if parsed is None:
        return None
    return "EXTREME" if parsed >= 1 else "STRONG" if parsed >= .3 else "WEAK" if parsed <= -.3 else "NORMAL"


def _matches_theme(item: dict[str, Any], name: str) -> bool:
    return str(item.get("industry") or "") == name or name in (item.get("themes") or [])
