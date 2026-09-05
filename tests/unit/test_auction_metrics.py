from src.auction.metrics import build_daily_summary


def _checkpoint(time_text: str, price: float, amount: float, formal: bool = False) -> dict:
    return {
        "trade_date": "2026-09-04",
        "ts_code": "000001.SZ",
        "stock_name": "平安银行",
        "checkpoint_time": time_text,
        "match_price": price,
        "matched_volume": amount / price,
        "matched_amount": amount,
        "is_formal_opening_match": formal,
        "quality_status": "PASS",
    }


def test_daily_summary_computes_baselines_growth_and_unscaled_score():
    rows = [
        _checkpoint("09:20:00", 10.0, 100_000),
        _checkpoint("09:23:00", 10.1, 150_000),
        _checkpoint("09:24:00", 10.2, 180_000),
        _checkpoint("09:25:00", 10.3, 250_000, formal=True),
    ]
    history = [50_000 + index * 1_000 for index in range(60)]

    result = build_daily_summary(
        rows,
        previous_close=10.0,
        previous_day_amount=10_000_000,
        historical_auction_amounts=history,
    )

    assert result["auction_amount_ratio_5d"] is not None
    assert result["auction_amount_ratio_20d"] is not None
    assert result["auction_amount_percentile_60d"] == 100.0
    assert result["post_0920_amount_growth"] == 2.5
    assert result["last_2min_amount_growth"] == 250_000 / 150_000
    assert result["last_1min_amount_growth"] == (250_000 - 180_000) / 180_000
    assert 0 <= result["auction_volume_anomaly_score"] <= 20
    assert result["score_component_coverage"] == 1.0
    assert result["baseline_quality_status"] == "PASS"
    assert "STRONG_VOLUME_CONFIRMATION" in result["anomaly_labels"]


def test_daily_summary_keeps_missing_metrics_null_and_partial():
    result = build_daily_summary(
        [_checkpoint("09:25:00", 10.0, 100_000, formal=True)],
        previous_close=None,
        previous_day_amount=None,
        historical_auction_amounts=[],
    )

    assert result["auction_amount_ratio_5d"] is None
    assert result["auction_amount_ratio_20d"] is None
    assert result["auction_amount_percentile_60d"] is None
    assert result["auction_to_prev_day_amount"] is None
    assert result["post_0920_amount_growth"] is None
    assert result["score_component_coverage"] < 1.0
    assert result["quality_status"] == "PARTIAL"
    assert result["anomaly_labels"] == []
