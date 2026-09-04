import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.storage.models import AnalysisSnapshot, Stock, StockDailyScore, Theme, TradingDay


def search_stocks(session: Session, query: str, limit: int = 20) -> list[dict]:
    pattern = f"%{query.strip()}%"
    rows = session.execute(select(Stock).where(or_(Stock.stock_code.like(pattern), Stock.stock_name.like(pattern))).order_by(Stock.stock_code).limit(limit)).scalars()
    return [{"code": stock.stock_code, "name": stock.stock_name, "exchange": stock.exchange} for stock in rows]


def stock_detail(session: Session, stock_code: str) -> dict | None:
    row = session.execute(
        select(StockDailyScore, Stock.stock_name, Theme.canonical_name, TradingDay.trade_date)
        .join(Stock, StockDailyScore.stock_code == Stock.stock_code)
        .join(Theme, StockDailyScore.theme_id == Theme.id)
        .join(TradingDay, StockDailyScore.trading_day_id == TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(
            StockDailyScore.stock_code == stock_code,
            TradingDay.data_kind == "real",
            AnalysisSnapshot.status == "PASSED",
        )
        .order_by(TradingDay.trade_date.desc()).limit(1)
    ).first()
    if row is None:
        return None
    score, name, theme, trade_date = row
    return {"code": stock_code, "name": name, "theme": theme, "trade_date": trade_date, "role": score.role, "role_detail": score.role_detail, "stage": score.stage, "catalyst": score.catalyst, "benefit_path": json.loads(score.benefit_path), "causal_chain": json.loads(score.causal_chain), "realization_score": score.realization_score, "expectation_gap": score.expectation_gap, "logic_quality": score.logic_quality, "market_strength": score.market_strength, "risk_reward": score.risk_reward, "total_score": score.total_score, "rating": score.rating, "missing_reasons": json.loads(score.missing_reasons)}


def stock_history(session: Session, stock_code: str) -> list[dict]:
    rows = session.execute(
        select(TradingDay.trade_date, StockDailyScore)
        .join(StockDailyScore, StockDailyScore.trading_day_id == TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(
            StockDailyScore.stock_code == stock_code,
            TradingDay.data_kind == "real",
            AnalysisSnapshot.status == "PASSED",
        )
        .order_by(TradingDay.trade_date)
    ).all()
    return [{"trade_date": day, "total_score": score.total_score, "expectation_gap": score.expectation_gap, "market_strength": score.market_strength, "risk_reward": score.risk_reward, "delta_score": score.delta_score, "delta_reason": score.delta_reason} for day, score in rows]
