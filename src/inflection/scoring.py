from __future__ import annotations

from typing import Any


STATUS_THRESHOLDS = (
    (80, "MAIN_UPTREND"),
    (70, "TREND_CONFIRMED"),
    (60, "INFLECTION_CONFIRMED"),
    (50, "INFLECTION_CANDIDATE"),
    (40, "INFLECTION_WATCH"),
    (0, "NO_SIGNAL"),
)


def score_features(features: dict[str, Any], fundamental: dict[str, Any] | None = None) -> dict[str, Any]:
    fundamental = fundamental or {}
    fundamental_score = fundamental.get("fundamental_inflection_score")
    price_components = {
        "amount_anomaly": _points(features.get("amount_ratio_20d"), ((3, 5), (2, 4), (1.5, 3), (1, 1))),
        "historical_percentile": _points(features.get("amount_percentile_120d"), ((95, 4), (85, 3), (70, 2), (50, 1))),
        "up_down_amount": _points(features.get("up_down_amount_ratio"), ((1.5, 4), (1.2, 3), (1, 2), (0.8, 1))),
        "breakout_volume": _breakout_volume_points(features),
        "pullback_contraction": _pullback_points(features.get("pullback_volume_ratio")),
        "turnover_volatility_health": _health_points(features),
    }
    daily_components = {
        "breakout_20d": _binary(features.get("breakout_20d"), 3),
        "breakout_60d": _binary(features.get("breakout_60d"), 4),
        "long_breakout": _either_binary(features.get("breakout_120d"), features.get("breakout_250d"), 3),
        "breakout_hold": None if features.get("breakout_hold_status") == "UNAVAILABLE" else (3 if features.get("breakout_hold_status") == "BREAKOUT_HELD" else 0),
        "moving_average_structure": _both_binary(features.get("ma5_gt_ma10_gt_ma20"), features.get("ma20_gt_ma60"), 2),
    }
    weekly_components = {
        "breakout_12w": _binary(features.get("week_breakout_12w"), 3),
        "breakout_26w": _binary(features.get("week_breakout_26w"), 4),
        "breakout_52w": _binary(features.get("week_breakout_52w"), 3),
        "moving_average_structure": _binary(features.get("wma5_gt_wma10_gt_wma20"), 3),
        "wma20_slope": None if features.get("slope_wma20") is None else (2 if features["slope_wma20"] > 0 else 0),
    }
    chip_components = {
        "pullback_volume": _chip_pullback_points(features.get("pullback_volume_ratio")),
        "low_distribution_pressure": _distribution_health_points(features),
        "breakout_retest": 3 if features.get("breakout_retest_hold") else 0,
        "capacity_confirmation": 1 if features.get("capacity_confirmation") == "PASS" else None,
        "breadth_confirmation": 1 if features.get("breadth_confirmation") == "PASS" else None,
    }
    price_score = sum(value for value in price_components.values() if value is not None)
    daily_score = sum(value for value in daily_components.values() if value is not None)
    weekly_score = sum(value for value in weekly_components.values() if value is not None)
    chip_score = sum(value for value in chip_components.values() if value is not None)
    total = sum(value for value in (fundamental_score, price_score, daily_score, weekly_score, chip_score) if value is not None)
    status = _status(total)
    if features.get("distribution_warning"):
        status = "DISTRIBUTION_WARNING"
    elif features.get("trend_broken"):
        status = "TREND_BROKEN"
    maxima = {
        "price_volume": {"amount_anomaly": 5, "historical_percentile": 4, "up_down_amount": 4, "breakout_volume": 5, "pullback_contraction": 4, "turnover_volatility_health": 3},
        "daily_structure": {"breakout_20d": 3, "breakout_60d": 4, "long_breakout": 3, "breakout_hold": 3, "moving_average_structure": 2},
        "weekly_trend": {"breakout_12w": 3, "breakout_26w": 4, "breakout_52w": 3, "moving_average_structure": 3, "wma20_slope": 2},
        "chip_structure": {"pullback_volume": 5, "low_distribution_pressure": 5, "breakout_retest": 3, "capacity_confirmation": 1, "breadth_confirmation": 1},
    }
    groups = {"price_volume": price_components, "daily_structure": daily_components, "weekly_trend": weekly_components, "chip_structure": chip_components}
    available_points = (30 if fundamental_score is not None else 0) + sum(
        maximum for group, values in groups.items() for key, maximum in maxima[group].items() if values[key] is not None
    )
    return {
        "fundamental_inflection_score": fundamental_score,
        "price_volume_score": price_score,
        "daily_structure_score": daily_score,
        "weekly_trend_score": weekly_score,
        "chip_structure_score": chip_score,
        "trend_inflection_score": total,
        "status": status,
        "score_components": {
            "fundamental": fundamental.get("score_components"),
            "price_volume": price_components,
            "daily_structure": daily_components,
            "weekly_trend": weekly_components,
            "chip_structure": chip_components,
        },
        "score_component_coverage": {
            "available_points": available_points,
            "maximum_points": 100,
            "ratio": available_points / 100,
        },
    }


def _points(value: float | None, thresholds: tuple[tuple[float, int], ...]) -> int | None:
    if value is None:
        return None
    return next((points for threshold, points in thresholds if value >= threshold), 0)


def _breakout_volume_points(features: dict[str, Any]) -> int | None:
    if all(features.get(f"breakout_{window}d") is None for window in (20, 60, 120, 250)):
        return None
    if not features.get("breakout_type"):
        return 0
    return {"HIGH_VOLUME_CONFIRMED": 5, "NORMAL_VOLUME": 3, "LOW_VOLUME_BREAKOUT": 1}.get(features.get("breakout_volume_confirmation"), 0)


def _pullback_points(value: float | None) -> int | None:
    if value is None:
        return None
    if value < 0.5: return 4
    if value < 0.7: return 3
    if value < 1: return 1
    return 0


def _health_points(features: dict[str, Any]) -> int | None:
    turnover = features.get("turnover_percentile_120d")
    volatility = features.get("volatility_percentile_120d")
    if turnover is None or volatility is None:
        return None
    if turnover <= 85 and volatility <= 85: return 3
    if turnover <= 95 and volatility <= 95: return 1
    return 0


def _chip_pullback_points(value: float | None) -> int:
    if value is None: return None
    if value < 0.5: return 5
    if value < 0.7: return 4
    if value < 1: return 2
    return 0


def _distribution_health_points(features: dict[str, Any]) -> int:
    if features.get("distribution_warning"): return 0
    upper = features.get("upper_shadow_frequency_20d")
    negative = features.get("large_negative_candle_frequency_20d")
    if upper is None or negative is None: return None
    if upper < 0.1 and negative < 0.05: return 5
    if upper < 0.2 and negative < 0.1: return 3
    return 1


def _status(score: int) -> str:
    return next(status for threshold, status in STATUS_THRESHOLDS if score >= threshold)


def _binary(value: bool | None, points: int) -> int | None:
    return None if value is None else points if value else 0


def _both_binary(left: bool | None, right: bool | None, points: int) -> int | None:
    return None if left is None or right is None else points if left and right else 0


def _either_binary(left: bool | None, right: bool | None, points: int) -> int | None:
    return None if left is None and right is None else points if left or right else 0
