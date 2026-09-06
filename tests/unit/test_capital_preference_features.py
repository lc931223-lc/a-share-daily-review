from __future__ import annotations

import pandas as pd

from src.capital_preference.features import build_features


def _daily():
    rows = []
    stocks = (
        ("000001.SZ", "ThemeA", 0.08, 4_000_000),
        ("000002.SZ", "ThemeA", 0.03, 2_000_000),
        ("300001.SZ", "ThemeB", 0.01, 500_000),
        ("600001.SH", "ThemeC", -0.01, 200_000),
    )
    for index, timestamp in enumerate(pd.bdate_range("2025-07-01", periods=300)):
        for code, _, slope, amount in stocks:
            close = 10 * (1 + slope * index / 20)
            rows.append(
                {
                    "trade_date": timestamp.date().isoformat(),
                    "ts_code": code,
                    "close": close,
                    "amount": amount * (1 + index / 300),
                    "pct_chg": slope * 100,
                }
            )
    metadata = {code: {"stock_name": code, "industry": industry} for code, industry, _, _ in stocks}
    return pd.DataFrame(rows), metadata


def _inputs():
    intelligence = {
        "theme_features": [
            {
                "theme_name": "ThemeA",
                "theme_amount": 8_000_000,
                "theme_return": 8,
                "theme_inflection_score": 80,
                "top_gainers": [{"stock_code": "000001"}],
                "capacity_candidates": [],
            },
            {
                "theme_name": "ThemeB",
                "theme_amount": 500_000,
                "theme_return": 1,
                "theme_inflection_score": 50,
                "top_gainers": [{"stock_code": "000001"}, {"stock_code": "300001"}],
                "capacity_candidates": [{"stock_code": "300001"}],
            },
            {
                "theme_name": "ThemeC",
                "theme_amount": 200_000,
                "theme_return": -1,
                "theme_inflection_score": 20,
                "top_gainers": [{"stock_code": "600001"}],
                "capacity_candidates": [],
            },
        ],
        "role_candidates": [
            {
                "ts_code": "000001.SZ",
                "theme": "ThemeA",
                "role_candidate": "LEADER_CANDIDATE",
                "all_role_candidates": ["LEADER_CANDIDATE"],
                "role_candidate_score": 90,
            }
        ],
        "style_strength_ranking": [
            {"style": "value", "style_strength_score": 70},
            {"style": "growth", "style_strength_score": 50},
        ],
    }
    inflection = {
        "candidates": [
            {
                "ts_code": "000001.SZ",
                "status": "INFLECTION_CANDIDATE",
                "turnover_percentile_120d": 100,
            }
        ]
    }
    return intelligence, inflection


def test_missing_fundamental_and_no_capacity_stock_are_not_filled_with_false_data():
    daily, metadata = _daily()
    intelligence, inflection = _inputs()
    target = daily["trade_date"].max()
    themes, _ = build_features(
        target=target,
        daily=daily,
        metadata=metadata,
        market={},
        intelligence=intelligence,
        inflection=inflection,
        auction={},
        theme_activity={},
    )
    theme_a = next(row for row in themes if row["theme"] == "ThemeA")
    assert theme_a["fundamental_fit"]["score"] is None
    assert theme_a["capital_capacity"]["inputs"]["capacity_stock_count"] == 0
    assert theme_a["capital_capacity"]["score"] is not None
    assert theme_a["capacity_structure"]["capacity"] is None


def test_overcrowding_and_multi_theme_competition_remain_objective_candidates():
    daily, metadata = _daily()
    intelligence, inflection = _inputs()
    target = daily["trade_date"].max()
    themes, stocks = build_features(
        target=target,
        daily=daily,
        metadata=metadata,
        market={},
        intelligence=intelligence,
        inflection=inflection,
        auction={},
        theme_activity={
            name: {"active_days": 10, "observation_days": 10, "active_ratio": 1}
            for name in ("ThemeA", "ThemeB", "ThemeC")
        },
    )
    theme_a = next(row for row in themes if row["theme"] == "ThemeA")
    shared = next(row for row in stocks if row["ts_code"] == "000001.SZ")
    assert theme_a["crowding_status"] in {"ELEVATED", "EXTREME"}
    assert set(shared["themes"]) == {"ThemeA", "ThemeB"}
    assert all(row["candidate_only"] for row in themes + stocks)
    assert "prediction" not in str(themes).lower()
