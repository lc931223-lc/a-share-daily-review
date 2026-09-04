import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from src.validation.errors import format_validation_error
from src.validation.review_models import DailyReview


ROOT = Path(__file__).resolve().parents[2]


def valid_review():
    driver = {"code": 21, "name": "下游资本开支爆发", "evidence_level": "B"}
    return {
        "schema_version": "2.0",
        "date": "2026-09-01",
        "data_kind": "real",
        "strict_mode": True,
        "completeness": {"score": 80, "missing_items": ["炸板率"]},
        "market_regime": "分歧修复",
        "turnover": 20300.0,
        "turnover_delta": None,
        "advancers": 3386,
        "decliners": 2040,
        "limit_up_count": 94,
        "limit_down_count": 2,
        "max_board_height": 6,
        "position_min": 3,
        "position_max": 5,
        "main_themes": [
            {
                "name": "主题甲",
                "rank_no": 1,
                "stage": "主升期",
                "change_status": "strengthened",
                "causal_chain": ["真实观测", "资金确认", "订单"],
                "drivers": [driver],
                "scores": {
                    "base_logic_score": 38,
                    "realization_score": 23,
                    "expectation_gap_score": 8,
                    "persistence_score": 9,
                    "market_confirmation_score": 9,
                    "risk_penalty": -3,
                    "total_score": 84,
                    "rating": "S",
                    "logic_quality": 88,
                    "market_strength": 86,
                    "risk_reward": 72,
                    "missing_reasons": {},
                },
                "delta_reason": "产业链订单继续验证",
            }
        ],
        "stocks": [
            {
                "name": "测试中军",
                "code": "300308",
                "theme": "主题甲",
                "role": "中军",
                "role_detail": "核心趋势股",
                "stage": "主升期",
                "drivers": [driver],
                "catalyst": "资本开支增加",
                "benefit_path": ["需求", "订单", "利润"],
                "causal_chain": ["资本开支", "高速互联", "订单"],
                "scores": {
                    "realization_score": 82,
                    "expectation_gap": 68,
                    "logic_quality": 88,
                    "market_strength": 84,
                    "risk_reward": 70,
                    "total_score": 79,
                    "rating": "A",
                    "missing_reasons": {},
                },
                "delta_reason": "趋势保持",
            }
        ],
        "evidence": [
            {
                "entity_type": "theme",
                "entity_key": "主题甲",
                "evidence_level": "B",
                "evidence_type": "industry_data",
                "title": "资本开支数据",
                "source_name": "公开产业数据",
                "source_url": None,
                "published_at": None,
                "excerpt": "资本开支维持增长",
                "verified": True,
            }
        ],
        "risk_events": [],
        "tomorrow_checks": [
            {
                "entity_type": "theme",
                "entity_key": "主题甲",
                "check_type": "market_confirmation",
                "description": "板块成交额是否继续扩大",
            }
        ],
        "tomorrow_check_updates": [],
        "changes_vs_previous_day": {
            "new": [],
            "strengthened": ["主题甲"],
            "weakened": [],
            "expanded": [],
            "realized": [],
            "invalidated": [],
        },
    }


def test_valid_review_is_accepted():
    review = DailyReview.model_validate(valid_review())
    assert review.date.isoformat() == "2026-09-01"


def test_strict_partial_scores_require_reasons_and_no_total():
    payload = valid_review()
    scores = payload["main_themes"][0]["scores"]
    scores["realization_score"] = None
    scores["total_score"] = None
    scores["rating"] = None
    scores["missing_reasons"] = {
        "realization_score": "缺少订单和业绩证据",
        "total_score": "评分分项不完整",
        "rating": "综合分暂不生成",
    }
    review = DailyReview.model_validate(payload)
    assert review.main_themes[0].scores.total_score is None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("main_themes", 0, "stage"), "加速期"),
        (("main_themes", 0, "scores", "base_logic_score"), 41),
        (("stocks", 0, "code"), "123"),
        (("main_themes", 0, "drivers", 0, "name"), "错误名称"),
    ],
)
def test_invalid_business_values_are_rejected(path, value):
    payload = valid_review()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        DailyReview.model_validate(payload)


def test_total_and_rating_must_match_formula():
    payload = valid_review()
    payload["main_themes"][0]["scores"]["total_score"] = 85
    with pytest.raises(ValidationError, match="total_score 应为 84"):
        DailyReview.model_validate(payload)


def test_null_without_reason_has_precise_error_path():
    payload = valid_review()
    payload["main_themes"][0]["scores"]["logic_quality"] = None
    with pytest.raises(ValidationError) as exc_info:
        DailyReview.model_validate(payload)
    message = format_validation_error(exc_info.value)
    assert "main_themes.0.scores" in message
    assert "logic_quality 为 null" in message


def test_real_review_requires_strict_mode():
    payload = valid_review()
    payload["strict_mode"] = False
    with pytest.raises(ValidationError, match="真实数据必须启用"):
        DailyReview.model_validate(payload)


def test_daily_review_rejects_demo():
    payload = valid_review()
    payload["data_kind"] = "demo"
    with pytest.raises(ValidationError, match="data_kind"):
        DailyReview.model_validate(payload)


def test_daily_review_requires_schema_version_2():
    payload = valid_review()
    payload["schema_version"] = "1.0"
    with pytest.raises(ValidationError, match="schema_version"):
        DailyReview.model_validate(payload)


def test_json_schema_and_pydantic_accept_same_valid_fixture():
    payload = valid_review()
    schema = json.loads((ROOT / "schemas" / "daily_review.schema.json").read_text("utf-8"))
    assert schema == DailyReview.model_json_schema()
    Draft202012Validator(schema).validate(payload)
    DailyReview.model_validate(payload)
