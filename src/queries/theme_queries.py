import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import AnalysisSnapshot, Theme, ThemeDailyScore, ThemeDriver, TradingDay


def list_themes(session: Session) -> list[Theme]:
    return list(session.scalars(select(Theme).order_by(Theme.canonical_name)))


def theme_detail(session: Session, theme_id: int) -> dict | None:
    row = session.execute(
        select(ThemeDailyScore, Theme.canonical_name, TradingDay.trade_date)
        .join(Theme, ThemeDailyScore.theme_id == Theme.id)
        .join(TradingDay, ThemeDailyScore.trading_day_id == TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(
            ThemeDailyScore.theme_id == theme_id,
            TradingDay.data_kind == "real",
            AnalysisSnapshot.status == "PASSED",
        )
        .order_by(TradingDay.trade_date.desc()).limit(1)
    ).first()
    if row is None:
        return None
    score, name, trade_date = row
    drivers = session.execute(select(ThemeDriver.driver_code, ThemeDriver.driver_name, ThemeDriver.evidence_level).where(ThemeDriver.trading_day_id == score.trading_day_id, ThemeDriver.theme_id == theme_id)).all()
    return {"name": name, "trade_date": trade_date, "stage": score.stage, "change_status": score.change_status, "causal_chain": json.loads(score.causal_chain), "scores": {key: getattr(score, key) for key in ("base_logic_score", "realization_score", "expectation_gap_score", "persistence_score", "market_confirmation_score", "risk_penalty", "total_score", "logic_quality", "market_strength", "risk_reward")}, "rating": score.rating, "delta_score": score.delta_score, "delta_reason": score.delta_reason, "missing_reasons": json.loads(score.missing_reasons), "drivers": [{"code": code, "name": driver, "evidence_level": level} for code, driver, level in drivers]}


def theme_history(session: Session, theme_id: int) -> list[dict]:
    rows = session.execute(
        select(TradingDay.trade_date, ThemeDailyScore)
        .join(ThemeDailyScore, ThemeDailyScore.trading_day_id == TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(
            ThemeDailyScore.theme_id == theme_id,
            TradingDay.data_kind == "real",
            AnalysisSnapshot.status == "PASSED",
        )
        .order_by(TradingDay.trade_date)
    ).all()
    return [{"trade_date": trade_date, "stage": score.stage, "total_score": score.total_score, "base_logic_score": score.base_logic_score, "realization_score": score.realization_score, "expectation_gap_score": score.expectation_gap_score, "persistence_score": score.persistence_score, "market_confirmation_score": score.market_confirmation_score, "risk_reward": score.risk_reward, "delta_score": score.delta_score, "delta_reason": score.delta_reason} for trade_date, score in rows]
