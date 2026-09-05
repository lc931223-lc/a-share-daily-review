from datetime import date

from src.auction.watchlist import compose_watchlist


def test_watchlist_prioritizes_review_and_fills_from_objective_packet():
    review = {
        "main_themes": [{"name": "机器人"}],
        "stocks": [{"code": "300001", "name": "核心股", "theme": "机器人", "role": "leader"}],
        "tomorrow_checks": [{"entity_type": "stock", "entity_key": "300002", "description": "观察承接"}],
    }
    stocks = [
        {
            "stock_code": f"{index:06d}",
            "stock_name": f"股票{index}",
            "themes": ["机器人"] if index == 2 else ["其他"],
            "amount": 1_000_000 - index,
            "limit_up": index == 3,
            "continuous_board_count": 2 if index == 4 else 0,
        }
        for index in range(1, 12)
    ]
    packet = {"stocks": stocks, "leader_candidates": [], "announcements": {"risk_announcements": []}}

    result = compose_watchlist(
        target_date=date(2026, 9, 7),
        previous_trade_date=date(2026, 9, 4),
        review=review,
        packet=packet,
        historical_codes=["600519.SH"],
        min_size=8,
        max_size=10,
    )

    assert 8 <= len(result["stocks"]) <= 10
    by_code = {item["ts_code"]: item for item in result["stocks"]}
    assert "300001.SZ" in by_code
    assert "official_review_stock" in by_code["300001.SZ"]["reasons"]
    assert "theme_member" in by_code["000002.SZ"]["reasons"]
    assert "previous_limit_up" in by_code["000003.SZ"]["reasons"]
    assert "historical_tracking" in by_code["600519.SH"]["reasons"]


def test_watchlist_does_not_invent_stocks_when_inputs_are_sparse():
    result = compose_watchlist(
        target_date=date(2026, 9, 7),
        previous_trade_date=date(2026, 9, 4),
        review={},
        packet={"stocks": []},
        historical_codes=[],
        min_size=100,
        max_size=200,
    )
    assert result["stocks"] == []
    assert result["quality_status"] == "PARTIAL"
