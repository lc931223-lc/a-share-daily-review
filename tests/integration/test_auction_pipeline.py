import json
from datetime import date
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
                "trade_date": trade_date.isoformat(),
                "ts_code": stock["ts_code"],
                "stock_name": stock["stock_name"],
                "snapshot_time": f"{trade_date.isoformat()}T09:24:58+08:00",
                "checkpoint_time": None,
                "match_price": 10.0 + index,
                "matched_volume": 1000,
                "matched_amount": 10_000 + index,
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
                "source_data_time": f"{trade_date.isoformat()}T09:24:58+08:00",
                "checkpoint_lag_ms": None,
                "is_formal_opening_match": False,
                "quality_status": "PASS",
                "content_hash": f"process-{index}",
                "schema_version": "auction_snapshot.1",
                "observation_kind": "raw_process",
            }
            process.append(base)
            opening = dict(base)
            opening.update(
                {
                    "snapshot_time": f"{trade_date.isoformat()}T09:25:00+08:00",
                    "source_data_time": f"{trade_date.isoformat()}T09:25:00+08:00",
                    "is_formal_opening_match": True,
                    "content_hash": f"formal-{index}",
                    "observation_kind": "formal_opening_match",
                }
            )
            formal.append(opening)
        return AuctionCollection(
            process,
            formal,
            [],
            {
                "request_count": len(stocks) * 2,
                "success_count": len(stocks),
                "failure_count": 0,
                "reconnect_count": 0,
                "median_latency_ms": 1.0,
                "p95_latency_ms": 2.0,
                "stock_completion_rate": 1.0,
            },
        )


class FakeLiveAuctionSource(FakeAuctionSource):
    def connect(self):
        pass

    def close(self):
        pass

    def collect_live_process(self, stocks, trade_date):
        return self.collect_historical(stocks, trade_date)

    def collect_live_formal(self, stocks, trade_date):
        return self.collect_historical(stocks, trade_date)

    def _stats(self, completed, total):
        return dict(request_count=1,success_count=completed,failure_count=total-completed,reconnect_count=0,median_latency_ms=1,p95_latency_ms=1,stock_completion_rate=completed/total)


def test_twenty_stock_live_freeze_then_resume_never_calls_open_router(tmp_path):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    target=date(2026,9,9)
    previous=date(2026,9,8)
    folder=tmp_path/'data/market_packets'
    folder.mkdir(parents=True)
    (folder/f'{previous}.json').write_text(json.dumps({'meta':{'trade_date':str(previous)},'stocks':[{'stock_code':f'{n:06d}','stock_name':f'stock{n}','close':10,'amount':1000000} for n in range(1,21)]}),encoding='utf-8')
    class NoOpen:
        def load(self,*a,**k):
            pytest.fail('09:25 must not request post-open quotes')
    clock=[datetime(2026,9,9,9,14,50,tzinfo=ZoneInfo('Asia/Shanghai'))]
    pipe=AuctionPipeline(root=tmp_path,source_factory=FakeLiveAuctionSource,calendar_loader=lambda _:[TradingCalendarDay(previous,True),TradingCalendarDay(target,True)],realtime_open_router=NoOpen())
    result=pipe.run_live(target,min_watchlist_size=20,max_watchlist_size=20,baseline_days=60,now=lambda:clock[0],sleeper=lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)))
    assert clock[0].strftime('%H:%M:%S')=='09:25:02'
    assert 'auction_report_0925' in result['packet']
    assert 'post_open_validation' not in result['packet']
    assert result['packet']['data_quality']['production']['previous_formal_review_status']=='MISSING'
    assert pipe.run_live(target,now=lambda:clock[0])['reused']

    def collect_formal_only(self, stocks, trade_date):
        return AuctionCollection(
            [],
            [],
            [
                {"ts_code": stock["ts_code"], "error_type": "Unavailable", "error": "suspended"}
                for stock in stocks
            ],
            {
                "request_count": 1,
                "success_count": 0,
                "failure_count": len(stocks),
                "reconnect_count": 0,
                "median_latency_ms": 1.0,
                "p95_latency_ms": 1.0,
                "stock_completion_rate": 0.0,
            },
        )


def test_historical_pipeline_writes_watchlist_packet_facts_and_audit(tmp_path):
    previous = date(2026, 9, 3)
    target = date(2026, 9, 4)
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    packet = {
        "meta": {"trade_date": previous.isoformat()},
        "stocks": [
            {
                "stock_code": f"{index:06d}",
                "stock_name": f"股票{index}",
                "amount": 1_000_000 - index,
                "open": 10.0,
                "close": 10.0,
                "themes": ["测试板块"],
            }
            for index in range(1, 21)
        ],
        "leader_candidates": [],
        "announcements": {"risk_announcements": []},
    }
    (packet_dir / f"{previous.isoformat()}.json").write_text(
        json.dumps(packet, ensure_ascii=False), encoding="utf-8"
    )
    calendar = [TradingCalendarDay(previous, True), TradingCalendarDay(target, True)]
    pipeline = AuctionPipeline(
        root=tmp_path,
        source_factory=FakeAuctionSource,
        calendar_loader=lambda _: calendar,
        eod_open_loader=lambda _, codes: {
            code: 10.0 if code.startswith("000001") else 11.0 for code in codes
        },
    )

    result = pipeline.run_historical(
        target, min_watchlist_size=20, max_watchlist_size=20, baseline_days=0
    )

    assert Path(result["paths"]["watchlist"]).exists()
    assert Path(result["paths"]["packet"]).exists()
    assert Path(result["paths"]["compact_packet"]).exists()
    assert result["packet"]["watchlist"]["stock_count"] == 20
    assert (
        result["packet"]["watchlist"]["sources"]["market_packet"]
        == "data/market_packets/2026-09-03.json"
    )
    assert "output_path" not in result["packet"]["watchlist"]
    assert result["packet"]["market_auction_summary"]["formal_opening_match_success_rate"] == 1.0
    assert result["compact_packet"]["sector_auction_ranking"][0]["name"] == "测试板块"
    assert result["compact_packet"]["previous_mainline_validation"]["status"] == "UNAVAILABLE"
    assert result["compact_packet"]["weak_to_strong_candidates"] == []
    scores = [
        item["auction_volume_anomaly_score"]
        for item in result["packet"]["volume_anomaly_candidates"]
    ]
    assert scores == sorted(scores, reverse=True)
    assert result["packet"]["data_quality"]["status"] == "FAIL"
    assert result["packet"]["data_quality"]["level"] == "LOW"


def test_historical_amounts_deduplicate_append_only_partitions_by_trade_date(tmp_path):
    pipeline = AuctionPipeline(root=tmp_path)
    for amount in (100.0, 120.0):
        pipeline.fact_store.write_dataset(
            "auction_daily_summary",
            date(2026, 9, 3),
            [{"ts_code": "000001.SZ", "auction_amount": amount, "revision": amount}],
        )
    pipeline.fact_store.write_dataset(
        "auction_daily_summary",
        date(2026, 9, 2),
        [{"ts_code": "000001.SZ", "auction_amount": 80.0}],
    )
    result = pipeline._historical_amounts(date(2026, 9, 4))
    assert len(result["000001.SZ"]) == 2
    assert result["000001.SZ"][-1] in {100.0, 120.0}


def test_post_open_stage_updates_packet_and_persists_fact_partition(tmp_path):
    target = date(2026, 9, 4)
    previous = date(2026, 9, 3)
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / f"{previous.isoformat()}.json").write_text(
        json.dumps(
            {
                "meta": {"trade_date": previous.isoformat()},
                "stocks": [
                    {
                        "stock_code": f"{index:06d}",
                        "stock_name": f"股票{index}",
                        "amount": 1_000_000 - index,
                        "open": 10.0,
                        "close": 10.0,
                        "themes": ["测试板块"],
                    }
                    for index in range(1, 21)
                ],
                "leader_candidates": [],
                "announcements": {"risk_announcements": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calendar = [TradingCalendarDay(previous, True), TradingCalendarDay(target, True)]
    pipeline = AuctionPipeline(
        root=tmp_path,
        source_factory=FakeAuctionSource,
        calendar_loader=lambda _: calendar,
    )
    pipeline.run_historical(
        target, min_watchlist_size=20, max_watchlist_size=20, baseline_days=0
    )

    class FakePostOpenRouter:
        @staticmethod
        def load(trade_date, codes, *, now=None):
            return (
                "fixture_post_open",
                [
                    {
                        "ts_code": code,
                        "last_price": 11.2,
                        "open_price": 11.0,
                        "high_price": 11.3,
                        "low_price": 11.0,
                        "observed_at": f"{trade_date.isoformat()}T09:35:00+08:00",
                    }
                    for code in codes
                ],
                [],
            )

    pipeline.post_open_router = FakePostOpenRouter()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    frozen_path = tmp_path / 'data/auction_packets' / f'{target}.json'
    before = frozen_path.read_bytes()
    result = pipeline.run_post_open(target, now=datetime.combine(target, datetime.strptime('09:35','%H:%M').time(), ZoneInfo('Asia/Shanghai')))

    validation = result["packet"]["post_open_validation"]
    assert validation["status"] == "AVAILABLE"
    assert validation["coverage"] == 1.0
    assert Path(result["path"]).exists()
    assert frozen_path.read_bytes() == before
    assert len(result['post_open']['snapshots']) == 1


def test_archived_tushare_open_loader_prefers_full_raw_record_and_guards_date(tmp_path):
    raw_dir = tmp_path / "data" / "raw" / "market_packets" / "2026-09-04"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "tushare_daily_all.json"
    raw_path.write_text(
        json.dumps(
            {
                "data_date": "2026-09-04",
                "rows": [{"ts_code": "000001.SZ", "open": 12.34}],
            }
        ),
        encoding="utf-8",
    )
    pipeline = AuctionPipeline(root=tmp_path, calendar_loader=lambda _: [])

    assert pipeline._load_archived_tushare_opens(date(2026, 9, 4)) == {"000001.SZ": 12.34}

    raw_path.write_text(
        json.dumps(
            {
                "data_date": "2026-09-03",
                "rows": [{"ts_code": "000001.SZ", "open": 12.34}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="date mismatch"):
        pipeline._load_archived_tushare_opens(date(2026, 9, 4))


def test_baseline_backfill_rates_final_pool_coverage_not_only_missing_stocks(tmp_path):
    pipeline = AuctionPipeline(root=tmp_path, source_factory=FakeAuctionSource)
    baseline_date = date(2026, 9, 3)
    stocks = [{"ts_code": f"{index:06d}.SZ", "stock_name": str(index)} for index in range(100)]
    pipeline.fact_store.write_dataset(
        "auction_daily_summary",
        baseline_date,
        [
            {
                "trade_date": baseline_date.isoformat(),
                "ts_code": stock["ts_code"],
                "auction_amount": 100.0,
            }
            for stock in stocks[:99]
        ],
    )

    result = pipeline._backfill_formal_baselines(stocks, [baseline_date])

    assert result["completed_dates"] == 1
    assert result["failed_dates"] == []
    assert result["minimum_stock_coverage"] == 0.99
