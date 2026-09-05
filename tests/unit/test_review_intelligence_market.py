from src.review_intelligence.market import compute_cycle_features, compute_market_operability


def _market(**overrides):
    base = {
        "total_market_turnover": 1_000.0,
        "turnover_delta_pct": 5.0,
        "rise_count": 3000,
        "fall_count": 2000,
        "limit_up_count": 60,
        "limit_down_count": 5,
        "failed_limit_count": 20,
        "seal_rate": 75.0,
        "highest_board": 5,
        "previous_limit_up_avg_change_pct": 1.2,
        "previous_continuous_board_performance": {"avg_change_pct": 2.0, "red_rate": 70.0},
    }
    return base | overrides


def test_operability_keeps_missing_components_null():
    result = compute_market_operability(_market(turnover_delta_pct=None), [], None)
    assert result["feature_components"]["liquidity"] is None
    assert result["available_max_score"] < 100
    assert result["market_operability_score"] <= result["available_max_score"]


def test_high_level_retreat_is_only_a_cycle_candidate():
    result = compute_cycle_features(
        _market(rise_count=900, fall_count=4200, seal_rate=35, failed_limit_count=50,
                previous_limit_up_avg_change_pct=-3, limit_down_count=30),
        stocks=[{"board_count": 4, "change_pct": -8}],
        theme_changes={"new": 0, "strengthening": 0, "weakening": 8},
    )
    assert "RETREAT_CANDIDATE" in result["cycle_candidates"]
    assert "should" not in str(result).lower()


def test_new_theme_startup_candidate_requires_breadth():
    result = compute_cycle_features(
        _market(limit_up_count=70), [], {"new": 4, "strengthening": 3, "weakening": 0}
    )
    assert "STARTUP_CANDIDATE" in result["cycle_candidates"]
