from src.auction.open_validation import apply_open_validation


def test_open_validation_records_exact_match():
    summaries = [{"ts_code": "000001.SZ", "auction_price": 10.0}]
    conflicts = apply_open_validation(summaries, {"000001.SZ": 10.0}, source="tushare_daily")
    assert conflicts == []
    assert summaries[0]["open_price_error_pct"] == 0.0
    assert summaries[0]["conflict_status"] == "none"


def test_open_validation_preserves_conflicting_values():
    summaries = [{"ts_code": "000001.SZ", "auction_price": 10.0}]
    conflicts = apply_open_validation(summaries, {"000001.SZ": 10.1}, source="tencent_realtime")
    assert len(conflicts) == 1
    assert conflicts[0]["auction_final_price"] == 10.0
    assert conflicts[0]["official_open_price"] == 10.1
    assert summaries[0]["conflict_status"] == "conflict"


def test_open_validation_keeps_missing_reference_null():
    summaries = [{"ts_code": "000001.SZ", "auction_price": 10.0}]
    apply_open_validation(summaries, {}, source="tencent_realtime")
    assert summaries[0]["open_price_error_pct"] is None
    assert summaries[0]["conflict_status"] == "not_validated"
