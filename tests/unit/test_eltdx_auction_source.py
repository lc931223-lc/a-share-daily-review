from datetime import date
from types import SimpleNamespace

from src.auction.eltdx_source import EltdxAuctionSource


class FakeClient:
    def __init__(self, *, fail_code: str | None = None):
        self.fail_code = fail_code
        self.auctions = SimpleNamespace(series=self.series)
        self.trades = SimpleNamespace(opening_match_history=self.opening)

    def connect(self):
        return None

    def close(self):
        return None

    def series(self, code, date_text):
        if code == self.fail_code:
            raise RuntimeError("single stock failure")
        point = SimpleNamespace(
            time_label="09:20:00",
            time_seconds=33_600,
            price=10.0,
            matched_volume=12,
            unmatched_volume=3,
            unmatched_signed_raw=-3,
            unmatched_direction_raw=-1,
        )
        return SimpleNamespace(points=[point])

    def opening(self, code, date_text, **kwargs):
        if isinstance(code, list):
            return {
                ("sh" if item.startswith("6") else "sz") + item: self.opening(item, date_text)
                for item in code if item != self.fail_code
            }
        if code == self.fail_code:
            raise RuntimeError("single stock failure")
        return SimpleNamespace(price=10.2, volume=20, trade_amount_yuan=20_400, time_label="09:25")


def test_eltdx_normalizes_lots_and_keeps_unknown_direction_fields_null():
    source = EltdxAuctionSource(client_factory=FakeClient)
    result = source.collect_historical([{"ts_code": "000001.SZ", "stock_name": "平安银行"}], date(2026, 9, 4))

    raw = result.process_rows[0]
    assert raw["matched_volume"] == 1_200
    assert raw["raw_matched_volume"] == 12
    assert raw["raw_volume_unit"] == "lot"
    assert raw["matched_amount"] == 12_000
    assert raw["matched_amount_value_kind"] == "DERIVED"
    assert raw["unmatched_buy"] is None and raw["unmatched_sell"] is None
    assert result.formal_rows[0]["matched_volume"] == 2_000


def test_eltdx_isolates_single_stock_failure():
    source = EltdxAuctionSource(client_factory=lambda: FakeClient(fail_code="000002"), max_reconnects=1)
    result = source.collect_historical(
        [
            {"ts_code": "000001.SZ", "stock_name": "A"},
            {"ts_code": "000002.SZ", "stock_name": "B"},
        ],
        date(2026, 9, 4),
    )

    assert result.stats["success_count"] == 1
    assert result.stats["failure_count"] == 1
    assert result.stats["reconnect_count"] >= 1
    assert result.failures[0]["ts_code"] == "000002.SZ"


def test_eltdx_records_full_source_failure_without_fabricating_rows():
    source = EltdxAuctionSource(client_factory=lambda: FakeClient(fail_code="000001"), max_reconnects=1)
    result = source.collect_historical(
        [{"ts_code": "000001.SZ", "stock_name": "A"}],
        date(2026, 9, 4),
    )

    assert result.process_rows == []
    assert result.formal_rows == []
    assert result.stats["success_count"] == 0
    assert result.stats["failure_count"] == 1
    assert result.failures[0]["ts_code"] == "000001.SZ"
