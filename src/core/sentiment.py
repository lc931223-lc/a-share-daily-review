from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SentimentResult:
    stage: str
    temperature: int
    suggested_position: tuple[int, int]
    reasons: list[str]
    conflicts: list[str]


def analyze_sentiment(snapshot: Any) -> SentimentResult:
    advancers = int(getattr(snapshot, "advancers", 0) or 0)
    decliners = int(getattr(snapshot, "decliners", 0) or 0)
    limit_up = int(getattr(snapshot, "limit_up_count", 0) or 0)
    limit_down = int(getattr(snapshot, "limit_down_count", 0) or 0)
    failed = int(getattr(snapshot, "failed_limit_count", 0) or 0)
    max_board = int(getattr(snapshot, "max_board_height", 0) or 0)
    index_pct = float(getattr(snapshot, "index_pct_chg", 0) or 0)

    breadth_total = max(1, advancers + decliners)
    breadth_score = round(40 * advancers / breadth_total)
    limit_score = min(25, limit_up // 4) - min(15, limit_down * 2)
    board_score = min(15, max_board * 2)
    index_score = 10 if index_pct > 0 else -5
    failed_penalty = min(20, failed)
    temperature = max(0, min(100, 30 + breadth_score + limit_score + board_score + index_score - failed_penalty))

    if temperature >= 75:
        stage = "主升"
        position = (5, 7)
    elif temperature >= 60:
        stage = "修复"
        position = (3, 5)
    elif failed > limit_up * 0.25:
        stage = "分歧"
        position = (2, 4)
    elif temperature <= 35:
        stage = "冰点"
        position = (0, 2)
    else:
        stage = "退潮"
        position = (0, 3)

    reasons = [
        f"上涨家数 {advancers}、下跌家数 {decliners}",
        f"涨停 {limit_up}、跌停 {limit_down}、炸板 {failed}",
        f"最高连板 {max_board}，指数涨跌幅 {index_pct}",
    ]
    return SentimentResult(stage, temperature, position, reasons, [])
