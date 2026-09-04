import json
from datetime import date
from pathlib import Path

import pytest

from src.adapters.cninfo_disclosure import CninfoDisclosureAdapter
from src.adapters.eastmoney_fallback import EastmoneyFallbackAdapter, FallbackScopeError
from src.adapters.tencent_market import TencentMarketAdapter
from src.adapters.ths_market import ThsMarketAdapter
from src.config.runtime import DataPipelineConfig


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "supplemental"


@pytest.fixture
def pipeline_config():
    return DataPipelineConfig.model_validate(
        {
            "rule_version": "test.1",
            "request_timeout_seconds": 15,
            "max_retries": 2,
            "major_indices": ["000001.SH"],
            "thresholds": {
                "security_status_explained": 0.995,
                "daily_quote_required_fields": 0.995,
                "major_index_coverage": 1.0,
                "limit_candidate_coverage": 0.98,
                "supplemental_abs_diff": 2,
                "supplemental_ratio_diff": 0.02,
                "critical_conflicts": 0,
            },
            "eastmoney_fallback_fields": [
                "advancers",
                "decliners",
                "limit_up",
                "limit_down",
                "failed_limit",
                "board_height",
                "theme_name",
                "theme_membership",
            ],
        }
    )


@pytest.fixture
def eastmoney_adapter(pipeline_config):
    payload = json.loads((FIXTURE_ROOT / "eastmoney_breadth.json").read_text("utf-8"))
    return EastmoneyFallbackAdapter(pipeline_config, loader=lambda dataset, trade_date: payload)


def test_eastmoney_rejects_core_dataset(eastmoney_adapter):
    with pytest.raises(FallbackScopeError):
        eastmoney_adapter.fetch("stock_daily", date(2026, 9, 1))


@pytest.mark.parametrize(
    "dataset",
    ["market_breadth", "limit_pool", "failed_limit", "theme_membership"],
)
def test_eastmoney_allows_only_whitelisted_supplements(eastmoney_adapter, dataset):
    record = eastmoney_adapter.fetch(dataset, date(2026, 9, 1))

    assert record.is_fallback is True
    assert record.fallback_reason


def test_cninfo_keeps_official_url():
    payload = json.loads((FIXTURE_ROOT / "cninfo_announcements.json").read_text("utf-8"))
    adapter = CninfoDisclosureAdapter(loader=lambda trade_date: payload)

    announcement = adapter.announcements(date(2026, 9, 1)).payload[0]

    assert announcement["source_url"].startswith("https://")


def test_tencent_quotes_parse_required_fields():
    text = (FIXTURE_ROOT / "tencent_quotes.txt").read_text("utf-8")
    adapter = TencentMarketAdapter(loader=lambda trade_date: text)

    quote = adapter.quotes(date(2026, 9, 1)).payload[0]

    assert quote["code"] == "600001"
    assert quote["name"] == "测试银行"
    assert quote["amount"] > 0


def test_ths_limit_pool_outputs_themes_and_members():
    payload = json.loads((FIXTURE_ROOT / "ths_limit_pool.json").read_text("utf-8"))
    adapter = ThsMarketAdapter(loader=lambda trade_date: payload)

    record = adapter.limit_pool(date(2026, 9, 1))

    assert record.payload[0]["dataset"] == "limit_up"
    assert record.payload[-1]["theme_name"] == "主题甲"
