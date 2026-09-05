import json
from datetime import date

import pytest

from src.review_context.builder import ReviewContextBuilder


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _inputs(root, *, market_date="2026-09-04"):
    market = {
        "meta": {"trade_date": market_date},
        "market_overview": {"total_market_turnover": 100, "rise_count": 3, "fall_count": 2,
            "limit_up_count": 2, "limit_down_count": 0, "failed_limit_count": 1,
            "seal_rate": 66, "highest_board": 2},
        "limit_up_down": {}, "themes": [], "announcements": {"records": []},
        "previous_review": {"date": "2026-09-03", "themes": [], "stocks": []},
        "tomorrow_check_context": {"checks": [{"description": "check"}],
            "changes_vs_previous_day": {"strengthened": ["A"], "weakened": ["B"], "invalidated": ["C"]}},
        "data_quality": {"status": "PASS"},
    }
    intelligence = {
        "meta": {"trade_date": "2026-09-04"}, "market_operability": {"market_operability_score": 60},
        "cycle_candidates": ["REPAIR_CANDIDATE"], "cycle_feature_vector": {},
        "style_strength_ranking": [], "theme_concentration": {}, "theme_features": [],
        "role_candidates": [], "money_effect_features": {}, "trend_chip_candidates": [],
        "next_day_plan_candidates": [], "objective_factor_features": {},
        "risk_and_falsification_candidates": [], "historical_changes": {},
        "data_quality": {"status": "PASS"},
    }
    inflection = {"meta": {"trade_date": "2026-09-04"}, "candidates": [], "data_quality": {"status": "PASS"}}
    auction = {"meta": {"trade_date": "2026-09-04"}, "data_quality": {"status": "PASS"}}
    _write(root / "data/market_packets/2026-09-04.json", market)
    _write(root / "data/review_intelligence/2026-09-04.json", intelligence)
    _write(root / "data/inflection/2026-09-04.json", inflection)
    _write(root / "data/auction_packets/2026-09-04.json", auction)


def test_context_contains_all_objective_sections(tmp_path):
    _inputs(tmp_path)
    result = ReviewContextBuilder(tmp_path).build(date(2026, 9, 4))
    required = {"market_environment", "next_day_theme_candidates", "medium_term_structure_candidates",
        "market_cycle_and_style", "core_theme_roles", "inflection_candidates",
        "previous_hypothesis_validation", "next_day_plan", "review_template_support", "data_quality"}
    assert required <= result["packet"].keys()
    assert result["packet"]["previous_hypothesis_validation"]["confirmed"] == ["A"]
    assert result["packet"]["previous_hypothesis_validation"]["weakened"] == ["B"]
    assert result["packet"]["previous_hypothesis_validation"]["invalidated"] == ["C"]
    assert len(json.dumps(result["compact"])) <= len(json.dumps(result["packet"]))


def test_mismatched_current_input_date_is_rejected(tmp_path):
    _inputs(tmp_path, market_date="2026-09-03")
    with pytest.raises(ValueError, match="date mismatch"):
        ReviewContextBuilder(tmp_path).build(date(2026, 9, 4))


def test_same_day_official_review_is_not_loaded_as_history(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path / "data/official_reviews/2026-09-04.json", {"date": "2026-09-04", "main_themes": ["future"]})
    result = ReviewContextBuilder(tmp_path).build(date(2026, 9, 4))
    assert result["packet"]["source_manifest"]["prior_official_review"]["status"] == "FALLBACK_EMBEDDED_HISTORY"


def test_output_contains_no_prohibited_final_conclusions(tmp_path):
    _inputs(tmp_path)
    packet = ReviewContextBuilder(tmp_path).build(date(2026, 9, 4))["packet"]
    text = json.dumps(packet, ensure_ascii=False)
    for phrase in ("应该买入", "建议仓位", "确定龙头", "确定主线", "股票推荐", "最终评级"):
        assert phrase not in text
