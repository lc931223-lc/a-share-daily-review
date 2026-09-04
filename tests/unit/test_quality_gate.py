from types import SimpleNamespace

import pytest

from src.config.runtime import DataPipelineConfig
from src.domain.market_data import GateStatus
from src.services.quality_gate import QualityGate


@pytest.fixture
def config():
    return DataPipelineConfig.model_validate(
        {
            "rule_version": "2026.09.02.1",
            "request_timeout_seconds": 15,
            "max_retries": 2,
            "major_indices": ["000001.SH", "399001.SZ"],
            "thresholds": {
                "security_status_explained": 0.995,
                "daily_quote_required_fields": 0.995,
                "major_index_coverage": 1.0,
                "limit_candidate_coverage": 0.98,
                "supplemental_abs_diff": 2,
                "supplemental_ratio_diff": 0.02,
                "critical_conflicts": 0,
            },
            "eastmoney_fallback_fields": ["advancers"],
        }
    )


@pytest.fixture
def complete_snapshot():
    return SimpleNamespace(
        is_trading_day=True,
        trade_date_consistent=True,
        security_status_explained=0.997,
        daily_required_coverage=0.999,
        major_index_coverage=1.0,
        limit_candidate_coverage=0.99,
        supplemental_abs_diff=1,
        supplemental_ratio_diff=0.01,
        critical_conflicts=0,
        missing_enhancements=[],
    )


@pytest.fixture
def incomplete_snapshot(complete_snapshot):
    return SimpleNamespace(**vars(complete_snapshot))


def failed_check_names(decision):
    return {check.name for check in decision.checks if not check.passed}


def test_complete_close_snapshot_passes(complete_snapshot, config):
    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="close")

    assert decision.status == GateStatus.PASSED
    assert decision.confidence == 100


def test_missing_core_daily_data_fails(incomplete_snapshot, config):
    incomplete_snapshot.daily_required_coverage = 0.98

    decision = QualityGate(config).evaluate(incomplete_snapshot, report_mode="close")

    assert decision.status == GateStatus.FAILED
    assert "daily_quote_required_fields" in failed_check_names(decision)


def test_intraday_snapshot_is_draft_only(complete_snapshot, config):
    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="intraday")

    assert decision.status == GateStatus.DRAFT_ONLY


def test_enhancement_gap_reduces_confidence_but_does_not_fail(complete_snapshot, config):
    complete_snapshot.missing_enhancements = ["公告催化", "资金流"]

    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="close")

    assert decision.status == GateStatus.PASSED
    assert decision.confidence == 80


def test_critical_conflict_fails(complete_snapshot, config):
    complete_snapshot.critical_conflicts = 1

    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="close")

    assert decision.status == GateStatus.FAILED
    assert "critical_conflicts" in failed_check_names(decision)
