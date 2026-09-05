from datetime import date

from src.auction.checkpoints import map_checkpoints


def _event(time_text: str, price: float, amount: float) -> dict:
    return {
        "trade_date": "2026-09-04",
        "ts_code": "000001.SZ",
        "stock_name": "平安银行",
        "snapshot_time": f"2026-09-04T{time_text}+08:00",
        "checkpoint_time": None,
        "match_price": price,
        "matched_volume": 1000,
        "matched_amount": amount,
        "unmatched_signed_volume": None,
        "unmatched_direction_raw": 1,
        "unmatched_buy": None,
        "unmatched_sell": None,
        "raw_matched_volume": 10,
        "raw_volume_unit": "lot",
        "matched_amount_value_kind": "DERIVED",
        "source": "eltdx",
        "source_batch_id": None,
        "retrieved_at": "2026-09-05T01:00:00+00:00",
        "source_data_time": f"2026-09-04T{time_text}+08:00",
        "checkpoint_lag_ms": None,
        "is_formal_opening_match": False,
        "quality_status": "PASS",
        "content_hash": "raw",
        "schema_version": "auction_snapshot.1",
        "observation_kind": "raw_process",
    }


def test_checkpoint_uses_latest_prior_event_and_formal_opening_match():
    events = [_event("09:19:40", 10.0, 10_000), _event("09:19:58", 10.1, 12_000)]
    formal = _event("09:25:00", 10.2, 15_000)
    formal["is_formal_opening_match"] = True
    formal["observation_kind"] = "formal_opening_match"

    rows = map_checkpoints(date(2026, 9, 4), events, formal, max_lag_seconds=65)
    by_time = {row["checkpoint_time"]: row for row in rows}

    assert by_time["09:20:00"]["match_price"] == 10.1
    assert by_time["09:20:00"]["checkpoint_lag_ms"] == 2_000
    assert by_time["09:25:00"]["is_formal_opening_match"] is True


def test_checkpoint_does_not_use_future_or_stale_event():
    events = [_event("09:15:30", 10.0, 10_000), _event("09:18:40", 10.1, 12_000)]
    rows = map_checkpoints(date(2026, 9, 4), events, None, max_lag_seconds=15)
    by_time = {row["checkpoint_time"]: row for row in rows}

    assert by_time["09:15:00"]["quality_status"] == "UNAVAILABLE"
    assert by_time["09:17:00"]["match_price"] is None
    assert by_time["09:19:00"]["match_price"] is None
    assert by_time["09:25:00"]["match_price"] is None
