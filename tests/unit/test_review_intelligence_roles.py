from src.review_intelligence.roles import build_role_candidates, detect_catalyst_fatigue


def _theme():
    return {
        "theme_name": "robot", "theme_inflection_score": 70,
        "top_gainers": [
            {"stock_code": "000001", "stock_name": "small", "change_pct": 10, "amount": 1e8, "board_count": 2},
            {"stock_code": "000002", "stock_name": "capacity", "change_pct": 4, "amount": 5e9, "board_count": 0},
        ],
        "leader_candidates": [], "capacity_candidates": [], "catch_up_candidates": [],
    }


def test_only_small_stock_has_no_capacity_candidate():
    theme = _theme()
    theme["top_gainers"] = theme["top_gainers"][:1]
    rows = build_role_candidates([theme], {}, {}, {})
    assert not any(row["role_candidate"] == "CAPACITY_CANDIDATE" for row in rows)


def test_capacity_can_rank_when_large_amount_is_confirmed():
    rows = build_role_candidates([_theme()], {}, {}, {})
    capacity = next(row for row in rows if row["ts_code"].startswith("000002"))
    assert capacity["role_scores"]["capacity"] > capacity["role_scores"]["leader"]


def test_old_theme_laggard_is_only_catch_up_candidate():
    rows = build_role_candidates([_theme()], {}, {}, {})
    laggard = next(row for row in rows if row["ts_code"].startswith("000002"))
    assert "CATCH_UP_CANDIDATE" in laggard["all_role_candidates"]


def test_positive_catalyst_fatigue_needs_two_comparable_events():
    events = [
        {"ts_code": "000001.SZ", "strength": 5, "return_3d": 8, "amount_change": 1.5},
        {"ts_code": "000001.SZ", "strength": 8, "return_3d": 1, "amount_change": 0.2},
    ]
    assert detect_catalyst_fatigue(events)[0]["label"] == "POSITIVE_CATALYST_FATIGUE_CANDIDATE"
    assert detect_catalyst_fatigue(events[:1]) == []


def test_inflection_match_can_supply_trend_leader_candidate():
    theme = _theme()
    theme["trend_candidates"] = [{"ts_code": "000003.SZ", "stock_name": "trend"}]
    rows = build_role_candidates(
        [theme], {}, {"000003.SZ": {"trend_inflection_score": 60, "breakout_hold_days": 3}}, {}
    )
    trend = next(row for row in rows if row["ts_code"] == "000003.SZ")
    assert trend["role_candidate"] == "TREND_LEADER_CANDIDATE"
