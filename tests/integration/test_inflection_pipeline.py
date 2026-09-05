from datetime import date, timedelta
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from src.inflection.pipeline import InflectionPipeline
from src.storage.database import create_db_engine, session_factory
from src.storage.models import QualityGateRun, SourceBatch, SourceObservation


class FakeHistoryRepository:
    def __init__(self, target: date):
        rows = []
        start = target - timedelta(days=300)
        for stock in range(50):
            code = f"{stock + 1:06d}.SZ"
            for index in range(280):
                close = 10 + stock * 0.01 + index * 0.005
                rows.append({
                    "trade_date": (start + timedelta(days=index)).isoformat(), "ts_code": code,
                    "open": close * 0.99, "high": close * 1.01, "low": close * 0.98,
                    "close": close, "pre_close": close / 1.001, "pct_chg": 0.1,
                    "vol": 1_000_000 + index, "amount": 10_000_000 + index * 1000,
                    "turnover_rate": 2.0,
                })
            rows[-1]["trade_date"] = target.isoformat()
            rows[-1]["amount"] = 40_000_000
            rows[-1]["close"] *= 1.08
            rows.append({**rows[-1], "trade_date": (target + timedelta(days=1)).isoformat(), "close": 9999})
        self.frame = pd.DataFrame(rows)

    def ensure_history(self, target):
        return {"requested_dates": 280, "cached_dates": 280, "loaded_dates": 0, "failed_dates": []}

    def query(self, start, end, codes=None):
        return self.frame.copy()

    def stock_metadata(self, target):
        return {f"{stock + 1:06d}.SZ": {"stock_name": f"股票{stock + 1}", "industry": "测试行业", "themes": ["测试主题"]} for stock in range(50)}


def test_inflection_pipeline_scans_50_stocks_without_future_pollution(tmp_path):
    target = date(2026, 9, 4)
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "2026-09-04.json").write_text(json.dumps({"announcements": {"records": []}}), encoding="utf-8")
    pipeline = InflectionPipeline(root=tmp_path, history_repository=FakeHistoryRepository(target))

    result = pipeline.run(target, scan_limit=50)

    assert result["packet"]["scan_summary"]["scanned_count"] == 50
    assert Path(result["paths"]["full"]).exists()
    assert Path(result["paths"]["compact"]).exists()
    assert all(item["close"] != 9999 for item in pipeline.fact_store.read_dataset("inflection_daily", target))
    assert all(item["status"] not in {"TREND_BROKEN", "DISTRIBUTION_WARNING"} for item in result["compact"]["top_new_inflections"])
    factory = session_factory(create_db_engine(tmp_path / "data" / "a_share_review.db"))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceBatch)) == 1
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 50
        assert session.scalar(select(func.count()).select_from(QualityGateRun)) == 1
