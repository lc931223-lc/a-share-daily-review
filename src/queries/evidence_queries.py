from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import AnalysisSnapshot, Evidence, TradingDay


def evidence_list(session: Session, level: str | None = None, verified: bool | None = None) -> list[dict]:
    statement = (
        select(Evidence, TradingDay.trade_date)
        .join(TradingDay, Evidence.trading_day_id == TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(TradingDay.data_kind == "real", AnalysisSnapshot.status == "PASSED")
    )
    if level:
        statement = statement.where(Evidence.evidence_level == level)
    if verified is not None:
        statement = statement.where(Evidence.verified == verified)
    rows = session.execute(statement.order_by(TradingDay.trade_date.desc(), Evidence.id.desc())).all()
    return [{"id": item.id, "trade_date": day, "entity_type": item.entity_type, "entity_key": item.entity_key, "evidence_level": item.evidence_level, "evidence_type": item.evidence_type, "title": item.title, "source_name": item.source_name, "source_url": item.source_url, "published_at": item.published_at, "excerpt": item.excerpt, "verified": item.verified} for item, day in rows]
