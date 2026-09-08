from __future__ import annotations

import json
from datetime import date

from src.feedback.forward import advance_feedback
from src.storage.fact_store import FactStore


def test_waiting_feedback_advances_when_next_trading_day_facts_arrive(tmp_path):
    context_dir = tmp_path / "data" / "review_context"
    context_dir.mkdir(parents=True)
    context = {
        "meta": {"trade_date": "2026-09-07"},
        "next_day_theme_candidates": [{"theme": "测试主题"}],
        "core_theme_roles": [],
        "next_day_plan": [],
        "inflection_candidates": [],
        "risk_and_falsification_candidates": [],
        "market_cycle_and_style": {"style_strength": []},
        "data_quality": {"status": "PARTIAL"},
    }
    (context_dir / "2026-09-07.json").write_text(json.dumps(context), encoding="utf-8")
    facts = FactStore(tmp_path / "data" / "facts")
    base = {
        "ts_code": "000001.SZ",
        "open": 10.0,
        "high": 10.2,
        "low": 9.9,
        "close": 10.0,
    }
    facts.write_dataset("stock_daily_ohlcv", date(2026, 9, 7), [base | {"trade_date": "2026-09-07"}])
    first = advance_feedback(tmp_path, date(2026, 9, 7))
    assert first["still_waiting_count"] == 1

    facts.write_dataset(
        "stock_daily_ohlcv",
        date(2026, 9, 8),
        [base | {"trade_date": "2026-09-08", "close": 10.1}],
    )
    second = advance_feedback(tmp_path, date(2026, 9, 8))
    assert second["newly_validated_count"] == 1
    assert second["still_waiting_count"] == 0
    validation = json.loads(
        (tmp_path / "data" / "feedback_records" / "2026-09-07" / "validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert validation["meta"]["status"] == "PARTIAL_FORWARD_WINDOW"
    assert validation["meta"]["available_horizons"] == [1]

    backward = advance_feedback(tmp_path, date(2026, 9, 7))
    retained = json.loads(
        (tmp_path / "data" / "feedback_records" / "2026-09-07" / "validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert backward["newly_validated_count"] == 0
    assert retained["meta"]["status"] == "PARTIAL_FORWARD_WINDOW"
    assert retained["meta"]["available_horizons"] == [1]

    repeated = advance_feedback(tmp_path, date(2026, 9, 8))
    assert repeated["newly_validated_count"] == 0
