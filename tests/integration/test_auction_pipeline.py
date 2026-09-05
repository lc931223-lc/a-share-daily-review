from datetime import date
import json
from pathlib import Path

import pytest

from src.auction.eltdx_source import AuctionCollection
from src.auction.pipeline import AuctionPipeline
from src.market_packet.trading_calendar import TradingCalendarDay


class FakeAuctionSource:
    def collect_historical(self, stocks, trade_date):
        process = []
        formal = []
        for index, stock in enumerate(stocks):
            base = {
                "trade_date": trade_date.isoformat(), "ts_code": stock["ts_code"], "stock_name": stock["stock_name"],
                "snapshot_time": f"{trade_date.isoformat()}T09:24:58+08:00", "checkpoint_time": None,
                "match_price": 10.0 + index, "matched_volume": 1000, "matched_amount": 10_000 + index,
                "unmatched_signed_volume": None, "unmatched_direction_raw": 1, "unmatched_buy": None,
                "unmatched_sell": None, "raw_matched_volume": 10, "raw_volume_unit": "lot",
                "matched_amount_value_kind": "DERIVED", "source": "eltdx", "source_batch_id": None,
                "retrieved_at": "2026-09-05T01:00:00+00:00", "source_data_time": f"{trade_date.isoformat()}T09:24:58+08:00",
                "checkpoint_lag_ms": None, "is_formal_opening_match": False, "quality_status": "PASS",
                "content_hash": f"process-{index}", "schema_version": "auction_snapshot.1", "observation_kind": "raw_process",
            }
            process.append(base)
            opening = dict(base)
            opening.update({
                "snapshot_time": f"{trade_date.isoformat()}T09:25:00+08:00",
                "source_data_time": f"{trade_date.isoformat()}T09:25:00+08:00",
                "is_formal_opening_match": True, "content_hash": f"formal-{index}",
                "observation_kind": "formal_opening_match",
            })
            formal.append(opening)
        return AuctionCollection(process, formal, [], {
            "request_count": len(stocks) * 2, "success_count": len(stocks), "failure_count": 0,
            "reconnect_count": 0, "median_latency_ms": 1.0, "p95_latency_ms": 2.0,
            "stock_completion_rate": 1.0,
        })

    def collect_formal_only(self, stocks, trade_date):
        return AuctionCollection([], [], [
            {"ts_code": stock["ts_code"], "error_type": "Unavailable", "error": "suspended"}
            for stock in stocks
        ], {
            "request_count": 1, "success_count": 0, "failure_count": len(stocks),
            "reconnect_count": 0, "median_latency_ms": 1.0, "p95_latency_ms": 1.0,
            "stock_completion_rate": 0.0,
        })


def test_historical_pipeline_writes_watchlist_packet_facts_and_audit(tmp_path):
    previous = date(2026, 9, 3)
    target = date(2026, 9, 4)
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    packet = {
        "stocks": [
            {"stock_code": "000001", "stock_name": "平安银行", "amount": 1000, "open": 10.0, "close": 10.0},
            {"stock_code": "600519", "stock_name": "贵州茅台", "amount": 900, "open": 11.0, "close": 11.0},
        ],
        "leader_candidates": [], "announcements": {"risk_announcements": []},
    }
    (packet_dir / f"{previous.isoformat()}.json").write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    calendar = [TradingCalendarDay(previous, True), TradingCalendarDay(target, True)]
    pipeline = AuctionPipeline(
        root=tmp_path, source_factory=FakeAuctionSource,
        calendar_loader=lambda _: calendar,
        eod_open_loader=lambda _, codes: {code: 10.0 if code.startswith("000001") else 11.0 for code in codes},
    )

    result = pipeline.run_historical(target, min_watchlist_size=2, max_watchlist_size=2, baseline_days=0)

    assert Path(result["paths"]["watchlist"]).exists()
    assert Path(result["paths"]["packet"]).exists()
    assert result["packet"]["watchlist"]["stock_count"] == 2
    assert result["packet"]["watchlist"]["sources"]["market_packet"] == "data/market_packets/2026-09-03.json"
    assert "output_path" not in result["packet"]["watchlist"]
    assert result["packet"]["market_auction_summary"]["formal_opening_match_success_rate"] == 1.0
    assert result["packet"]["data_quality"]["status"] == "PARTIAL"


def test_historical_amounts_deduplicate_append_only_partitions_by_trade_date(tmp_path):
    pipeline = AuctionPipeline(root=tmp_path)
    for amount in (100.0, 120.0):
        pipeline.fact_store.write_dataset(
            "auction_daily_summary", date(2026, 9, 3),
            [{"ts_code": "000001.SZ", "auction_amount": amount, "revision": amount}],
        )
    pipeline.fact_store.write_dataset(
        "auction_daily_summary", date(2026, 9, 2),
        [{"ts_code": "000001.SZ", "auction_amount": 80.0}],
    )
    result = pipeline._historical_amounts(date(2026, 9, 4))
    assert len(result["000001.SZ"]) == 2
    assert result["000001.SZ"][-1] in {100.0, 120.0}


def test_archived_tushare_open_loader_prefers_full_raw_record_and_guards_date(tmp_path):
    raw_dir = tmp_path / "data" / "raw" / "market_packets" / "2026-09-04"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "tushare_daily_all.json"
    raw_path.write_text(json.dumps({
        "data_date": "2026-09-04",
        "rows": [{"ts_code": "000001.SZ", "open": 12.34}],
    }), encoding="utf-8")
    pipeline = AuctionPipeline(root=tmp_path, calendar_loader=lambda _: [])

    assert pipeline._load_archived_tushare_opens(date(2026, 9, 4)) == {"000001.SZ": 12.34}

    raw_path.write_text(json.dumps({
        "data_date": "2026-09-03",
        "rows": [{"ts_code": "000001.SZ", "open": 12.34}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="date mismatch"):
        pipeline._load_archived_tushare_opens(date(2026, 9, 4))


def test_baseline_backfill_rates_final_pool_coverage_not_only_missing_stocks(tmp_path):
    pipeline = AuctionPipeline(root=tmp_path, source_factory=FakeAuctionSource)
    baseline_date = date(2026, 9, 3)
    stocks = [
        {"ts_code": f"{index:06d}.SZ", "stock_name": str(index)}
        for index in range(100)
    ]
    pipeline.fact_store.write_dataset("auction_daily_summary", baseline_date, [
        {"trade_date": baseline_date.isoformat(), "ts_code": stock["ts_code"], "auction_amount": 100.0}
        for stock in stocks[:99]
    ])

    result = pipeline._backfill_formal_baselines(stocks, [baseline_date])

    assert result["completed_dates"] == 1
    assert result["failed_dates"] == []
    assert result["minimum_stock_coverage"] == 0.99
