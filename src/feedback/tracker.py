from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import ReviewPredictionRecord, ReviewValidationResult


def prediction_from_official_review(
    payload: dict[str, Any], path: Path | None = None
) -> dict[str, Any]:
    prediction_date = str(payload.get("date") or "")[:10]
    if not prediction_date:
        raise ValueError("official_review date is required")
    themes = _list(payload.get("main_themes"))
    stocks = _list(payload.get("stocks"))
    leaders = [
        row
        for row in stocks
        if str(row.get("role") or "") in {"龙头", "中军", "补涨", "趋势龙头", "弹性"}
    ]
    completeness = payload.get("completeness")
    completeness_score = (
        completeness.get("score") if isinstance(completeness, dict) else completeness
    )
    commentary = " ".join(str(item) for item in _list(payload.get("market_commentary")))
    is_simulated = "模拟" in commentary or str(payload.get("data_kind") or "").lower() in {
        "demo",
        "sample",
    }
    confidence = (
        "LOW"
        if is_simulated
        else "HIGH"
        if isinstance(completeness_score, (int, float)) and completeness_score >= 90
        else "MEDIUM"
        if isinstance(completeness_score, (int, float)) and completeness_score >= 70
        else "LOW"
    )
    digest = _digest(payload)
    return {
        "prediction_date": prediction_date,
        "source_review": f"official_review:{digest[:16]}",
        "source_path": str(path) if path else None,
        "theme_prediction": themes,
        "style_prediction": _list(payload.get("sector_strength"))
        + _list(payload.get("sentiment_dashboard")),
        "leader_candidates": leaders,
        "next_day_plan": _list(payload.get("tomorrow_plan")),
        "inflection_candidates": [row for row in stocks if "拐点" in str(row.get("stage") or "")],
        "risk_points": _list(payload.get("risk_events")),
        "confidence_level": confidence,
        "record_kind": "SIMULATED_OFFICIAL_REVIEW" if is_simulated else "FORMAL_OFFICIAL_REVIEW",
    }


def prediction_from_review_context(
    payload: dict[str, Any], path: Path | None = None
) -> dict[str, Any]:
    meta = payload.get("meta") or {}
    prediction_date = str(meta.get("trade_date") or "")[:10]
    if not prediction_date:
        raise ValueError("review_context trade_date is required")
    themes = payload.get("next_day_theme_candidates") or []
    roles = payload.get("core_theme_roles") or []
    leaders = []
    for row in roles:
        for role in (
            "leader_candidate",
            "capacity_candidate",
            "trend_leader",
            "elasticity",
            "catch_up",
        ):
            candidate = row.get(role)
            if candidate:
                leaders.append({"theme": row.get("theme"), "role": role, "candidate": candidate})
    quality = payload.get("data_quality") or {}
    digest = _digest(payload)
    return {
        "prediction_date": prediction_date,
        "source_review": f"review_context:{digest[:16]}",
        "source_path": str(path) if path else None,
        "theme_prediction": themes,
        "style_prediction": (payload.get("market_cycle_and_style") or {}).get("style_strength")
        or [],
        "leader_candidates": leaders,
        "next_day_plan": payload.get("next_day_plan") or [],
        "inflection_candidates": payload.get("inflection_candidates") or [],
        "risk_points": payload.get("risk_and_falsification_candidates") or [],
        "confidence_level": _confidence(quality),
        "record_kind": "OBJECTIVE_REVIEW_CONTEXT",
    }


def persist_predictions(database_path: Path, predictions: list[dict[str, Any]]) -> dict[str, int]:
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    inserted = updated = 0
    with factory.begin() as session:
        for item in predictions:
            prediction_date = date.fromisoformat(str(item["prediction_date"])[:10])
            source = str(item["source_review"])
            record = session.scalar(
                select(ReviewPredictionRecord).where(
                    ReviewPredictionRecord.prediction_date == prediction_date,
                    ReviewPredictionRecord.source_review == source,
                )
            )
            values = {
                "theme_prediction": _json(item.get("theme_prediction") or []),
                "style_prediction": _json(item.get("style_prediction") or []),
                "leader_candidates": _json(item.get("leader_candidates") or []),
                "next_day_plan": _json(item.get("next_day_plan") or []),
                "inflection_candidates": _json(item.get("inflection_candidates") or []),
                "risk_points": _json(item.get("risk_points") or []),
                "confidence_level": str(item.get("confidence_level") or "LOW"),
            }
            if record is None:
                session.add(
                    ReviewPredictionRecord(
                        prediction_date=prediction_date,
                        source_review=source,
                        **values,
                    )
                )
                inserted += 1
            else:
                for key, value in values.items():
                    setattr(record, key, value)
                updated += 1
    engine.dispose()
    return {"inserted": inserted, "updated": updated}


def persist_validations(database_path: Path, validations: list[dict[str, Any]]) -> dict[str, int]:
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    inserted = updated = skipped = 0
    with factory.begin() as session:
        for item in validations:
            prediction = session.scalar(
                select(ReviewPredictionRecord).where(
                    ReviewPredictionRecord.prediction_date
                    == date.fromisoformat(item["prediction_date"]),
                    ReviewPredictionRecord.source_review == item["source_review"],
                )
            )
            if prediction is None:
                skipped += 1
                continue
            validation_date = date.fromisoformat(item["validation_date"])
            record = session.scalar(
                select(ReviewValidationResult).where(
                    ReviewValidationResult.prediction_id == prediction.id,
                    ReviewValidationResult.validation_date == validation_date,
                )
            )
            values = {
                "actual_market_state": _json(item.get("actual_market_state") or {}),
                "actual_theme_result": _json(item.get("actual_theme_result") or {}),
                "theme_return_5d": _json(item.get("theme_return_5d") or {}),
                "theme_return_10d": _json(item.get("theme_return_10d") or {}),
                "theme_return_20d": _json(item.get("theme_return_20d") or {}),
                "leader_result": _json(item.get("leader_result") or []),
                "stock_result": _json(item.get("stock_result") or []),
                "max_gain": item.get("max_gain"),
                "max_drawdown": item.get("max_drawdown"),
                "error_type": _json(item.get("error_type") or []),
            }
            if record is None:
                session.add(
                    ReviewValidationResult(
                        validation_date=validation_date,
                        prediction_id=prediction.id,
                        **values,
                    )
                )
                inserted += 1
            else:
                for key, value in values.items():
                    setattr(record, key, value)
                updated += 1
    engine.dispose()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def _confidence(quality: dict[str, Any]) -> str:
    status = str(quality.get("status") or "").upper()
    return "HIGH" if status == "PASS" else "MEDIUM" if status == "PARTIAL" else "LOW"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
