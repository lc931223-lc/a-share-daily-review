import json
from datetime import date, datetime, UTC
from pathlib import Path

import pytest

from src.market_packet.collector import CollectedDataset
from src.market_packet.empty_verification import verify_empty_limit_down
from src.market_packet.trading_calendar import TradingCalendarDay
from src.formal_review.persistence import import_record, load_previous_formal, import_inbox
from src.formal_review.support import _factor_evaluation, validate_formal_hypotheses
from src.formal_review.support import build_formal_review_support
from src.formal_review.evidence_domains import score_components, market_evidence, identity

DAY = date(2026, 9, 8)


def dataset(name, rows, quality="PASS"):
    return CollectedDataset(name, "test", DAY, datetime.now(UTC), rows, quality, "historical", False)


def test_empty_valid_limit_down_requires_independent_daily_verification():
    values = {"limit_down": dataset("limit_down", [], "FAIL"), "tushare_daily_all": dataset("daily", [{"ts_code": "600001.SH", "trade_date": "20260908", "pre_close": 10, "close": 10}])}
    verify_empty_limit_down(values, DAY, minimum_rows=1)
    assert values["limit_down"].quality == "EMPTY_VALID"
    values["tushare_daily_all"] = dataset("daily", [{"ts_code": "600001.SH", "trade_date": "20260908", "pre_close": 10, "close": 9}])
    verify_empty_limit_down(values, DAY, minimum_rows=1)
    assert values["limit_down"].quality == "UNAVAILABLE"
    assert values["limit_down"].error_type == "SOURCE_FAILURE"


def test_source_failure_is_not_a_valid_empty_set():
    values = {"limit_down": dataset("limit_down", [], "FAIL")}
    verify_empty_limit_down(values, DAY)
    assert values["limit_down"].quality == "UNAVAILABLE"


def test_short_window_and_confirmation_are_available_without_five_days():
    scores = score_components({"strength_change_1d": 2, "change_pct": 1, "amount": 100}, _factor_evaluation([]))["components"]
    assert scores["continuity"]["window_available"] == 1
    assert scores["continuity"]["available_score"] == 2
    assert scores["market_confirmation"]["available_score"] == 5
    assert scores["expectation_gap"]["reason"] == "NO_EXPECTATION_BASELINE"


def test_market_breakout_evidence_cannot_confirm_an_order():
    context = {"inflection_candidates": [{"themes": ["元件"], "ts_code": "600001.SH", "breakout": {"hold_status": "BREAKOUT_HELD", "volume_confirmation": "HIGH_VOLUME_CONFIRMED", "failure": False}}]}
    _, evidence = market_evidence({"theme": "元件"}, context, {}, DAY)
    factors = _factor_evaluation(evidence)
    assert factors[35]["status"] == "CONFIRMED"
    assert factors[18]["status"] == "UNCONFIRMED"


def test_parent_child_is_not_an_alias():
    assert identity("农化")["canonical_name"] == "农化制品"
    assert identity("草甘膦")["parent"] == "农化制品"
    assert identity("草甘膦")["canonical_name"] != identity("农化")["canonical_name"]


def formal_payload():
    return {"schema_version": "formal_review.3", "date": "2026-09-07", "previous_trade_date": "2026-09-04", "final_judgement_owner": "chatgpt", "market_overview": {}, "market_regime": "test", "main_themes": [], "changes_vs_previous_day": {k: [] for k in ("new", "strengthened", "weakened", "diffused", "realized", "falsified")}, "previous_day_validation": {"records": [], "prediction_count": 0, "confirmed_count": 0, "partial_count": 0, "failed_count": 0, "not_evaluable_count": 0, "hit_rate": None, "weighted_hit_rate": None}, "uncertainties": []}


def test_formal_inbox_exact_day_idempotency_and_sha(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    source = Path(__file__).resolve().parents[2] / "schemas/formal_review_record.schema.json"
    (schema_dir / source.name).write_bytes(source.read_bytes())
    days = [TradingCalendarDay(date(2026, 9, n), True) for n in (4, 7, 8)]
    assert load_previous_formal(tmp_path, DAY, days)[1]["status"] == "PREVIOUS_FORMAL_REVIEW_UNAVAILABLE"
    inbox = tmp_path / "data/formal_review_inbox"
    inbox.mkdir(parents=True)
    (inbox / "review.json").write_text(json.dumps(formal_payload()), encoding="utf-8")
    result = import_inbox(tmp_path, days)[0]
    assert result["status"] == "IMPORTED" and len(result["sha256"]) == 64
    assert import_inbox(tmp_path, days)[0]["status"] == "UNCHANGED"
    assert load_previous_formal(tmp_path, DAY, days)[0]["date"] == "2026-09-07"
    with pytest.raises(ValueError, match="immutable"):
        import_record(tmp_path, formal_payload() | {"market_regime": "changed"}, days)


def test_objective_support_never_enters_formal_hit_rate():
    support = {"theme_support": [{"next_day_validation": [{"validation_point": "up"}]}]}
    result = validate_formal_hypotheses(support, {})
    assert result["prediction_count"] == 0
    assert result["hit_rate"] is None


def test_formal_predicate_uses_actual_condition_not_price_direction():
    formal = {"main_themes": [{"theme_name": "元件", "next_day_validation": [{"validation_point": "amount >=100", "predicate": {"field": "amount", "operator": "gte", "threshold": 100}}]}]}
    market = {"meta": {"trade_date": "2026-09-08"}, "themes": [{"theme_name": "元件", "amount": 90, "change_pct": 9}]}
    result = validate_formal_hypotheses(formal, {}, market)
    assert result["failed_count"] == 1
    assert result["hit_rate"] == 0


def test_hard_gate_failure_propagates_to_support(tmp_path):
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    source = Path(__file__).resolve().parents[2] / "schemas/formal_review_support.schema.json"
    (schemas / source.name).write_bytes(source.read_bytes())
    for folder, quality in (("market_packets", "FAIL"), ("review_context", "PARTIAL")):
        path = tmp_path / "data" / folder
        path.mkdir(parents=True)
        (path / "2026-09-08.json").write_text(json.dumps({"meta": {"trade_date": "2026-09-08"}, "data_quality": {"status": quality}}), encoding="utf-8")
    reference = tmp_path / "data/reference"
    reference.mkdir()
    (reference / "trade_calendar_2026.json").write_text(json.dumps({"rows": [{"cal_date": "20260907", "is_open": 1}, {"cal_date": "20260908", "is_open": 1}]}), encoding="utf-8")
    packet = build_formal_review_support(tmp_path, DAY)["packet"]
    assert packet["data_quality"]["status"] == "PARTIAL_WITH_UPSTREAM_FAILURE"
    assert packet["previous_day_validation"]["hit_rate"] is None


def test_sparse_files_are_not_five_trading_days(tmp_path, monkeypatch):
    from src.review_intelligence.pipeline import ReviewIntelligencePipeline
    folder = tmp_path / "data/review_intelligence"
    folder.mkdir(parents=True)
    for day in (1, 2, 3, 4, 7):
        (folder / f"2026-09-{day:02}.json").write_text(json.dumps({"theme_features": [{"theme_name": "test", "theme_inflection_score": day}]}), encoding="utf-8")
    days = [TradingCalendarDay(date(2026, 9, n), True) for n in (1, 2, 3, 4, 7, 8)]
    monkeypatch.setattr("src.review_intelligence.pipeline.load_trading_calendar", lambda *a, **k: days)
    states = ReviewIntelligencePipeline(tmp_path)._previous_states(date(2026, 9, 9))
    assert states["theme_1d"] == {}
    assert states["theme_5d"]["test"] == 2


def test_no_fundamental_evidence_is_unavailable_not_zero():
    components = score_components({}, [])['components']
    assert components['base_logic']['raw_score'] is None
    assert components['base_logic']['available_score'] == 0
