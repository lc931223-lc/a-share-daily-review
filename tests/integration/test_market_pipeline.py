from datetime import UTC, date, datetime
from unittest.mock import Mock

from src.adapters.base import AdapterPermissionError, AdapterTimeout
from src.config.runtime import DataPipelineConfig
from src.domain.market_data import GateStatus, SourceName, SourceRecord
from src.services.market_pipeline import MarketPipeline


def config():
    return DataPipelineConfig.model_validate(
        {
            "rule_version": "2026.09.02.1",
            "primary_market_source": "tushare",
            "tushare_role": "required_primary",
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


def record(source, dataset):
    return SourceRecord(
        source=source,
        dataset=dataset,
        trade_date=date(2026, 9, 1),
        fetched_at=datetime.now(UTC),
        payload=[{"ok": True}],
    )


def build_pipeline(tmp_path):
    tushare = Mock()
    tushare.trade_calendar.return_value = SourceRecord(
        source=SourceName.TUSHARE,
        dataset="trade_cal",
        trade_date=date(2026, 9, 1),
        fetched_at=datetime.now(UTC),
        payload=[{"cal_date": "20260901", "is_open": 1}],
    )
    tushare.stock_basic.return_value = record(SourceName.TUSHARE, "stock_basic")
    tushare.stock_daily.return_value = record(SourceName.TUSHARE, "daily")
    tushare.index_daily.return_value = record(SourceName.TUSHARE, "index_daily")
    tushare.adj_factor.return_value = record(SourceName.TUSHARE, "adj_factor")
    ths = Mock()
    ths.limit_pool.return_value = record(SourceName.THS, "limit_pool")
    tencent = Mock()
    tencent.quotes.return_value = record(SourceName.TENCENT, "quotes")
    cninfo = Mock()
    cninfo.announcements.return_value = record(SourceName.CNINFO, "announcements")
    eastmoney = Mock()
    fallback = record(SourceName.EASTMONEY, "limit_pool")
    fallback = fallback.model_copy(
        update={"is_fallback": True, "fallback_reason": "supplemental source unavailable"}
    )
    eastmoney.fetch.return_value = fallback
    pipeline = MarketPipeline(
        config=config(),
        tushare=tushare,
        ths=ths,
        tencent=tencent,
        cninfo=cninfo,
        eastmoney=eastmoney,
        database_path=tmp_path / "pipeline.db",
    )
    return pipeline


def build_eastmoney_primary_pipeline(tmp_path):
    ths = Mock()
    ths.limit_pool.return_value = record(SourceName.THS, "limit_pool")
    tencent = Mock()
    tencent.quotes.return_value = record(SourceName.TENCENT, "quotes")
    cninfo = Mock()
    cninfo.announcements.return_value = record(SourceName.CNINFO, "announcements")
    eastmoney = Mock()
    eastmoney.trade_calendar.return_value = SourceRecord(
        source=SourceName.EASTMONEY,
        dataset="trade_calendar",
        trade_date=date(2026, 9, 1),
        fetched_at=datetime.now(UTC),
        payload=[{"cal_date": "20260901", "is_open": 1}],
    )
    eastmoney.stock_basic.return_value = record(SourceName.EASTMONEY, "stock_basic")
    eastmoney.stock_daily.return_value = record(SourceName.EASTMONEY, "daily")
    eastmoney.index_daily.return_value = record(SourceName.EASTMONEY, "index_daily")
    eastmoney.fetch.return_value = record(SourceName.EASTMONEY, "limit_pool")
    eastmoney.fetch.return_value = eastmoney.fetch.return_value.model_copy(
        update={"is_fallback": True, "fallback_reason": "supplemental source unavailable"}
    )
    pipeline_config = config().model_copy(
        update={"primary_market_source": "eastmoney", "tushare_role": "optional_cross_check"}
    )
    return MarketPipeline(
        config=pipeline_config,
        tushare=None,
        ths=ths,
        tencent=tencent,
        cninfo=cninfo,
        eastmoney=eastmoney,
        database_path=tmp_path / "pipeline-eastmoney.db",
    )


def test_pipeline_uses_eastmoney_only_after_supplement_failure(tmp_path):
    pipeline = build_pipeline(tmp_path)
    pipeline.ths.limit_pool.side_effect = AdapterTimeout("ths", "limit_pool")

    result = pipeline.collect(date(2026, 9, 1), mode="close")

    assert result.fallbacks[0].fallback_source == "eastmoney"
    assert result.fallbacks[0].fields == ["limit_up", "limit_down", "failed_limit"]
    pipeline.eastmoney.fetch.assert_called_once()


def test_pipeline_never_falls_back_for_tushare_daily(tmp_path):
    pipeline = build_pipeline(tmp_path)
    pipeline.tushare.stock_daily.side_effect = AdapterPermissionError("daily")

    result = pipeline.collect(date(2026, 9, 1), mode="close")

    assert result.gate.status == GateStatus.FAILED
    pipeline.eastmoney.fetch.assert_not_called()


def test_pipeline_complete_close_passes(tmp_path):
    pipeline = build_pipeline(tmp_path)

    result = pipeline.collect(date(2026, 9, 1), mode="close")

    assert result.gate.status == GateStatus.PASSED
    assert result.snapshot is not None
    assert result.snapshot.status == "PASSED"


def test_pipeline_uses_eastmoney_as_default_primary_without_tushare(tmp_path):
    pipeline = build_eastmoney_primary_pipeline(tmp_path)

    result = pipeline.collect(date(2026, 9, 1), mode="close")

    assert result.gate.status == GateStatus.PASSED
    pipeline.eastmoney.stock_daily.assert_called_once()
    assert pipeline.tushare is None
