from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.review_intelligence.helpers import clamp, mean, number, percentile_rank, stock_code


def build_role_candidates(
    themes: list[dict[str, Any]],
    stock_lookup: dict[str, dict[str, Any]],
    inflections: dict[str, dict[str, Any]],
    auction: dict[str, dict[str, Any]],
    previous_scores: dict[str, dict[str, float]] | None = None,
    five_day_scores: dict[str, dict[str, float]] | None = None,
    twenty_day_scores: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    output = []
    previous_scores = previous_scores or {}
    five_day_scores = five_day_scores or {}
    twenty_day_scores = twenty_day_scores or {}
    for theme in themes[:20]:
        name = theme["theme_name"]
        raw_candidates = _theme_stocks(theme)
        amounts = [row.get("amount") for row in raw_candidates.values()]
        caps = [stock_lookup.get(code, {}).get("market_cap") for code in raw_candidates]
        leader_return = max((number(row.get("change_pct")) or -100 for row in raw_candidates.values()), default=None)
        for code, source in raw_candidates.items():
            stock = stock_lookup.get(code, {}) | source
            inflection = inflections.get(code, {})
            auction_row = auction.get(code, {})
            amount_pct = percentile_rank(amounts, stock.get("amount"))
            cap_pct = percentile_rank(caps, stock.get("market_cap"))
            board = number(stock.get("board_count")) or 0
            change = number(stock.get("change_pct"))
            auction_score = number(auction_row.get("auction_volume_anomaly_score"))
            leader = clamp(board * 18 + max(change or 0, 0) * 2 + (auction_score or 0) + (number(stock.get("leader_candidate_score")) or 0) * .35)
            capacity = clamp((amount_pct or 0) * .35 + (cap_pct or 0) * .3 + (number(stock.get("capacity_candidate_score")) or 0) * .25 + (number(inflection.get("trend_inflection_score")) or 0) * .1)
            trend = clamp((number(inflection.get("trend_inflection_score")) or 0) * .8 + (20 if inflection.get("breakout_hold_days") else 0))
            elasticity = clamp(max(change or 0, 0) * 5 + (number(stock.get("turnover_rate")) or 0) * 1.5 + board * 10)
            lag = max((leader_return or 0) - (change or 0), 0)
            catch_up = clamp((number(theme.get("theme_inflection_score")) or 0) * .35 + min(lag, 10) * 3 + (amount_pct or 0) * .2)
            follower = clamp((number(theme.get("theme_inflection_score")) or 0) * .4 + max(change or 0, 0) * 2)
            scores = {"leader": leader, "capacity": capacity, "trend_leader": trend, "elasticity": elasticity, "catch_up": catch_up, "follower": follower}
            qualified = _qualified_roles(scores, amount_pct, cap_pct, board, change, leader_return)
            if not qualified:
                continue
            role = max(qualified, key=lambda item: scores[item])
            role_name = f"{role.upper()}_CANDIDATE"
            if role == "trend_leader":
                role_name = "TREND_LEADER_CANDIDATE"
            prior = previous_scores.get(f"{name}:{code}", {})
            prior_five = five_day_scores.get(f"{name}:{code}", {})
            prior_twenty = twenty_day_scores.get(f"{name}:{code}", {})
            output.append({
                "ts_code": code, "stock_name": stock.get("stock_name") or stock.get("name"),
                "theme": name, "role_candidate": role_name,
                "all_role_candidates": ["TREND_LEADER_CANDIDATE" if item == "trend_leader" else f"{item.upper()}_CANDIDATE" for item in qualified],
                "role_candidate_score": round(scores[role], 2),
                "role_scores": {key: round(value, 2) for key, value in scores.items()},
                "role_score_change_1d": scores[role] - number(prior.get(role)) if number(prior.get(role)) is not None else None,
                "role_score_change_5d": scores[role] - number(prior_five.get(role)) if number(prior_five.get(role)) is not None else None,
                "role_score_change_20d": scores[role] - number(prior_twenty.get(role)) if number(prior_twenty.get(role)) is not None else None,
                "board_height": board, "relative_strength": change,
                "theme_leadership": number(theme.get("theme_inflection_score")),
                "theme_follow_rate": number(theme.get("theme_breadth")),
                "turnover": number(stock.get("turnover_rate")), "amount": number(stock.get("amount")),
                "recognition_score": number(stock.get("leader_candidate_score")),
                "continuity": number(stock.get("continuous_board_count")),
                "previous_day_strength": number(stock.get("previous_day_change")),
                "auction_confirmation": auction_score,
                "candidate_only": True,
            })
    output.sort(key=lambda row: (-row["role_candidate_score"], row["ts_code"], row["theme"]))
    return output


def compute_money_effects(roles: list[dict[str, Any]], themes: list[dict[str, Any]]) -> dict[str, Any]:
    returns: dict[str, list[Any]] = defaultdict(list)
    for row in roles:
        for role in row.get("all_role_candidates") or [row["role_candidate"]]:
            returns[role].append(row.get("relative_strength"))
    theme_returns = [row.get("theme_return") for row in themes]
    new_returns = [row.get("theme_return") for row in themes if row.get("score_change") is None]
    old_returns = [row.get("theme_return") for row in themes if row.get("score_change") is not None]
    features = {
        "leader_return": mean(returns["LEADER_CANDIDATE"]),
        "capacity_return": mean(returns["CAPACITY_CANDIDATE"]),
        "catch_up_return": mean(returns["CATCH_UP_CANDIDATE"]),
        "new_theme_return": mean(new_returns), "old_theme_return": mean(old_returns),
        "high_level_return": mean([row.get("relative_strength") for row in roles if (number(row.get("board_height")) or 0) >= 3]),
        "low_level_return": mean([row.get("relative_strength") for row in roles if (number(row.get("board_height")) or 0) <= 1]),
        "all_theme_return": mean(theme_returns),
    }
    available = {key: value for key, value in features.items() if value is not None}
    candidates = []
    if available:
        role_values = {"LEADER_DOMINANT": features["leader_return"], "CATCH_UP_DOMINANT": features["catch_up_return"], "ROTATION_DOMINANT": features["new_theme_return"]}
        valid_roles = {key: value for key, value in role_values.items() if value is not None}
        if valid_roles:
            candidates.append(max(valid_roles, key=valid_roles.get))
        if features["new_theme_return"] is not None and features["old_theme_return"] is not None and features["new_theme_return"] > features["old_theme_return"] + 2:
            candidates.append("SWITCH_CANDIDATE")
        if (features["all_theme_return"] or 0) > 0 and (features["high_level_return"] or 0) < 0:
            candidates.append("REPAIR_CANDIDATE")
    return {"features": features, "structure_candidates": candidates or ["NO_STRUCTURE"]}


def build_chip_candidates(
    inflections: dict[str, dict[str, Any]], roles: list[dict[str, Any]],
    previous_scores: dict[str, float] | None = None,
    five_day_scores: dict[str, float] | None = None,
    twenty_day_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    role_map = {row["ts_code"]: row for row in roles}
    previous_scores, five_day_scores, twenty_day_scores = previous_scores or {}, five_day_scores or {}, twenty_day_scores or {}
    rows = []
    for code, item in inflections.items():
        if code not in role_map and item.get("status") in (None, "NO_SIGNAL"):
            continue
        available = [
            item.get("pullback_volume_ratio"), item.get("amount_percentile_120d"),
            item.get("turnover_percentile_120d"), item.get("volatility_percentile_120d"),
            item.get("upper_shadow_frequency_20d"), item.get("large_negative_candle_frequency_20d"),
        ]
        score = number(item.get("chip_structure_score"))
        rows.append({
            "ts_code": code, "stock_name": item.get("stock_name") or role_map.get(code, {}).get("stock_name"),
            "pullback_volume_ratio": number(item.get("pullback_volume_ratio")),
            "amount_percentile": number(item.get("amount_percentile_120d")),
            "turnover_percentile": number(item.get("turnover_percentile_120d")),
            "volatility_percentile": number(item.get("volatility_percentile_120d")),
            "upper_shadow_frequency": number(item.get("upper_shadow_frequency_20d")),
            "large_negative_frequency": number(item.get("large_negative_candle_frequency_20d")),
            "breakout_hold": item.get("breakout_hold_status"),
            "catalyst_price_response": item.get("catalyst_price_response"),
            "chip_health_feature_score": score,
            "chip_health_change": score - number(previous_scores.get(code)) if score is not None and number(previous_scores.get(code)) is not None else None,
            "chip_health_change_1d": score - number(previous_scores.get(code)) if score is not None and number(previous_scores.get(code)) is not None else None,
            "chip_health_change_5d": score - number(five_day_scores.get(code)) if score is not None and number(five_day_scores.get(code)) is not None else None,
            "chip_health_change_20d": score - number(twenty_day_scores.get(code)) if score is not None and number(twenty_day_scores.get(code)) is not None else None,
            "available_feature_count": sum(value is not None for value in available),
            "risk_flags": item.get("risk_flags") or [],
        })
    return sorted(rows, key=lambda row: (-(row["chip_health_feature_score"] or -1), row["ts_code"]))[:100]


def detect_catalyst_fatigue(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        code = stock_code(event.get("ts_code") or event.get("stock_code"))
        if code:
            grouped[code].append(event)
    results = []
    for code, rows in grouped.items():
        if len(rows) < 2:
            continue
        previous, current = rows[-2], rows[-1]
        if (number(current.get("strength")) or 0) > (number(previous.get("strength")) or 0) and (
            number(current.get("return_3d")) is not None and number(previous.get("return_3d")) is not None
            and number(current.get("return_3d")) < number(previous.get("return_3d"))
        ):
            results.append({
                "ts_code": code, "label": "POSITIVE_CATALYST_FATIGUE_CANDIDATE",
                "previous_response": previous, "current_response": current, "candidate_only": True,
            })
    return results


def _theme_stocks(theme: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for field in ("top_gainers", "leader_candidates", "capacity_candidates", "catch_up_candidates", "trend_candidates"):
        for item in theme.get(field) or []:
            code = stock_code(item.get("stock_code") or item.get("ts_code"))
            if code:
                rows.setdefault(code, {}).update(item)
    return rows


def _qualified_roles(scores, amount_pct, cap_pct, board, change, leader_return):
    roles = []
    if board >= 2 or scores["leader"] >= 55:
        roles.append("leader")
    if (amount_pct or 0) >= 75 and ((cap_pct or 0) >= 50 or scores["capacity"] >= 50):
        roles.append("capacity")
    if scores["trend_leader"] >= 40:
        roles.append("trend_leader")
    if scores["elasticity"] >= 45:
        roles.append("elasticity")
    if leader_return is not None and change is not None and 0 <= change < leader_return and scores["catch_up"] >= 35:
        roles.append("catch_up")
    if not roles and (change or 0) > 0:
        roles.append("follower")
    return roles
