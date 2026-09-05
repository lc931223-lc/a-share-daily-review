from __future__ import annotations

import json

from sqlalchemy import func, select

from src.feedback.tracker import (
    persist_predictions,
    persist_validations,
    prediction_from_official_review,
    prediction_from_review_context,
)
from src.storage.database import create_db_engine, session_factory
from src.storage.models import ReviewPredictionRecord, ReviewValidationResult


def _context():
    return {
        "meta": {"trade_date": "2026-09-04"},
        "next_day_theme_candidates": [{"theme": "机器人"}],
        "market_cycle_and_style": {"style_strength": [{"style": "成长"}]},
        "core_theme_roles": [{"theme": "机器人", "leader_candidate": {"ts_code": "000001.SZ"}}],
        "next_day_plan": [{"ts_code": "000001.SZ"}],
        "inflection_candidates": [{"ts_code": "000002.SZ"}],
        "risk_and_falsification_candidates": [{"type": "风险"}],
        "data_quality": {"status": "PARTIAL"},
    }


def test_prediction_and_validation_are_idempotent(tmp_path):
    database = tmp_path / "feedback.db"
    prediction = prediction_from_review_context(_context())
    assert prediction["confidence_level"] == "MEDIUM"
    persist_predictions(database, [prediction])
    persist_predictions(database, [prediction])
    validation = {
        "prediction_date": "2026-09-04",
        "source_review": prediction["source_review"],
        "validation_date": "2026-09-11",
        "actual_market_state": {"state": "MIXED"},
        "actual_theme_result": {},
        "theme_return_5d": {},
        "theme_return_10d": {},
        "theme_return_20d": {},
        "leader_result": [],
        "stock_result": [],
        "max_gain": None,
        "max_drawdown": None,
        "error_type": ["DATA_LIMITATION"],
    }
    persist_validations(database, [validation])
    persist_validations(database, [validation])
    factory = session_factory(create_db_engine(database))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ReviewPredictionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ReviewValidationResult)) == 1
        stored = session.scalar(select(ReviewPredictionRecord))
        assert json.loads(stored.theme_prediction)[0]["theme"] == "机器人"


def test_official_review_is_labeled_as_formal():
    record = prediction_from_official_review(
        {
            "date": "2026-09-04",
            "completeness": 92,
            "main_themes": [{"name": "算力"}],
            "stocks": [{"code": "300308", "role": "中军"}],
            "tomorrow_plan": [{"item": "算力"}],
            "risk_events": [],
        }
    )
    assert record["record_kind"] == "FORMAL_OFFICIAL_REVIEW"
    assert record["source_review"].startswith("official_review:")
    assert record["confidence_level"] == "HIGH"


def test_simulated_official_review_is_not_labeled_as_formal():
    record = prediction_from_official_review(
        {
            "date": "2026-09-04",
            "completeness": {"score": 95},
            "market_commentary": ["这是模拟输出"],
        }
    )
    assert record["record_kind"] == "SIMULATED_OFFICIAL_REVIEW"
    assert record["confidence_level"] == "LOW"
