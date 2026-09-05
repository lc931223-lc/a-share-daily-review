from src.review_intelligence.themes import compute_concentration, score_themes


def _theme(name, amount, limit_up, rise=8, fall=2):
    return {
        "theme_name": name, "amount": amount, "limit_up_count": limit_up,
        "rise_count": rise, "fall_count": fall, "top_gainers": [],
        "leader_candidates": [], "capacity_candidates": [], "catch_up_candidates": [],
    }


def test_multiple_equal_themes_are_not_high_concentration():
    result = compute_concentration([_theme("A", 100, 2), _theme("B", 100, 2), _theme("C", 100, 2)])
    assert result["concentration_candidate"] != "HIGH"


def test_no_clear_theme_stays_low():
    themes = [_theme(str(index), 10, 0, rise=1, fall=9) for index in range(10)]
    assert compute_concentration(themes)["concentration_candidate"] == "LOW"


def test_theme_score_change_is_not_fabricated_without_history():
    rows = score_themes([_theme("new", 100, 3)], {}, {}, {}, {})
    assert rows[0]["score_change"] is None
    assert rows[0]["previous_review_score"] is None
