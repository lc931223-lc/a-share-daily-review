from src.core.circuit_breaker import evaluate_circuit_breaker
from src.domain.market_data import GateStatus


def test_gate_failure_blocks_opening_positions():
    result = evaluate_circuit_breaker(GateStatus.FAILED, sentiment_stage="修复")

    assert result.action == "禁止开仓"
    assert result.reasons


def test_decline_reduces_position():
    result = evaluate_circuit_breaker(GateStatus.PASSED, sentiment_stage="退潮")

    assert result.action == "降低仓位"
