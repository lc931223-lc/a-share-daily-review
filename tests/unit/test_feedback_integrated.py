from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from src.feedback.integrated import (
    build_correction_record,
    build_integrated_prediction,
    build_review_record,
    validate_integrated_prediction,
)

TARGET = date(2026, 9, 4)


def _write_sources(root, *, mismatched_market: bool = False):
    payloads = {
        "market_packets": {
            "meta": {"trade_date": "2026-09-03" if mismatched_market else "2026-09-04"},
            "market_overview": {"rise_count": 3000},
            "market_breadth": {},
            "liquidity": {},
            "limit_up_down": {},
            "data_quality": {"status": "PASS"},
        },
        "review_intelligence": {
            "meta": {"trade_date": "2026-09-04"},
            "theme_features": [{"theme_name": "算力"}],
            "style_strength_ranking": [{"style": "growth"}],
            "role_candidates": [
                {"ts_code": "000001.SZ", "theme": "算力", "role_candidate": "LEADER_CANDIDATE"}
            ],
            "next_day_plan_candidates": [{"ts_code": "000001.SZ", "theme": "算力"}],
            "risk_and_falsification_candidates": [],
            "data_quality": {"status": "PASS"},
        },
        "inflection": {
            "meta": {"trade_date": "2026-09-04"},
            "scan_summary": {},
            "candidates": [{"ts_code": "000002.SZ", "status": "INFLECTION_CONFIRMED"}],
            "data_quality": {"status": "PASS"},
        },
        "auction_packets": {
            "meta": {"trade_date": "2026-09-04"},
            "market_auction_summary": {},
            "stock_auction_summary": [{"ts_code": "000001.SZ"}],
            "volume_anomaly_candidates": [],
            "objective_analysis": {},
            "conflicts": [],
            "data_quality": {"status": "PASS"},
        },
        "official_reviews": {
            "date": "2026-09-04",
            "data_kind": "real",
            "completeness": {"score": 95},
            "main_themes": [{"name": "算力"}],
            "stocks": [{"code": "000001", "theme": "算力", "role": "龙头"}],
            "tomorrow_plan": [{"item": "算力"}],
            "risk_events": [],
        },
    }
    for folder, payload in payloads.items():
        path = root / "data" / folder / "2026-09-04.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _daily(periods: int = 25):
    rows = []
    dates = [pd.Timestamp("2026-09-04"), *pd.bdate_range("2026-09-07", periods=periods)]
    for index, timestamp in enumerate(dates):
        for code, slope in (("000001.SZ", 0.02), ("000002.SZ", 0.01), ("600001.SH", -0.002)):
            close = 10 * (1 + slope * index)
            rows.append(
                {
                    "trade_date": timestamp.date().isoformat(),
                    "ts_code": code,
                    "close": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                }
            )
    return pd.DataFrame(rows)


def test_integrated_cycle_preserves_five_sources_and_disables_auto_changes(tmp_path):
    _write_sources(tmp_path)
    prediction = build_integrated_prediction(tmp_path, TARGET)
    assert set(prediction["source_manifest"]) == {
        "market_packet",
        "review_intelligence",
        "inflection_scanner",
        "auction_packet",
        "official_review",
    }
    assert prediction["meta"]["new_analysis_generated"] is False
    assert prediction["normalized_prediction_record"]["source_review"].startswith(
        "integrated_stack:"
    )
    validation = validate_integrated_prediction(tmp_path, prediction, _daily())
    review = build_review_record(tmp_path, prediction, validation)
    correction = build_correction_record(tmp_path, prediction, validation, review)
    assert validation["meta"]["status"] == "VALIDATED_20D"
    assert validation["leader_result"][0]["return_5d"] > 0
    assert correction["model_change_applied"] is False
    assert correction["weight_change_applied"] is False
    assert review["meta"]["status"] == "REVIEWED"
    for name in ("prediction.json", "validation.json", "review.json", "correction.json"):
        assert (tmp_path / "data" / "feedback_records" / "2026-09-04" / name).is_file()


def test_integrated_prediction_rejects_cross_date_source(tmp_path):
    _write_sources(tmp_path, mismatched_market=True)
    with pytest.raises(ValueError, match="market_packet date mismatch"):
        build_integrated_prediction(tmp_path, TARGET)


def test_integrated_validation_waits_without_future_market_data(tmp_path):
    _write_sources(tmp_path)
    prediction = build_integrated_prediction(tmp_path, TARGET)
    validation = validate_integrated_prediction(tmp_path, prediction, _daily(periods=0))
    assert validation["meta"]["status"] == "WAITING_FOR_MARKET_DATA"
    assert validation["meta"]["validation_date"] is None
