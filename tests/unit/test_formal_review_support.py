from __future__ import annotations

import pytest

from src.domain.constants import DRIVER_TYPES
from src.formal_review.support import (
    _factor_evaluation,
    _lifecycle,
    _previous_day_validation,
    _roles,
    validate_formal_review_record,
)


def test_factor_evaluation_always_contains_exact_41_catalog_entries():
    rows = _factor_evaluation([])
    assert [row["factor_id"] for row in rows] == list(range(1, 42))
    assert [row["factor_name"] for row in rows] == list(DRIVER_TYPES.values())
    assert all(row["status"] == "UNCONFIRMED" for row in rows)


def test_tier_four_evidence_cannot_confirm_factor():
    payload = {
        "main_themes": [
            {
                "41_factors": [
                    {
                        "factor_id": factor_id,
                        "factor_name": name,
                        "status": "CONFIRMED" if factor_id == 1 else "UNCONFIRMED",
                        "evidence": [{"tier": 4}] if factor_id == 1 else [],
                    }
                    for factor_id, name in DRIVER_TYPES.items()
                ]
            }
        ]
    }
    with pytest.raises(ValueError, match="Tier 4"):
        validate_formal_review_record(payload)


def test_future_dated_formal_evidence_is_rejected():
    payload = {
        "date": "2026-09-08",
        "main_themes": [
            {
                "41_factors": [
                    {
                        "factor_id": factor_id,
                        "factor_name": name,
                        "status": "CONFIRMED" if factor_id == 1 else "UNCONFIRMED",
                        "evidence": (
                            [{"tier": 1, "source_date": "2026-09-09"}]
                            if factor_id == 1
                            else []
                        ),
                    }
                    for factor_id, name in DRIVER_TYPES.items()
                ]
            }
        ],
    }
    with pytest.raises(ValueError, match="future-dated"):
        validate_formal_review_record(payload)


def test_lifecycle_does_not_jump_from_meng_long_to_main_up_on_one_day_strength():
    result = _lifecycle({"strength": 90, "strength_change_1d": 20}, "MENG_LONG")
    assert result["current_state"] == "VALIDATION"


def test_role_projection_reuses_capital_preference_evidence():
    context = {
        "core_theme_roles": [
            {
                "theme": "机器人",
                "leader_candidate": {
                    "ts_code": "000001.SZ",
                    "stock_name": "样本",
                    "role_candidate_score": 72,
                },
            }
        ],
        "capital_preference": {
            "stock_capital_preference": [
                {
                    "ts_code": "000001.SZ",
                    "themes": ["机器人"],
                    "stock_capital_preference_score": 81,
                }
            ]
        },
    }
    roles = _roles(context, "机器人")
    assert roles[0]["role"] == "LEADER"
    assert roles[0]["capital_preference_score"] == 81
    assert roles[0]["unconfirmed_claims"]


def test_previous_day_validation_excludes_support_hypothesis():
    previous = {
        "theme_support": [
            {
                "theme_name": "机器人",
                "next_day_validation": [
                    {
                        "validation_point": "板块保持正收益",
                        "strengthening_condition": "板块保持正收益",
                    }
                ],
                "core_stocks": [],
            }
        ]
    }
    market = {"themes": [{"name": "机器人", "change_pct": -1.2}], "stocks": []}
    result = _previous_day_validation(None, None, market, previous)
    assert result["prediction_count"] == 0
    assert result["hit_rate"] is None
