from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.constants import DRIVER_TYPES
from src.storage.models import AnalysisSnapshot, ScoreHistory, StockDailyReview, ThemeDailyReview, ThemeDailyScore, ThemeDriver, TomorrowCheck, TradingDay, ValidationResult


def _formal_day_ids(session: Session, limit_days: int | None = None) -> list[int]:
    statement = (
        select(TradingDay.id)
        .join(AnalysisSnapshot, AnalysisSnapshot.trade_date == TradingDay.trade_date)
        .where(TradingDay.data_kind == "real", AnalysisSnapshot.status == "PASSED")
        .order_by(TradingDay.trade_date.desc())
    )
    if limit_days is not None:
        statement = statement.limit(limit_days)
    return list(session.scalars(statement))


def driver_statistics(session: Session, limit_days: int = 20) -> list[dict]:
    day_ids = _formal_day_ids(session, limit_days)
    grouped = defaultdict(lambda: {"scores": [], "sa": 0})
    if day_ids:
        rows = session.execute(select(ThemeDriver, ThemeDailyScore.total_score, ThemeDailyScore.rating).join(ThemeDailyScore, (ThemeDailyScore.trading_day_id == ThemeDriver.trading_day_id) & (ThemeDailyScore.theme_id == ThemeDriver.theme_id)).where(ThemeDriver.trading_day_id.in_(day_ids))).all()
        for driver, score, rating in rows:
            if score is not None:
                grouped[driver.driver_code]["scores"].append(score)
            if rating in {"S+", "S", "A"}:
                grouped[driver.driver_code]["sa"] += 1
            grouped[driver.driver_code]["count"] = grouped[driver.driver_code].get("count", 0) + 1
    return [{"driver_code": code, "driver_name": name, "count": grouped[code].get("count", 0), "average_score": round(sum(grouped[code]["scores"]) / len(grouped[code]["scores"]), 1) if grouped[code]["scores"] else None, "sa_count": grouped[code]["sa"]} for code, name in DRIVER_TYPES.items()]


def lifecycle_statistics(session: Session) -> list[dict]:
    day_ids = _formal_day_ids(session)
    rows = session.execute(
        select(ThemeDailyScore.stage).where(ThemeDailyScore.trading_day_id.in_(day_ids))
    ).scalars()
    counts = Counter(rows)
    return [{"stage": stage, "count": counts[stage]} for stage in ("朦胧期", "发酵期", "验证期", "主升期", "扩散期", "兑现期")]


def rating_sample_statistics(session: Session) -> list[dict]:
    rows = session.execute(select(ThemeDailyReview.rating, ThemeDailyReview.delta_score)).all()
    grouped = defaultdict(lambda: {"count": 0, "deltas": []})
    for rating, delta in rows:
        key = rating or "未评分"
        grouped[key]["count"] += 1
        if delta is not None:
            grouped[key]["deltas"].append(delta)
    ordered = ["S+", "S", "A", "B", "C", "D", "未评分"]
    return [
        {
            "rating": rating,
            "sample_count": grouped[rating]["count"],
            "avg_delta_score": round(sum(grouped[rating]["deltas"]) / len(grouped[rating]["deltas"]), 2) if grouped[rating]["deltas"] else None,
            "next_day_return": None,
            "five_day_return": None,
            "ten_day_return": None,
            "twenty_day_return": None,
            "return_data_status": "pending_price_validation",
        }
        for rating in ordered
        if grouped[rating]["count"]
    ]


def delta_score_statistics(session: Session) -> list[dict]:
    rows = session.execute(select(ScoreHistory.entity_type, ScoreHistory.delta_score)).all()
    grouped = defaultdict(lambda: {"count": 0, "positive": 0, "negative": 0, "flat": 0})
    for entity_type, delta in rows:
        grouped[entity_type]["count"] += 1
        if delta is None or delta == 0:
            grouped[entity_type]["flat"] += 1
        elif delta > 0:
            grouped[entity_type]["positive"] += 1
        else:
            grouped[entity_type]["negative"] += 1
    return [{"entity_type": key, **value} for key, value in sorted(grouped.items())]


def tomorrow_check_statistics(session: Session) -> list[dict]:
    rows = session.execute(select(TomorrowCheck.status)).scalars().all()
    counts = Counter(rows)
    total = sum(counts.values())
    return [
        {
            "status": status,
            "count": counts[status],
            "ratio": round(counts[status] / total * 100, 2) if total else 0,
        }
        for status in ("pending", "confirmed", "partially_confirmed", "weakened", "invalidated")
        if counts[status]
    ]


def stock_role_statistics(session: Session) -> list[dict]:
    rows = session.execute(select(StockDailyReview.role, StockDailyReview.delta_score)).all()
    grouped = defaultdict(lambda: {"count": 0, "deltas": []})
    for role, delta in rows:
        grouped[role]["count"] += 1
        if delta is not None:
            grouped[role]["deltas"].append(delta)
    return [
        {
            "role": role,
            "sample_count": values["count"],
            "avg_delta_score": round(sum(values["deltas"]) / len(values["deltas"]), 2) if values["deltas"] else None,
            "return_data_status": "pending_price_validation",
        }
        for role, values in sorted(grouped.items())
    ]


def validation_results(session: Session) -> list[dict]:
    rows = session.execute(select(ValidationResult).order_by(ValidationResult.trade_date.desc(), ValidationResult.id.desc())).scalars().all()
    return [
        {
            "trade_date": item.trade_date,
            "entity_type": item.entity_type,
            "entity_key": item.entity_key,
            "validation_type": item.validation_type,
            "status": item.status,
            "result": item.result,
        }
        for item in rows
    ]
