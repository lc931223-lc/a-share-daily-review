from __future__ import annotations

from typing import Any

from src.review_intelligence.helpers import clamp, mean, number, ratio


def compute_market_operability(
    overview: dict[str, Any], indices: list[dict[str, Any]], concentration_score: float | None,
    sector_concentration_score: float | None = None,
) -> dict[str, Any]:
    rise = number(overview.get("rise_count"))
    fall = number(overview.get("fall_count"))
    breadth = ratio(rise, (rise or 0) + (fall or 0), scale=100)
    turnover_change = number(overview.get("turnover_delta_pct"))
    seal_rate = number(overview.get("seal_rate"))
    limit_up = number(overview.get("limit_up_count"))
    limit_down = number(overview.get("limit_down_count"))
    previous_return = number(overview.get("previous_limit_up_avg_change_pct"))
    continuous = overview.get("previous_continuous_board_performance") or {}
    continuous_red = number(continuous.get("red_rate"))
    highest = number(overview.get("highest_board"))
    large_loss = number(overview.get("large_loss_count"))

    components = {
        "liquidity": None if turnover_change is None else clamp(8 + turnover_change * 0.5, 0, 15),
        "breadth": None if breadth is None else clamp(breadth * 0.15, 0, 15),
        "limit_structure": None if seal_rate is None or limit_up is None or limit_down is None else clamp(
            seal_rate * 0.1 + (limit_up - limit_down) * 0.12, 0, 15
        ),
        "previous_limit_feedback": None if previous_return is None else clamp(7.5 + previous_return * 2.5, 0, 15),
        "continuous_board_feedback": None if continuous_red is None else clamp(continuous_red * 0.1, 0, 10),
        "board_height": None if highest is None else clamp(highest * 2, 0, 10),
        "loss_control": None if large_loss is None else clamp(15 - large_loss * 0.75, 0, 15),
        "theme_concentration": None if concentration_score is None else clamp(concentration_score * 0.1, 0, 10),
    }
    maxima = {
        "liquidity": 15, "breadth": 15, "limit_structure": 15, "previous_limit_feedback": 15,
        "continuous_board_feedback": 10, "board_height": 10, "loss_control": 10,
        "theme_concentration": 10,
    }
    # loss_control is capped to its assigned ten points after preserving a steeper penalty curve.
    if components["loss_control"] is not None:
        components["loss_control"] = min(10.0, components["loss_control"])
    available = sum(maxima[key] for key, value in components.items() if value is not None)
    score = sum(value for value in components.values() if value is not None)
    index_returns = []
    for item in indices:
        change = number(item.get("change_pct"))
        if change is None:
            change = ratio((number(item.get("close")) or 0) - (number(item.get("open")) or 0), item.get("open"), scale=100)
        if change is not None:
            index_returns.append(change)
    dispersion = max(index_returns) - min(index_returns) if len(index_returns) >= 2 else None
    return {
        "total_turnover": number(overview.get("total_market_turnover")),
        "turnover_change_pct": turnover_change,
        "rise_count": int(rise) if rise is not None else None,
        "fall_count": int(fall) if fall is not None else None,
        "limit_up_count": int(limit_up) if limit_up is not None else None,
        "limit_down_count": int(limit_down) if limit_down is not None else None,
        "failed_limit_count": overview.get("failed_limit_count"),
        "seal_rate": seal_rate,
        "previous_limit_avg_return": previous_return,
        "previous_limit_red_rate": number((overview.get("previous_limit_up_performance") or {}).get("red_rate")),
        "continuous_board_red_rate": continuous_red,
        "highest_board": highest,
        "high_level_loss_count": _high_level_loss_count(overview),
        "large_loss_count": large_loss,
        "index_strength_dispersion": dispersion,
        "sector_concentration": sector_concentration_score,
        "theme_concentration": concentration_score,
        "market_operability_score": round(score, 2),
        "available_max_score": available,
        "feature_components": {key: round(value, 2) if value is not None else None for key, value in components.items()},
    }


def compute_cycle_features(
    overview: dict[str, Any], stocks: list[dict[str, Any]], theme_changes: dict[str, int] | None
) -> dict[str, Any]:
    changes = theme_changes or {"new": 0, "strengthening": 0, "weakening": 0}
    limit_up = number(overview.get("limit_up_count"))
    rise = number(overview.get("rise_count"))
    failed = number(overview.get("failed_limit_count"))
    high_returns = [row.get("change_pct") for row in stocks if (number(row.get("board_count")) or 0) >= 4]
    mid_returns = [row.get("change_pct") for row in stocks if 2 <= (number(row.get("board_count")) or 0) < 4]
    low_first = sum((number(row.get("board_count")) or 0) == 1 for row in stocks)
    failed_rate = ratio(failed, (failed or 0) + (limit_up or 0), scale=100)
    vector = {
        "new_theme_count": changes.get("new", 0),
        "strengthening_theme_count": changes.get("strengthening", 0),
        "weakening_theme_count": changes.get("weakening", 0),
        "limit_up_breadth": ratio(limit_up, rise, scale=100),
        "continuous_board_height": number(overview.get("highest_board")),
        "promotion_rate": number(overview.get("promotion_rate")),
        "previous_limit_feedback": number(overview.get("previous_limit_up_avg_change_pct")),
        "high_level_stock_return": mean(high_returns),
        "mid_level_stock_return": mean(mid_returns),
        "low_level_first_board_count": low_first,
        "failed_limit_rate": failed_rate,
        "large_loss_count": number(overview.get("large_loss_count")),
    }
    candidates = []
    if changes.get("new", 0) >= 2 and (limit_up or 0) >= 20:
        candidates.append("STARTUP_CANDIDATE")
    if (number(overview.get("highest_board")) or 0) >= 4 and (number(overview.get("seal_rate")) or 0) >= 50:
        candidates.append("MAIN_UP_CANDIDATE")
    if (failed_rate or 0) >= 40 or (number(overview.get("large_loss_count")) or 0) >= 15:
        candidates.append("HIGH_VOLATILITY_CANDIDATE")
    if (number(overview.get("fall_count")) or 0) > (number(overview.get("rise_count")) or 0) * 1.5 and (
        number(overview.get("previous_limit_up_avg_change_pct")) or 0
    ) < 0:
        candidates.append("RETREAT_CANDIDATE")
    if changes.get("strengthening", 0) > changes.get("weakening", 0) and not candidates:
        candidates.append("REPAIR_CANDIDATE")
    return {"cycle_feature_vector": vector, "cycle_candidates": candidates or ["NO_STRUCTURE"]}


def _high_level_loss_count(overview: dict[str, Any]) -> int | None:
    value = number(overview.get("high_level_loss_count"))
    return int(value) if value is not None else None
