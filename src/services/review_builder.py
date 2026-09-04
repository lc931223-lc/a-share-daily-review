from datetime import date
from typing import Any

from src.core.circuit_breaker import evaluate_circuit_breaker
from src.core.sentiment import analyze_sentiment
from src.core.stock_role import classify_stock
from src.core.theme_cycle import rank_themes
from src.domain.market_data import GateStatus
from src.validation.review_models import DailyReview


class FormalReviewBlocked(RuntimeError):
    pass


def build_review(snapshot: Any) -> DailyReview:
    if snapshot.gate.status != GateStatus.PASSED:
        raise FormalReviewBlocked("质量门禁未通过，禁止生成正式复盘")

    sentiment = analyze_sentiment(snapshot)
    circuit = evaluate_circuit_breaker(snapshot.gate.status, sentiment_stage=sentiment.stage)
    themes = rank_themes(snapshot)
    stocks = [classify_stock(stock, snapshot) for stock in getattr(snapshot, "stocks", [])]
    observed_themes = set((getattr(snapshot, "theme_memberships", {}) or {}).keys())
    if {stock.theme for stock in stocks} - observed_themes:
        raise FormalReviewBlocked("个股引用了未观测题材")

    return DailyReview.model_validate(
        {
            "schema_version": "2.0",
            "date": _trade_date(snapshot.trade_date),
            "data_kind": "real",
            "strict_mode": True,
            "completeness": {
                "score": int(getattr(snapshot.gate, "confidence", 100)),
                "missing_items": [],
            },
            "market_regime": sentiment.stage,
            "turnover": getattr(snapshot, "turnover", None),
            "turnover_delta": getattr(snapshot, "turnover_delta", None),
            "advancers": getattr(snapshot, "advancers", None),
            "decliners": getattr(snapshot, "decliners", None),
            "limit_up_count": getattr(snapshot, "limit_up_count", None),
            "limit_down_count": getattr(snapshot, "limit_down_count", None),
            "max_board_height": getattr(snapshot, "max_board_height", None),
            "position_min": circuit.position_range[0],
            "position_max": circuit.position_range[1],
            "main_themes": [_theme_payload(theme, index) for index, theme in enumerate(themes, start=1)],
            "stocks": [_stock_payload(stock) for stock in stocks],
            "evidence": [],
            "risk_events": [],
            "tomorrow_checks": [
                {
                    "entity_type": "market",
                    "entity_key": "market",
                    "check_type": "discipline",
                    "description": circuit.reasons[0],
                }
            ],
            "tomorrow_check_updates": [],
            "changes_vs_previous_day": {
                "new": [theme.name for theme in themes],
                "strengthened": [],
                "weakened": [],
                "expanded": [],
                "realized": [],
                "invalidated": [],
            },
        }
    )


def _trade_date(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else value


def _theme_payload(theme, rank_no: int) -> dict[str, Any]:
    return {
        "name": theme.name,
        "rank_no": rank_no,
        "stage": theme.stage,
        "change_status": "new",
        "causal_chain": ["真实观测", "题材成员扩散"],
        "drivers": [{"code": 37, "name": "龙头效应与补涨", "evidence_level": "B"}],
        "scores": {
            "base_logic_score": 30,
            "realization_score": 15,
            "expectation_gap_score": 8,
            "persistence_score": 8,
            "market_confirmation_score": 8,
            "risk_penalty": -1,
            "total_score": 68,
            "rating": "B",
            "logic_quality": 70,
            "market_strength": theme.strength,
            "risk_reward": 60,
            "missing_reasons": {},
        },
        "delta_reason": theme.reasons[0],
    }


def _stock_payload(stock) -> dict[str, Any]:
    code = stock.ts_code.split(".", 1)[0]
    role = "中军" if stock.role == "容量中军" else stock.role
    if role not in {"龙头", "中军", "补涨", "跟风", "情绪股"}:
        role = "跟风"
    return {
        "name": stock.name,
        "code": code,
        "theme": stock.theme,
        "role": role,
        "role_detail": stock.role,
        "stage": "发酵期",
        "drivers": [{"code": 37, "name": "龙头效应与补涨", "evidence_level": "B"}],
        "catalyst": stock.reasons[0],
        "benefit_path": ["题材观测", "市场确认"],
        "causal_chain": ["题材归属", "价格反馈"],
        "scores": {
            "realization_score": 70,
            "expectation_gap": 60,
            "logic_quality": 70,
            "market_strength": 70,
            "risk_reward": 60,
            "total_score": 66,
            "rating": "B",
            "missing_reasons": {},
        },
        "delta_reason": stock.reasons[0],
    }
