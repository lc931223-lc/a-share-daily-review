
from dataclasses import dataclass

from src.domain.scoring import calculate_total, rating_for_score

@dataclass
class ScoreInput:
    base_logic: int
    realization: int
    expectation_gap: int
    persistence: int
    market_confirmation: int
    risk_penalty: int = 0

def total_score(x: ScoreInput) -> int:
    return calculate_total(
        {
            "base_logic": x.base_logic,
            "realization": x.realization,
            "expectation_gap": x.expectation_gap,
            "persistence": x.persistence,
            "market_confirmation": x.market_confirmation,
            "risk_penalty": x.risk_penalty,
        }
    )

def rating(score: int) -> str:
    return rating_for_score(score)
