from datetime import date
import json
from pathlib import Path

from src.auction.pipeline import AuctionPipeline


def test_eod_reconciliation_preserves_realtime_validation_and_writes_tushare_result(tmp_path):
    trade_date = date(2026, 9, 4)
    packet_dir = tmp_path / "data" / "auction_packets"
    packet_dir.mkdir(parents=True)
    packet = {
        "meta": {"schema_version": "auction_packet.1", "trade_date": trade_date.isoformat(), "mode": "live", "process_primary": "eltdx", "final_judgement_owner": "chatgpt"},
        "watchlist": {}, "market_auction_summary": {},
        "stock_auction_summary": [{
            "ts_code": "000001.SZ", "auction_price": 10.0, "official_open_price": 10.0,
            "open_price_validation_source": "tencent_realtime", "open_price_error_pct": 0.0,
            "conflict_status": "none", "quality_status": "PARTIAL",
        }],
        "volume_anomaly_candidates": [],
        "objective_analysis": {
            "market_auction_environment": {}, "previous_mainline_validation": {},
            "sector_auction_ranking": [], "stock_auction_ranking": [],
            "weak_to_strong_candidates": [], "strong_to_weak_candidates": [],
            "transition_status": "UNAVAILABLE", "validation_conditions_0930_1000": [],
        },
        "data_quality": {"status": "PARTIAL", "checks": []}, "conflicts": [],
    }
    path = packet_dir / f"{trade_date.isoformat()}.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    pipeline = AuctionPipeline(root=tmp_path, eod_open_loader=lambda _, __: {"000001.SZ": 10.0})
    result = pipeline.reconcile_eod(trade_date)
    summary = result["packet"]["stock_auction_summary"][0]
    assert summary["realtime_open_validation_source"] == "tencent_realtime"
    assert summary["eod_open_price_error_pct"] == 0.0
    assert result["status"] == "PASS"
    assert Path(result["compact_path"]).exists()
    assert result["compact_packet"]["data_quality"]["conflict_count"] == 0
