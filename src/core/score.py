
from dataclasses import dataclass

@dataclass
class ScoreInput:
    base_logic: int
    realization: int
    expectation_gap: int
    persistence: int
    market_confirmation: int
    risk_penalty: int = 0

def total_score(x: ScoreInput) -> int:
    values = [
        max(0, min(40, x.base_logic)),
        max(0, min(25, x.realization)),
        max(0, min(15, x.expectation_gap)),
        max(0, min(10, x.persistence)),
        max(0, min(10, x.market_confirmation)),
        max(-20, min(0, x.risk_penalty)),
    ]
    return sum(values)

def rating(score: int) -> str:
    if score >= 90: return "S+"
    if score >= 80: return "S"
    if score >= 70: return "A"
    if score >= 60: return "B"
    if score >= 45: return "C"
    return "D"
