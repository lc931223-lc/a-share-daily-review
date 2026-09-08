from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.feedback.tracker import prediction_from_official_review

COMPONENT_PATHS = {
    "market_packet": "market_packets",
    "review_intelligence": "review_intelligence",
    "inflection_scanner": "inflection",
    "auction_packet": "auction_packets",
    "official_review": "official_reviews",
}
HORIZONS = (1, 5, 10, 20)
INFLECTION_FIELDS = (
    "trade_date",
    "ts_code",
    "stock_name",
    "industry",
    "themes",
    "status",
    "trend_inflection_score",
    "fundamental_inflection_score",
    "price_volume_score",
    "daily_structure_score",
    "weekly_trend_score",
    "chip_structure_score",
    "breakout_type",
    "breakout_hold_status",
    "weekly_breakout_type",
    "distribution_warning",
    "main_catalyst",
    "catalyst_stage",
    "evidence_level",
    "risk_flags",
    "why_selected",
)
AUCTION_FIELDS = (
    "trade_date",
    "ts_code",
    "stock_name",
    "auction_gap_pct",
    "auction_amount",
    "auction_amount_ratio_20d",
    "auction_amount_percentile_60d",
    "post_0920_amount_growth",
    "last_2min_amount_growth",
    "auction_volume_anomaly_score",
    "anomaly_labels",
    "open_price_error_pct",
    "conflict_status",
    "quality_status",
)


def build_integrated_prediction(root: Path, target: date) -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {}
    manifest: dict[str, dict[str, Any]] = {}
    for component, folder in COMPONENT_PATHS.items():
        path = root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            raise FileNotFoundError(f"{component} is unavailable: {path}")
        payload = _read(path)
        actual_date = _payload_date(payload)
        if actual_date != target.isoformat():
            raise ValueError(
                f"{component} date mismatch: expected {target.isoformat()}, got {actual_date}"
            )
        payloads[component] = payload
        manifest[component] = {
            "trade_date": actual_date,
            "path": path.relative_to(root).as_posix(),
            "sha256": _digest(payload),
            "quality_status": _quality(payload),
        }

    official = prediction_from_official_review(
        payloads["official_review"],
        root / "data" / "official_reviews" / f"{target.isoformat()}.json",
    )
    intelligence = payloads["review_intelligence"]
    inflection = payloads["inflection_scanner"]
    auction = payloads["auction_packet"]
    inflection_candidates = _project(inflection.get("candidates") or [], INFLECTION_FIELDS, 100)
    auction_summaries = _project(auction.get("stock_auction_summary") or [], AUCTION_FIELDS, 200)
    auction_anomalies = _project(
        auction.get("volume_anomaly_candidates") or [], AUCTION_FIELDS, 100
    )
    review_kind = official["record_kind"]
    status = "READY" if review_kind == "FORMAL_OFFICIAL_REVIEW" else "SIMULATED_REVIEW_ONLY"
    source_review = f"integrated_stack:{_digest(manifest)[:16]}"
    normalized = {
        "prediction_date": target.isoformat(),
        "source_review": source_review,
        "theme_prediction": _tag(official["theme_prediction"], "official_review")
        + _tag((intelligence.get("theme_features") or [])[:20], "review_intelligence"),
        "style_prediction": _tag(official["style_prediction"], "official_review")
        + _tag(
            (intelligence.get("style_strength_ranking") or [])[:20],
            "review_intelligence",
        ),
        "leader_candidates": _tag(official["leader_candidates"], "official_review")
        + _tag((intelligence.get("role_candidates") or [])[:50], "review_intelligence"),
        "next_day_plan": _tag(official["next_day_plan"], "official_review")
        + _tag(
            (intelligence.get("next_day_plan_candidates") or [])[:20],
            "review_intelligence",
        ),
        "inflection_candidates": _tag(inflection_candidates, "inflection_scanner"),
        "risk_points": _tag(official["risk_points"], "official_review")
        + _tag(
            intelligence.get("risk_and_falsification_candidates") or [],
            "review_intelligence",
        )
        + _tag(auction.get("conflicts") or [], "auction_packet"),
        "confidence_level": official["confidence_level"],
        "record_kind": "INTEGRATED_RESEARCH_STACK",
    }
    packet = {
        "meta": {
            "schema_version": "integrated_prediction.1",
            "prediction_date": target.isoformat(),
            "status": status,
            "source_review": source_review,
            "official_review_kind": review_kind,
            "final_judgement_owner": "official_review",
            "new_analysis_generated": False,
        },
        "source_manifest": manifest,
        "market_baseline": {
            "market_overview": payloads["market_packet"].get("market_overview") or {},
            "market_breadth": payloads["market_packet"].get("market_breadth") or {},
            "liquidity": payloads["market_packet"].get("liquidity") or {},
            "limit_up_down": payloads["market_packet"].get("limit_up_down") or {},
        },
        "official_review": official,
        "review_intelligence": {
            "market_operability": intelligence.get("market_operability") or {},
            "cycle_candidates": intelligence.get("cycle_candidates") or [],
            "style_strength_ranking": intelligence.get("style_strength_ranking") or [],
            "theme_features": intelligence.get("theme_features") or [],
            "role_candidates": intelligence.get("role_candidates") or [],
            "next_day_plan_candidates": intelligence.get("next_day_plan_candidates") or [],
            "risk_and_falsification_candidates": intelligence.get(
                "risk_and_falsification_candidates"
            )
            or [],
        },
        "inflection": {
            "scan_summary": inflection.get("scan_summary") or {},
            "candidates": inflection_candidates,
        },
        "auction": {
            "market_auction_summary": auction.get("market_auction_summary") or {},
            "stock_auction_summary": auction_summaries,
            "volume_anomaly_candidates": auction_anomalies,
            "objective_analysis": auction.get("objective_analysis") or {},
            "conflicts": auction.get("conflicts") or [],
        },
        "normalized_prediction_record": normalized,
    }
    _write(root, target, "prediction.json", packet)
    return packet


def validate_integrated_prediction(
    root: Path, packet: dict[str, Any], daily: pd.DataFrame
) -> dict[str, Any]:
    prediction_date = packet["meta"]["prediction_date"]
    frame = daily.copy()
    if not frame.empty:
        frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
        frame["ts_code"] = frame["ts_code"].astype(str)
        frame = frame.sort_values(["ts_code", "trade_date"])
    future_dates = sorted(
        value
        for value in frame.get("trade_date", pd.Series(dtype=str)).unique()
        if value > prediction_date
    )
    available_horizons = [horizon for horizon in HORIZONS if len(future_dates) >= horizon]
    normalized = packet["normalized_prediction_record"]
    leaders = _codes(normalized["leader_candidates"])
    inflections = _codes(normalized["inflection_candidates"])
    auction_codes = _codes(packet["auction"]["stock_auction_summary"])
    plan_codes = _codes(normalized["next_day_plan"])
    all_codes = sorted(leaders | inflections | auction_codes | plan_codes)
    stock_results = (
        _stock_results(frame, prediction_date, all_codes, available_horizons)
        if available_horizons
        else []
    )
    by_code = {row["ts_code"]: row for row in stock_results}
    leader_results = [by_code[code] for code in sorted(leaders) if code in by_code]
    inflection_results = [by_code[code] for code in sorted(inflections) if code in by_code]
    auction_results = [by_code[code] for code in sorted(auction_codes) if code in by_code]
    market_state = _market_results(frame, prediction_date, available_horizons)
    theme_results = _theme_results(normalized, by_code, available_horizons)
    max_gain = max(
        (row["max_gain"] for row in stock_results if row.get("max_gain") is not None),
        default=None,
    )
    max_drawdown = min(
        (row["max_drawdown"] for row in stock_results if row.get("max_drawdown") is not None),
        default=None,
    )
    errors = _validation_errors(
        packet, available_horizons, leader_results, theme_results, max_drawdown
    )
    status = (
        "WAITING_FOR_MARKET_DATA"
        if not available_horizons
        else "VALIDATED_20D"
        if 20 in available_horizons
        else "PARTIAL_FORWARD_WINDOW"
    )
    validation_date = future_dates[max(available_horizons) - 1] if available_horizons else None
    result = {
        "meta": {
            "schema_version": "integrated_validation.1",
            "prediction_date": prediction_date,
            "validation_date": validation_date,
            "status": status,
            "available_horizons": available_horizons,
            "source_review": packet["meta"]["source_review"],
        },
        "actual_market_state": market_state,
        "actual_theme_result": theme_results,
        "theme_return_5d": _horizon_theme(theme_results, 5),
        "theme_return_10d": _horizon_theme(theme_results, 10),
        "theme_return_20d": _horizon_theme(theme_results, 20),
        "leader_result": leader_results,
        "inflection_result": inflection_results,
        "auction_result": {
            "source_validation": packet["auction"].get("conflicts") or [],
            "stock_results": auction_results,
        },
        "stock_result": stock_results,
        "max_gain": max_gain,
        "max_drawdown": max_drawdown,
        "error_type": errors,
    }
    _write(root, date.fromisoformat(prediction_date), "validation.json", result)
    return result


def build_review_record(
    root: Path, prediction: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any]:
    errors = validation.get("error_type") or []
    status = (
        "WAITING_FOR_VALIDATION"
        if validation["meta"]["status"] == "WAITING_FOR_MARKET_DATA"
        else "PARTIAL_REVIEW"
        if validation["meta"]["status"] == "PARTIAL_FORWARD_WINDOW"
        else "REVIEWED"
    )
    correct = []
    incorrect = []
    if status != "WAITING_FOR_VALIDATION" and 5 in validation["meta"].get("available_horizons", []):
        if "LEADER_WRONG" not in errors:
            correct.append("Existing leader candidates include a positive five-day result.")
        if "THEME_WRONG" not in errors:
            correct.append(
                "Evaluable existing theme candidate baskets are not negative at five days."
            )
        incorrect = [error for error in errors if error != "DATA_LIMITATION"]
    result = {
        "meta": {
            "schema_version": "integrated_feedback_review.1",
            "prediction_date": prediction["meta"]["prediction_date"],
            "status": status,
        },
        "correct_parts": correct,
        "incorrect_parts": incorrect,
        "error_type": errors,
        "actual_market_state": validation.get("actual_market_state") or {},
        "actual_theme_result": validation.get("actual_theme_result") or [],
    }
    _write(
        root,
        date.fromisoformat(prediction["meta"]["prediction_date"]),
        "review.json",
        result,
    )
    return result


def build_correction_record(
    root: Path,
    prediction: dict[str, Any],
    validation: dict[str, Any],
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = validation.get("error_type") or []
    result = {
        "meta": {
            "schema_version": "integrated_correction.1",
            "prediction_date": prediction["meta"]["prediction_date"],
            "status": "WAITING_FOR_REVIEW"
            if validation["meta"]["status"] == "WAITING_FOR_MARKET_DATA"
            else "ERRORS_RECORDED",
        },
        "review_status": (review or {}).get("meta", {}).get("status"),
        "registered_error_types": errors,
        "data_limitations": [
            "Style and cycle conclusions are not reverse-engineered when no existing point-in-time validator is available."
        ]
        if "DATA_LIMITATION" in errors
        else [],
        "model_change_applied": False,
        "weight_change_applied": False,
        "automatic_recommendation_generated": False,
    }
    _write(
        root,
        date.fromisoformat(prediction["meta"]["prediction_date"]),
        "correction.json",
        result,
    )
    return result


def validation_for_storage(
    prediction: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any] | None:
    validation_date = validation["meta"].get("validation_date")
    if validation_date is None:
        return None
    return {
        "prediction_date": prediction["meta"]["prediction_date"],
        "source_review": prediction["meta"]["source_review"],
        "validation_date": validation_date,
        "actual_market_state": validation["actual_market_state"],
        "actual_theme_result": validation["actual_theme_result"],
        "theme_return_5d": validation["theme_return_5d"],
        "theme_return_10d": validation["theme_return_10d"],
        "theme_return_20d": validation["theme_return_20d"],
        "leader_result": validation["leader_result"],
        "stock_result": validation["stock_result"],
        "max_gain": validation["max_gain"],
        "max_drawdown": validation["max_drawdown"],
        "error_type": validation["error_type"],
    }


def _stock_results(
    frame: pd.DataFrame,
    prediction_date: str,
    codes: list[str],
    horizons: list[int],
) -> list[dict[str, Any]]:
    results = []
    for code in codes:
        stock = frame[frame["ts_code"] == code].sort_values("trade_date").reset_index(drop=True)
        matches = stock.index[stock["trade_date"] == prediction_date].tolist()
        if not matches:
            continue
        index = matches[-1]
        entry = _float(stock.loc[index, "close"])
        if entry is None or entry == 0:
            continue
        future = stock.iloc[index + 1 : index + 21]
        row: dict[str, Any] = {"ts_code": code}
        for horizon in HORIZONS:
            row[f"return_{horizon}d"] = (
                _float(stock.loc[index + horizon, "close"] / entry - 1)
                if horizon in horizons and index + horizon < len(stock)
                else None
            )
        row["max_gain"] = (
            _float(pd.to_numeric(future["high"], errors="coerce").max() / entry - 1)
            if not future.empty
            else None
        )
        row["max_drawdown"] = (
            _float(pd.to_numeric(future["low"], errors="coerce").min() / entry - 1)
            if not future.empty
            else None
        )
        results.append(row)
    return results


def _market_results(
    frame: pd.DataFrame, prediction_date: str, horizons: list[int]
) -> dict[str, Any]:
    base = frame[frame["trade_date"] == prediction_date][["ts_code", "close"]].rename(
        columns={"close": "base_close"}
    )
    result = {}
    future_dates = sorted(
        value for value in frame["trade_date"].unique() if value > prediction_date
    )
    for horizon in HORIZONS:
        if horizon not in horizons:
            result[f"return_{horizon}d"] = None
            continue
        future = frame[frame["trade_date"] == future_dates[horizon - 1]][["ts_code", "close"]]
        joined = base.merge(future, on="ts_code")
        values = (
            pd.to_numeric(joined["close"], errors="coerce")
            / pd.to_numeric(joined["base_close"], errors="coerce")
            - 1
        )
        result[f"return_{horizon}d"] = _float(values.mean())
    return result


def _theme_results(
    normalized: dict[str, Any], by_code: dict[str, dict[str, Any]], horizons: list[int]
) -> list[dict[str, Any]]:
    theme_codes: dict[str, set[str]] = {}
    for row in normalized["leader_candidates"] + normalized["next_day_plan"]:
        theme = str(row.get("theme") or row.get("theme_name") or row.get("item") or "").strip()
        code = _code(row)
        if theme and code:
            theme_codes.setdefault(theme, set()).add(code)
    theme_names = []
    for row in normalized["theme_prediction"]:
        name = str(row.get("name") or row.get("theme") or row.get("theme_name") or "").strip()
        if name and name not in theme_names:
            theme_names.append(name)
    output = []
    for theme in theme_names:
        codes = theme_codes.get(theme, set())
        result: dict[str, Any] = {"theme": theme, "candidate_codes": sorted(codes)}
        for horizon in HORIZONS:
            values = [
                by_code[code].get(f"return_{horizon}d")
                for code in codes
                if code in by_code and by_code[code].get(f"return_{horizon}d") is not None
            ]
            result[f"return_{horizon}d"] = (
                _float(sum(values) / len(values)) if horizon in horizons and values else None
            )
        output.append(result)
    return output


def _validation_errors(packet, horizons, leaders, themes, max_drawdown):
    errors = []
    if 5 in horizons:
        leader_returns = [
            row.get("return_5d") for row in leaders if row.get("return_5d") is not None
        ]
        if leader_returns and not any(value > 0 for value in leader_returns):
            errors.append("LEADER_WRONG")
        theme_returns = [row.get("return_5d") for row in themes if row.get("return_5d") is not None]
        if theme_returns and max(theme_returns) < 0:
            errors.append("THEME_WRONG")
        if (
            themes
            and themes[0].get("return_5d") is not None
            and themes[0].get("return_20d") is not None
            and themes[0]["return_5d"] < 0 < themes[0]["return_20d"]
        ):
            errors.append("TIMING_WRONG")
        if (
            not packet["normalized_prediction_record"]["risk_points"]
            and max_drawdown is not None
            and max_drawdown <= -0.10
        ):
            errors.append("RISK_IGNORED")
    if 20 not in horizons or packet["meta"]["status"] != "READY":
        errors.append("DATA_LIMITATION")
    return sorted(set(errors))


def _horizon_theme(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    return {
        row["theme"]: row.get(f"return_{horizon}d")
        for row in rows
        if row.get(f"return_{horizon}d") is not None
    }


def _codes(rows: list[dict[str, Any]]) -> set[str]:
    return {code for row in rows if (code := _code(row))}


def _code(row: dict[str, Any]) -> str | None:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
    value = candidate.get("ts_code") or candidate.get("stock_code") or candidate.get("code")
    code = str(value or "").split(".", 1)[0]
    if len(code) != 6 or not code.isdigit():
        return None
    suffix = (
        "SH" if code.startswith(("5", "6")) else "BJ" if code.startswith(("4", "8", "9")) else "SZ"
    )
    return f"{code}.{suffix}"


def _tag(rows: list[Any], component: str) -> list[dict[str, Any]]:
    return [dict(row, source_component=component) for row in rows if isinstance(row, dict)]


def _project(rows: list[Any], fields: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    return [
        {field: row.get(field) for field in fields} for row in rows[:limit] if isinstance(row, dict)
    ]


def _payload_date(payload: dict[str, Any]) -> str:
    return str(payload.get("date") or (payload.get("meta") or {}).get("trade_date") or "")[:10]


def _quality(payload: dict[str, Any]) -> str | None:
    return (payload.get("data_quality") or {}).get("status")


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
        return round(parsed, 8) if pd.notna(parsed) else None
    except (TypeError, ValueError):
        return None


def _digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(root: Path, target: date, name: str, payload: dict[str, Any]) -> None:
    folder = root / "data" / "feedback_records" / target.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
