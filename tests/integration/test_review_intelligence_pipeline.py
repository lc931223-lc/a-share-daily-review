import json
from datetime import date

import pandas as pd

from src.review_intelligence.pipeline import ReviewIntelligencePipeline


class FakeHistory:
    def query(self, start, end, codes=None):
        rows = []
        for offset, day in enumerate(("2026-09-03", "2026-09-04")):
            for index in range(60):
                rows.append({
                    "trade_date": day, "ts_code": f"{index:06d}.SZ", "open": 10,
                    "high": 11, "low": 9.8, "close": 10.5, "pre_close": 10,
                    "pct_chg": 5 if offset else 0, "vol": 1000, "amount": 100000 + index,
                    "turnover_rate": None,
                })
        return pd.DataFrame(rows)

    def stock_metadata(self, target):
        return {f"{index:06d}.SZ": {"stock_name": f"S{index}", "industry": "tech"} for index in range(60)}


def test_pipeline_outputs_compact_contract_without_final_judgement(tmp_path):
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    market = {
        "meta": {"trade_date": "2026-09-04"},
        "market_overview": {"total_market_turnover": 6_000_000, "turnover_delta_pct": 5,
            "rise_count": 45, "fall_count": 15, "limit_up_count": 8, "limit_down_count": 0,
            "failed_limit_count": 2, "seal_rate": 80, "highest_board": 3,
            "previous_limit_up_avg_change_pct": 1,
            "previous_continuous_board_performance": {"avg_change_pct": 2, "red_rate": 70}},
        "indices": [], "stocks": [], "themes": [], "announcements": {"records": []},
        "previous_review": {"themes": []}, "data_quality": {"status": "PASS"},
    }
    (packet_dir / "2026-09-04.json").write_text(json.dumps(market), encoding="utf-8")
    result = ReviewIntelligencePipeline(tmp_path, history_repository=FakeHistory()).run(date(2026, 9, 4))
    compact = result["compact"]
    required = {"market_operability", "cycle_candidates", "style_strength_ranking",
        "theme_concentration", "top_theme_features", "role_candidates", "money_effect_features",
        "trend_chip_candidates", "positive_catalyst_fatigue", "next_day_plan_candidates",
        "objective_factor_features", "previous_hypothesis_validation",
        "risk_and_falsification_candidates", "historical_changes", "data_quality"}
    assert required <= compact.keys()
    assert "final_market_stage" not in json.dumps(compact)
    assert len(compact["next_day_plan_candidates"]) <= 20
    assert compact["previous_hypothesis_validation"]["prior_official_review"]["status"] == "UNAVAILABLE"
