from src.services.market_calculations import calculate_breadth, calculate_limit_price, quotes


def test_market_breadth_is_recomputed_from_quotes():
    result = calculate_breadth(quotes([1.2, 0.0, -0.5]))

    assert result.advancers == 1
    assert result.flat == 1
    assert result.decliners == 1


def test_market_breadth_sums_turnover():
    result = calculate_breadth(
        [
            {"ts_code": "600001.SH", "pct_chg": 1.2, "amount": 100000.0},
            {"ts_code": "000001.SZ", "pct_chg": -0.5, "amount": 200000.0},
        ]
    )

    assert result.turnover_yi == 3.0


def test_calculate_limit_price_respects_board_rules():
    assert calculate_limit_price(10.0, "600001.SH") == 11.0
    assert calculate_limit_price(10.0, "300750.SZ") == 12.0
    assert calculate_limit_price(10.0, "688001.SH") == 12.0
    assert calculate_limit_price(10.0, "830001.BJ") == 13.0


def test_st_stock_uses_five_percent_limit():
    assert calculate_limit_price(10.0, "600001.SH", is_st=True) == 10.5
