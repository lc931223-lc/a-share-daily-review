from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import StockDailyScore, ThemeDailyScore, TradingDay


def previous_theme_score(session: Session, theme_id: int, data_kind: str, before: date):
    return session.scalar(
        select(ThemeDailyScore)
        .join(TradingDay, ThemeDailyScore.trading_day_id == TradingDay.id)
        .where(ThemeDailyScore.theme_id == theme_id, TradingDay.data_kind == data_kind, TradingDay.trade_date < before)
        .order_by(TradingDay.trade_date.desc())
        .limit(1)
    )


def previous_stock_score(session: Session, stock_code: str, theme_id: int, data_kind: str, before: date):
    return session.scalar(
        select(StockDailyScore)
        .join(TradingDay, StockDailyScore.trading_day_id == TradingDay.id)
        .where(StockDailyScore.stock_code == stock_code, StockDailyScore.theme_id == theme_id, TradingDay.data_kind == data_kind, TradingDay.trade_date < before)
        .order_by(TradingDay.trade_date.desc())
        .limit(1)
    )


def score_delta(previous_score: int | None, current_score: int | None) -> int | None:
    if previous_score is None or current_score is None:
        return None
    return current_score - previous_score
