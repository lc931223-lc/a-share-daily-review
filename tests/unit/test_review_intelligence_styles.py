import pandas as pd

from src.review_intelligence.styles import compute_style_rankings


def test_style_switch_has_objective_score_change():
    current = pd.DataFrame([
        {"ts_code": "300001.SZ", "pct_chg": 8, "amount": 200, "close": 20},
        {"ts_code": "600001.SH", "pct_chg": -2, "amount": 100, "close": 5},
    ])
    result = compute_style_rankings(current, pd.DataFrame(), {}, [], {}, {"growth": 10})
    growth = next(row for row in result if row["style"] == "growth")
    assert growth["style_change_1d"] is not None
    assert growth["style_change_1d"] > 0
