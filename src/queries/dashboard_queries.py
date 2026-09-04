import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.storage.models import (
    AnalysisSnapshot,
    Stock,
    StockDailyScore,
    Theme,
    ThemeDailyScore,
    TomorrowCheck,
    TradingDay,
)


def _formal_real_days():
    return (
        select(TradingDay)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(TradingDay.data_kind == "real", AnalysisSnapshot.status == "PASSED")
    )


def list_days(session: Session) -> list[TradingDay]:
    return list(session.scalars(_formal_real_days().order_by(TradingDay.trade_date.desc())))


def latest_day(session: Session) -> TradingDay | None:
    return session.scalar(_formal_real_days().order_by(TradingDay.trade_date.desc()).limit(1))


def get_day(session: Session, trade_date: date) -> TradingDay | None:
    return session.scalar(_formal_real_days().where(TradingDay.trade_date == trade_date))


def market_summary(day: TradingDay | None) -> dict | None:
    if day is None:
        return None
    return {
        "id": day.id, "trade_date": day.trade_date, "data_kind": day.data_kind,
        "strict_mode": day.strict_mode, "completeness_score": day.completeness_score,
        "missing_items": json.loads(day.missing_items), "market_regime": day.market_regime,
        "turnover": day.turnover, "turnover_delta": day.turnover_delta,
        "advancers": day.advancers, "decliners": day.decliners,
        "limit_up_count": day.limit_up_count, "limit_down_count": day.limit_down_count,
        "max_board_height": day.max_board_height, "position_min": day.position_min,
        "position_max": day.position_max,
    }


def top_themes(session: Session, day_id: int, limit: int = 5) -> list[dict]:
    rows = session.execute(
        select(ThemeDailyScore, Theme.canonical_name)
        .join(Theme, ThemeDailyScore.theme_id == Theme.id)
        .where(ThemeDailyScore.trading_day_id == day_id)
        .order_by(ThemeDailyScore.rank_no)
        .limit(limit)
    ).all()
    return [{
        "theme_id": score.theme_id, "name": name, "rank_no": score.rank_no,
        "stage": score.stage, "change_status": score.change_status,
        "total_score": score.total_score, "rating": score.rating,
        "delta_score": score.delta_score, "delta_reason": score.delta_reason,
        "missing_reasons": json.loads(score.missing_reasons),
    } for score, name in rows]


def check_summary(session: Session, day_id: int) -> dict[str, int]:
    result = {key: 0 for key in ("pending", "confirmed", "weakened", "invalidated")}
    rows = session.execute(select(TomorrowCheck.status, func.count()).where(TomorrowCheck.proposed_day_id == day_id).group_by(TomorrowCheck.status)).all()
    result.update({status: count for status, count in rows})
    return result


def core_stocks_by_theme(session: Session, day_id: int) -> dict[int, str]:
    rows = session.execute(
        select(StockDailyScore.theme_id, Stock.stock_name, StockDailyScore.role)
        .join(Stock, StockDailyScore.stock_code == Stock.stock_code)
        .where(StockDailyScore.trading_day_id == day_id)
        .order_by(StockDailyScore.theme_id, StockDailyScore.id)
    ).all()
    grouped: dict[int, list[str]] = {}
    for theme_id, stock_name, role in rows:
        grouped.setdefault(theme_id, []).append(f"{stock_name}（{role}）")
    return {theme_id: " / ".join(items) for theme_id, items in grouped.items()}
