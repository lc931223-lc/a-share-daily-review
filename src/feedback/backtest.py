from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

ERROR_TYPES = {
    "THEME_WRONG",
    "STYLE_WRONG",
    "CYCLE_WRONG",
    "LEADER_WRONG",
    "TIMING_WRONG",
    "CATALYST_WRONG",
    "RISK_IGNORED",
    "DATA_LIMITATION",
}
SOURCE_REVIEW = "AS_OF_DAILY_PROXY.v1"
HORIZONS = (5, 10, 20)


def run_as_of_backtest(
    daily: pd.DataFrame,
    metadata: dict[str, dict[str, Any]],
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    frame = _prepare(daily, metadata)
    if frame.empty:
        raise ValueError("daily history is empty")
    trading_dates = sorted(
        frame.loc[frame["trade_date"].between(start, end), "trade_date"].unique()
    )
    all_dates = sorted(frame["trade_date"].unique())
    date_position = {value: index for index, value in enumerate(all_dates)}
    predictions: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []

    for trade_date in trading_dates:
        day = frame[frame["trade_date"] == trade_date].copy()
        prediction = _prediction(day, trade_date)
        predictions.append(prediction)
        validation = _validation(day, prediction, all_dates, date_position)
        if validation is not None:
            validations.append(validation)

    metrics = calculate_metrics(predictions, validations)
    return {
        "meta": {
            "schema_version": "as_of_backtest.1",
            "start_date": start,
            "end_date": end,
            "source_review": SOURCE_REVIEW,
            "prediction_count": len(predictions),
            "validation_count": len(validations),
            "adjustment_mode": "RAW_UNADJUSTED",
            "strict_as_of": True,
        },
        "metrics": metrics,
        "predictions": predictions,
        "validations": validations,
        "data_limitations": [
            "Historical official_review is unavailable for most dates; proxy records are never labeled as formal review.",
            "Industry membership uses the cached stock_basic classification and may contain classification or survivorship drift.",
            "Adjustment factors are unavailable; stock returns and structures use raw close prices.",
            "Theme predictions are industry aggregates because historical point-in-time concept membership is unavailable.",
            "Auction process snapshots are unavailable for the historical interval and are not reconstructed.",
        ],
    }


def calculate_metrics(
    predictions: list[dict[str, Any]],
    validations: list[dict[str, Any]],
) -> dict[str, Any]:
    complete_5d = [row for row in validations if row["actual_theme_result"].get("top_theme_5d")]
    top1_hits = sum(
        bool(row["theme_return_5d"].get("predicted_top1_is_actual_top1")) for row in complete_5d
    )
    top3_hits = sum(
        bool(row["theme_return_5d"].get("actual_top1_in_predicted_top3")) for row in complete_5d
    )
    leaders = [
        item
        for row in validations
        for item in row.get("leader_result") or []
        if item.get("return_5d") is not None
    ]
    return {
        "theme_top1_accuracy": _ratio(top1_hits, len(complete_5d))
        | {
            "definition": "Predicted Top1 industry equals the highest equal-weight industry return over the next five trading days."
        },
        "theme_top3_coverage": _ratio(top3_hits, len(complete_5d))
        | {
            "definition": "The highest-returning industry over the next five trading days appears in the predicted Top3."
        },
        "leader_candidate_win_rate": _ratio(
            sum(item["return_5d"] > 0 for item in leaders), len(leaders)
        )
        | {"definition": "Candidate raw close return is positive after five trading days."},
        "sample_counts": {
            "predictions": len(predictions),
            "theme_5d": len(complete_5d),
            "leader_5d": len(leaders),
        },
    }


def _prepare(daily: pd.DataFrame, metadata: dict[str, dict[str, Any]]) -> pd.DataFrame:
    required = {"trade_date", "ts_code", "close", "high", "low", "pct_chg", "amount"}
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f"daily history missing columns: {sorted(missing)}")
    frame = daily.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["ts_code"] = frame["ts_code"].astype(str)
    for column in ("close", "high", "low", "pct_chg", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "ts_code", "close"]).sort_values(
        ["ts_code", "trade_date"]
    )
    frame = frame.drop_duplicates(["trade_date", "ts_code"], keep="last")
    frame["industry"] = frame["ts_code"].map(
        lambda code: (metadata.get(code) or {}).get("industry")
    )
    frame["stock_name"] = frame["ts_code"].map(
        lambda code: (metadata.get(code) or {}).get("stock_name")
    )
    frame["industry"] = frame["industry"].fillna("UNKNOWN")
    grouped = frame.groupby("ts_code", sort=False)
    frame["prior_high_20d"] = grouped["high"].transform(
        lambda values: values.shift(1).rolling(20, min_periods=20).max()
    )
    frame["prior_amount_20d"] = grouped["amount"].transform(
        lambda values: values.shift(1).rolling(20, min_periods=20).mean()
    )
    frame["prior_high_60d"] = grouped["high"].transform(
        lambda values: values.shift(1).rolling(60, min_periods=40).max()
    )
    for horizon in HORIZONS:
        frame[f"return_{horizon}d"] = grouped["close"].transform(
            lambda values, h=horizon: values.shift(-h) / values - 1
        )
    frame["future_max_gain_20d"] = grouped.apply(
        lambda group: _future_extreme(group["high"], group["close"], "max"),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    frame["future_max_drawdown_20d"] = grouped.apply(
        lambda group: _future_extreme(group["low"], group["close"], "min"),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    return frame.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


def _future_extreme(values: pd.Series, close: pd.Series, mode: str) -> pd.Series:
    shifted = values.shift(-1)
    reverse = shifted.iloc[::-1]
    extreme = (
        reverse.rolling(20, min_periods=1).max()
        if mode == "max"
        else reverse.rolling(20, min_periods=1).min()
    ).iloc[::-1]
    return extreme / close - 1


def _prediction(day: pd.DataFrame, trade_date: str) -> dict[str, Any]:
    usable = day[day["industry"] != "UNKNOWN"].copy()
    theme_rows = []
    for industry, rows in usable.groupby("industry"):
        valid_pct = rows["pct_chg"].dropna()
        theme_rows.append(
            {
                "theme": industry,
                "strength": _number(valid_pct.mean()),
                "breadth": _number((valid_pct > 0).mean()),
                "amount": _number(rows["amount"].sum(min_count=1)),
                "stock_count": len(rows),
            }
        )
    themes = pd.DataFrame(theme_rows)
    if not themes.empty:
        themes["score"] = (
            themes["strength"].rank(pct=True).fillna(0) * 0.55
            + themes["breadth"].rank(pct=True).fillna(0) * 0.25
            + themes["amount"].rank(pct=True).fillna(0) * 0.20
        )
        theme_prediction = (
            themes.sort_values(["score", "amount"], ascending=False).head(3).to_dict("records")
        )
        theme_prediction = [_clean_dict(item) for item in theme_prediction]
    else:
        theme_prediction = []
    top_themes = {row["theme"] for row in theme_prediction}
    leaders = usable[usable["industry"].isin(top_themes)].copy()
    if not leaders.empty:
        leaders["leader_score"] = (
            leaders["pct_chg"].rank(pct=True).fillna(0) * 0.6
            + leaders["amount"].rank(pct=True).fillna(0) * 0.4
        )
    leader_candidates = (
        [_stock_summary(row) for _, row in leaders.nlargest(5, "leader_score").iterrows()]
        if not leaders.empty
        else []
    )
    inflections = usable[
        (usable["close"] > usable["prior_high_20d"])
        & (usable["amount"] >= usable["prior_amount_20d"] * 1.5)
    ].copy()
    if not inflections.empty:
        inflections["inflection_score"] = (
            inflections["close"] / inflections["prior_high_20d"] - 1
        ).clip(0, 0.2) * 200 + (inflections["amount"] / inflections["prior_amount_20d"]).clip(
            0, 5
        ) * 10
    inflection_candidates = (
        [
            _stock_summary(row, "inflection_score")
            for _, row in inflections.nlargest(10, "inflection_score").iterrows()
        ]
        if not inflections.empty
        else []
    )
    breadth = _number((day["pct_chg"] > 0).mean())
    avg_change = _number(day["pct_chg"].mean())
    cycle = (
        "MAIN_UP_CANDIDATE"
        if breadth is not None and breadth >= 0.55 and (avg_change or 0) > 0
        else "RETREAT_CANDIDATE"
        if breadth is not None and breadth < 0.35
        else "REPAIR_CANDIDATE"
    )
    styles = _style_rank(day, "pct_chg")
    risk_points = []
    if breadth is not None and breadth < 0.35:
        risk_points.append({"type": "WEAK_BREADTH", "value": breadth})
    distribution = usable[
        (usable["high"] >= usable["prior_high_60d"] * 0.98)
        & (usable["amount"] >= usable["prior_amount_20d"] * 1.8)
        & (usable["pct_chg"] < 0)
    ]
    if not distribution.empty:
        risk_points.append(
            {
                "type": "DISTRIBUTION_WARNING",
                "stock_count": len(distribution),
                "codes": distribution["ts_code"].head(20).tolist(),
            }
        )
    return {
        "prediction_date": trade_date,
        "source_review": SOURCE_REVIEW,
        "theme_prediction": theme_prediction,
        "style_prediction": styles,
        "leader_candidates": leader_candidates,
        "next_day_plan": [
            {"ts_code": row["ts_code"], "theme": row["industry"], "role": "OBJECTIVE_WATCH"}
            for row in leader_candidates
        ],
        "inflection_candidates": inflection_candidates,
        "risk_points": risk_points,
        "confidence_level": "LOW",
        "cycle_prediction": cycle,
        "record_kind": "HISTORICAL_OBJECTIVE_PROXY",
        "as_of": f"{trade_date}T15:05:00+08:00",
    }


def _validation(
    day: pd.DataFrame,
    prediction: dict[str, Any],
    all_dates: list[str],
    positions: dict[str, int],
) -> dict[str, Any] | None:
    if not any(day[f"return_{horizon}d"].notna().any() for horizon in HORIZONS):
        return None
    predicted_themes = [row["theme"] for row in prediction["theme_prediction"]]
    theme_returns: dict[int, dict[str, float]] = {}
    for horizon in HORIZONS:
        values = (
            day[day["industry"] != "UNKNOWN"]
            .groupby("industry")[f"return_{horizon}d"]
            .mean()
            .dropna()
            .sort_values(ascending=False)
        )
        theme_returns[horizon] = {str(key): round(float(value), 8) for key, value in values.items()}
    actual_top = next(iter(theme_returns[5]), None)
    actual_style = _style_rank(day, "return_5d")
    leader_codes = {row["ts_code"] for row in prediction["leader_candidates"]}
    inflection_codes = {row["ts_code"] for row in prediction["inflection_candidates"]}
    leader_result = [_result(row) for _, row in day[day["ts_code"].isin(leader_codes)].iterrows()]
    stock_result = [
        _result(row) for _, row in day[day["ts_code"].isin(inflection_codes)].iterrows()
    ]
    selected = leader_result + stock_result
    max_gain = max(
        (row["max_gain"] for row in selected if row["max_gain"] is not None), default=None
    )
    max_drawdown = min(
        (row["max_drawdown"] for row in selected if row["max_drawdown"] is not None), default=None
    )
    market_return_5d = _number(day["return_5d"].mean())
    actual_market_state = {
        "return_5d": market_return_5d,
        "state": "STRENGTHENED"
        if market_return_5d is not None and market_return_5d > 0.02
        else "WEAKENED"
        if market_return_5d is not None and market_return_5d < -0.02
        else "MIXED",
        "actual_style_5d": actual_style[0]["style"] if actual_style else None,
    }
    errors = _errors(
        prediction, actual_top, actual_market_state, leader_result, max_drawdown, theme_returns
    )
    position = positions[prediction["prediction_date"]]
    last_horizon = max(h for h in HORIZONS if day[f"return_{h}d"].notna().any())
    validation_date = all_dates[min(position + last_horizon, len(all_dates) - 1)]
    return {
        "prediction_date": prediction["prediction_date"],
        "source_review": SOURCE_REVIEW,
        "validation_date": validation_date,
        "actual_market_state": actual_market_state,
        "actual_theme_result": {"top_theme_5d": actual_top, "top_styles_5d": actual_style[:3]},
        "theme_return_5d": _theme_result(theme_returns[5], predicted_themes, actual_top),
        "theme_return_10d": _theme_result(
            theme_returns[10], predicted_themes, next(iter(theme_returns[10]), None)
        ),
        "theme_return_20d": _theme_result(
            theme_returns[20], predicted_themes, next(iter(theme_returns[20]), None)
        ),
        "leader_result": leader_result,
        "stock_result": stock_result,
        "max_gain": max_gain,
        "max_drawdown": max_drawdown,
        "error_type": errors,
    }


def _errors(prediction, actual_top, market_state, leaders, max_drawdown, theme_returns):
    errors = ["DATA_LIMITATION"]
    predicted_themes = [row["theme"] for row in prediction["theme_prediction"]]
    if actual_top and predicted_themes and predicted_themes[0] != actual_top:
        errors.append("THEME_WRONG")
    predicted_style = (prediction.get("style_prediction") or [{}])[0].get("style")
    if (
        predicted_style
        and market_state.get("actual_style_5d")
        and predicted_style != market_state["actual_style_5d"]
    ):
        errors.append("STYLE_WRONG")
    if (
        prediction.get("cycle_prediction") == "MAIN_UP_CANDIDATE"
        and market_state.get("state") == "WEAKENED"
    ):
        errors.append("CYCLE_WRONG")
    if leaders and not any((row.get("return_5d") or 0) > 0 for row in leaders):
        errors.append("LEADER_WRONG")
    if predicted_themes:
        top = predicted_themes[0]
        if (theme_returns[5].get(top) or 0) < 0 and (theme_returns[20].get(top) or 0) > 0:
            errors.append("TIMING_WRONG")
    has_risk = bool(prediction.get("risk_points"))
    if not has_risk and max_drawdown is not None and max_drawdown <= -0.10:
        errors.append("RISK_IGNORED")
    return sorted(set(errors))


def _style_rank(day: pd.DataFrame, value_column: str) -> list[dict[str, Any]]:
    code = day["ts_code"].astype(str)
    close = day["close"]
    median = close.median()
    masks = {
        "GROWTH_BOARD": code.str.startswith(("300", "301", "688")),
        "MAIN_BOARD": ~code.str.startswith(("300", "301", "688")),
        "HIGH_PRICE": close >= median,
        "LOW_PRICE": close < median,
    }
    rows = []
    for style, mask in masks.items():
        values = day.loc[mask, value_column].dropna()
        if not values.empty:
            rows.append(
                {
                    "style": style,
                    "strength": round(float(values.mean()), 8),
                    "sample_count": len(values),
                }
            )
    return sorted(rows, key=lambda row: row["strength"], reverse=True)


def _theme_result(
    values: dict[str, float], predicted: list[str], actual_top: str | None
) -> dict[str, Any]:
    return {
        "predicted": {theme: values.get(theme) for theme in predicted},
        "actual_top": actual_top,
        "predicted_top1_is_actual_top1": bool(
            predicted and actual_top and predicted[0] == actual_top
        ),
        "actual_top1_in_predicted_top3": bool(actual_top and actual_top in predicted[:3]),
    }


def _stock_summary(row: pd.Series, score_column: str = "leader_score") -> dict[str, Any]:
    return {
        "ts_code": row["ts_code"],
        "stock_name": row.get("stock_name"),
        "industry": row["industry"],
        "score": _number(row.get(score_column)),
        "pct_chg": _number(row.get("pct_chg")),
        "amount": _number(row.get("amount")),
    }


def _result(row: pd.Series) -> dict[str, Any]:
    return {
        "ts_code": row["ts_code"],
        "stock_name": row.get("stock_name"),
        "industry": row["industry"],
        "return_5d": _number(row.get("return_5d")),
        "return_10d": _number(row.get("return_10d")),
        "return_20d": _number(row.get("return_20d")),
        "max_gain": _number(row.get("future_max_gain_20d")),
        "max_drawdown": _number(row.get("future_max_drawdown_20d")),
    }


def _clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _number(item) if isinstance(item, (float, np.floating)) else item
        for key, item in value.items()
    }


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
        return round(parsed, 8) if np.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "value": round(numerator / denominator, 6) if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }
