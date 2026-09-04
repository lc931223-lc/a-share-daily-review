from dataclasses import dataclass

from src.domain.market_data import GateStatus


@dataclass(frozen=True)
class CircuitBreakerResult:
    action: str
    position_range: tuple[int, int]
    reasons: list[str]


def evaluate_circuit_breaker(
    gate_status: GateStatus,
    *,
    sentiment_stage: str,
    consecutive_losses: int = 0,
    drawdown_pct: float = 0.0,
) -> CircuitBreakerResult:
    if gate_status != GateStatus.PASSED:
        return CircuitBreakerResult("禁止开仓", (0, 0), ["数据门禁未通过"])
    if consecutive_losses >= 3 or drawdown_pct <= -5:
        return CircuitBreakerResult("暂停交易", (0, 0), ["亏损或回撤触发纪律熔断"])
    if sentiment_stage == "退潮":
        return CircuitBreakerResult("降低仓位", (0, 3), ["市场情绪退潮"])
    if sentiment_stage == "冰点":
        return CircuitBreakerResult("只观察", (0, 2), ["市场情绪处于冰点"])
    return CircuitBreakerResult("按计划交易", (3, 5), ["数据门禁通过且情绪未触发熔断"])
