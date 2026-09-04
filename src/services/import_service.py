import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.services.archive_service import archive_json
from src.services.comparison_service import previous_stock_score, previous_theme_score, score_delta
from src.services.theme_normalizer import normalize_theme
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import (
    Evidence,
    ReviewImport,
    RiskEvent,
    ScoreHistory,
    Stock,
    StockDailyScore,
    StockDriver,
    StockDailyReview,
    ThemeDailyScore,
    ThemeDailyReview,
    ThemeDriver,
    TomorrowCheck,
    TradingDay,
    AnalysisSnapshot,
    ValidationResult,
)
from src.validation.errors import format_validation_error
from src.validation.review_models import DailyReview


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReviewImportError(RuntimeError):
    pass


def infer_exchange(code: str) -> str:
    if code.startswith(("60", "68")):
        return "SSE"
    if code.startswith(("00", "30")):
        return "SZSE"
    return "BSE"


def _set_failed(factory, import_id: int, message: str) -> None:
    with factory.begin() as session:
        record = session.get(ReviewImport, import_id)
        record.status = "failed"
        record.error_json = json.dumps({"message": message}, ensure_ascii=False)
        record.completed_at = datetime.now(UTC)


def import_review(
    source_path: str | Path,
    database_path: str | Path | None = None,
    archive_dir: str | Path | None = None,
) -> dict[str, int | str]:
    source = Path(source_path).resolve()
    raw = source.read_bytes()
    digest, archive_path = archive_json(raw, archive_dir or PROJECT_ROOT / "data" / "archive")
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)

    try:
        unvalidated = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        unvalidated = {}
        validation_message = f"JSON 无法解析：{exc}"
    else:
        validation_message = ""

    with factory.begin() as session:
        audit = ReviewImport(
            source_path=str(source), sha256=digest, archive_path=str(archive_path),
            trade_date=None, data_kind=unvalidated.get("data_kind"), status="pending",
        )
        session.add(audit)
        session.flush()
        import_id = audit.id

    if validation_message:
        _set_failed(factory, import_id, validation_message)
        raise ReviewImportError(validation_message)

    try:
        review = DailyReview.model_validate(unvalidated)
    except ValidationError as exc:
        message = format_validation_error(exc)
        _set_failed(factory, import_id, message)
        raise ReviewImportError(message) from exc

    try:
        counts = _write_review(factory, import_id, review)
    except Exception as exc:
        message = _friendly_database_error(exc)
        _set_failed(factory, import_id, message)
        raise ReviewImportError(message) from exc
    return {"date": review.date.isoformat(), "data_kind": str(review.data_kind), "sha256": digest, **counts}


def _friendly_database_error(exc: Exception) -> str:
    if isinstance(exc, IntegrityError) and "trading_day.trade_date, trading_day.data_kind" in str(exc):
        return "相同日期和数据类型已存在，默认拒绝重复导入"
    return str(exc)


def _write_review(factory, import_id: int, review: DailyReview) -> dict[str, int]:
    with factory.begin() as session:
        duplicate = session.scalar(select(TradingDay.id).where(TradingDay.trade_date == review.date, TradingDay.data_kind == review.data_kind))
        if duplicate is not None:
            raise ReviewImportError("相同日期和数据类型已存在，默认拒绝重复导入")

        day = TradingDay(
            trade_date=review.date, data_kind=review.data_kind, strict_mode=review.strict_mode,
            completeness_score=review.completeness.score,
            missing_items=json.dumps(review.completeness.missing_items, ensure_ascii=False),
            market_regime=review.market_regime, turnover=review.turnover,
            turnover_delta=review.turnover_delta, advancers=review.advancers,
            decliners=review.decliners, limit_up_count=review.limit_up_count,
            limit_down_count=review.limit_down_count, max_board_height=review.max_board_height,
            position_min=review.position_min, position_max=review.position_max, import_id=import_id,
        )
        session.add(day)
        session.flush()
        session.add(
            AnalysisSnapshot(
                trade_date=review.date,
                status="PASSED",
                rule_version=review.schema_version,
                data_version=f"import-{import_id}",
                confidence=review.completeness.score,
                gate_run_id=None,
                result_json=review.model_dump_json(),
            )
        )
        theme_map = {}
        for item in review.main_themes:
            theme = normalize_theme(session, item.name)
            theme_map[item.name] = theme
            previous = previous_theme_score(session, theme.id, review.data_kind, review.date)
            scores = item.scores
            delta = score_delta(previous.total_score if previous else None, scores.total_score)
            session.add(ThemeDailyScore(
                trading_day_id=day.id, theme_id=theme.id, rank_no=item.rank_no,
                stage=item.stage, change_status=item.change_status,
                causal_chain=json.dumps(item.causal_chain, ensure_ascii=False),
                base_logic_score=scores.base_logic_score, realization_score=scores.realization_score,
                expectation_gap_score=scores.expectation_gap_score, persistence_score=scores.persistence_score,
                market_confirmation_score=scores.market_confirmation_score, risk_penalty=scores.risk_penalty,
                total_score=scores.total_score, rating=scores.rating, logic_quality=scores.logic_quality,
                market_strength=scores.market_strength, risk_reward=scores.risk_reward,
                missing_reasons=json.dumps(scores.missing_reasons, ensure_ascii=False),
                delta_score=delta,
                delta_reason=item.delta_reason,
            ))
            session.add(
                ThemeDailyReview(
                    trading_day_id=day.id,
                    theme_id=theme.id,
                    rank_no=item.rank_no,
                    base_logic_score=scores.base_logic_score,
                    realization_score=scores.realization_score,
                    expectation_gap_score=scores.expectation_gap_score,
                    persistence_score=scores.persistence_score,
                    market_confirmation_score=scores.market_confirmation_score,
                    risk_penalty=scores.risk_penalty,
                    total_score=scores.total_score,
                    rating=scores.rating,
                    lifecycle=item.stage,
                    delta_score=delta,
                    delta_reason=item.delta_reason,
                    validation_status="pending",
                )
            )
            session.add(
                ScoreHistory(
                    trade_date=review.date,
                    entity_type="theme",
                    entity_key=item.name,
                    previous_score=previous.total_score if previous else None,
                    current_score=scores.total_score,
                    delta_score=delta,
                    delta_reason=item.delta_reason,
                )
            )
            session.add_all([ThemeDriver(trading_day_id=day.id, theme_id=theme.id, driver_code=d.code, driver_name=d.name, evidence_level=d.evidence_level) for d in item.drivers])

        for item in review.stocks:
            theme = theme_map[item.theme]
            stock = session.get(Stock, item.code)
            if stock is None:
                stock = Stock(stock_code=item.code, stock_name=item.name, exchange=infer_exchange(item.code))
                session.add(stock)
            else:
                stock.stock_name = item.name
            previous = previous_stock_score(session, item.code, theme.id, review.data_kind, review.date)
            scores = item.scores
            delta = score_delta(previous.total_score if previous else None, scores.total_score)
            session.add(StockDailyScore(
                trading_day_id=day.id, stock_code=item.code, theme_id=theme.id,
                role=item.role, role_detail=item.role_detail, stage=item.stage, catalyst=item.catalyst,
                benefit_path=json.dumps(item.benefit_path, ensure_ascii=False),
                causal_chain=json.dumps(item.causal_chain, ensure_ascii=False),
                realization_score=scores.realization_score, expectation_gap=scores.expectation_gap,
                logic_quality=scores.logic_quality, market_strength=scores.market_strength,
                risk_reward=scores.risk_reward, total_score=scores.total_score, rating=scores.rating,
                missing_reasons=json.dumps(scores.missing_reasons, ensure_ascii=False),
                delta_score=delta,
                delta_reason=item.delta_reason,
            ))
            session.add(
                StockDailyReview(
                    trading_day_id=day.id,
                    stock_code=item.code,
                    theme_id=theme.id,
                    role=item.role,
                    lifecycle=item.stage,
                    total_score=scores.total_score,
                    rating=scores.rating,
                    delta_score=delta,
                    delta_reason=item.delta_reason,
                )
            )
            session.add(
                ScoreHistory(
                    trade_date=review.date,
                    entity_type="stock",
                    entity_key=item.code,
                    previous_score=previous.total_score if previous else None,
                    current_score=scores.total_score,
                    delta_score=delta,
                    delta_reason=item.delta_reason,
                )
            )
            session.add_all([StockDriver(trading_day_id=day.id, stock_code=item.code, theme_id=theme.id, driver_code=d.code, driver_name=d.name, evidence_level=d.evidence_level) for d in item.drivers])

        session.add_all([Evidence(trading_day_id=day.id, **item.model_dump()) for item in review.evidence])
        session.add_all([RiskEvent(trading_day_id=day.id, **item.model_dump()) for item in review.risk_events])
        session.add_all([TomorrowCheck(proposed_day_id=day.id, status="pending", **item.model_dump()) for item in review.tomorrow_checks])
        for update in review.tomorrow_check_updates:
            check = session.get(TomorrowCheck, update.check_id)
            if check is None or check.status != "pending":
                raise ValueError(f"tomorrow_check {update.check_id} 不存在或已解决")
            check.status = update.status
            check.result = update.result
            check.resolved_day_id = day.id
            session.add(
                ValidationResult(
                    trade_date=review.date,
                    entity_type=check.entity_type,
                    entity_key=check.entity_key,
                    validation_type=check.check_type,
                    status=update.status,
                    result=update.result,
                    source_check_id=check.id,
                )
            )
        audit = session.get(ReviewImport, import_id)
        audit.trade_date = review.date
        audit.data_kind = review.data_kind
        audit.status = "success"
        audit.completed_at = datetime.now(UTC)
        return {"themes": len(review.main_themes), "stocks": len(review.stocks), "evidence": len(review.evidence), "checks": len(review.tomorrow_checks)}
