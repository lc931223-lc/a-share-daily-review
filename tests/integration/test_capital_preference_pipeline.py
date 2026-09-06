from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from src.capital_preference.pipeline import CapitalPreferencePipeline

ROOT = Path(__file__).resolve().parents[2]


class FakeHistory:
    def __init__(self, frame, metadata):
        self.frame = frame
        self.metadata = metadata

    def query(self, start, end, codes=None):
        return self.frame.copy()

    def stock_metadata(self, target):
        return self.metadata


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _inputs(root):
    for name in (
        "capital_preference_packet.schema.json",
        "capital_preference_compact.schema.json",
    ):
        target = root / "schemas" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "schemas" / name, target)
    themes = [
        {
            "theme_name": "科技",
            "theme_amount": 3_000_000,
            "theme_return": 3,
            "theme_inflection_score": 70,
            "top_gainers": [{"stock_code": "000001"}],
            "capacity_candidates": [{"stock_code": "000001"}],
        }
    ]
    intelligence = {
        "meta": {"trade_date": "2026-09-04"},
        "theme_features": themes,
        "role_candidates": [
            {
                "ts_code": "000001.SZ",
                "theme": "科技",
                "role_candidate": "CAPACITY_CANDIDATE",
                "all_role_candidates": ["CAPACITY_CANDIDATE"],
                "role_candidate_score": 80,
            }
        ],
        "style_strength_ranking": [{"style": "value", "style_strength_score": 60}],
        "data_quality": {"status": "PASS"},
    }
    market = {
        "meta": {"trade_date": "2026-09-04"},
        "stocks": [
            {
                "stock_code": "000001",
                "market_cap": 10_000_000_000,
                "turnover_rate": 5,
            }
        ],
        "announcements": {"records": []},
        "policies": {"records": []},
        "data_quality": {
            "status": "PASS",
            "checks": [
                {"item": "公告", "status": "PASS"},
                {"item": "政策", "status": "PASS"},
            ],
        },
    }
    inflection = {
        "meta": {"trade_date": "2026-09-04"},
        "candidates": [],
        "data_quality": {"status": "PASS"},
    }
    auction = {
        "meta": {"trade_date": "2026-09-04"},
        "stock_auction_summary": [],
        "data_quality": {"status": "PASS"},
    }
    official = {
        "date": "2026-09-04",
        "data_kind": "real",
        "market_commentary": [],
    }
    for folder, payload in (
        ("review_intelligence", intelligence),
        ("market_packets", market),
        ("inflection", inflection),
        ("auction_packets", auction),
        ("official_reviews", official),
    ):
        _write(root / "data" / folder / "2026-09-04.json", payload)


def _history():
    rows = []
    dates = pd.bdate_range(end="2026-09-04", periods=280)
    for index, timestamp in enumerate(dates):
        rows.append(
            {
                "trade_date": timestamp.date().isoformat(),
                "ts_code": "000001.SZ",
                "close": 10 + index / 100,
                "amount": 1_000_000 + index,
                "pct_chg": 0.5,
            }
        )
    return pd.DataFrame(rows), {"000001.SZ": {"stock_name": "测试", "industry": "科技"}}


def test_pipeline_outputs_objective_full_and_compact_packets(tmp_path):
    _inputs(tmp_path)
    frame, metadata = _history()
    result = CapitalPreferencePipeline(
        tmp_path, history_repository=FakeHistory(frame, metadata)
    ).run(date(2026, 9, 4))
    compact = result["compact"]
    assert {
        "theme_capital_preference",
        "stock_capital_preference",
        "why_capital_selected",
        "capacity_structure",
        "crowding_status",
    } <= compact.keys()
    assert compact["review_section_support"]["title"] == "资金青睐逻辑拆解"
    assert result["packet"]["meta"]["final_judgement_owner"] == "chatgpt"
    assert result["packet"]["data_quality"]["status"] == "PARTIAL"
    text = json.dumps(result["packet"], ensure_ascii=False)
    for phrase in ("买入建议", "上涨预测", "仓位建议", "确定主线"):
        assert phrase not in text


def test_pipeline_rejects_cross_date_market_packet(tmp_path):
    _inputs(tmp_path)
    path = tmp_path / "data" / "market_packets" / "2026-09-04.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["meta"]["trade_date"] = "2026-09-03"
    _write(path, payload)
    frame, metadata = _history()
    pipeline = CapitalPreferencePipeline(tmp_path, history_repository=FakeHistory(frame, metadata))
    import pytest

    with pytest.raises(ValueError, match="date mismatch"):
        pipeline.run(date(2026, 9, 4))
