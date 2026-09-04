from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewImport(Base):
    __tablename__ = "review_import"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    archive_path: Mapped[str] = mapped_column(Text)
    trade_date: Mapped[date | None] = mapped_column(Date)
    data_kind: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SourceBatch(Base):
    __tablename__ = "source_batch"
    __table_args__ = (
        Index("idx_source_batch_source_date", "source_name", "trade_date"),
        UniqueConstraint("sha256", "archive_path", name="uq_source_batch_archive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(30))
    dataset: Mapped[str] = mapped_column(String(100))
    trade_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    sha256: Mapped[str] = mapped_column(String(64))
    archive_path: Mapped[str] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_category: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SourceObservation(Base):
    __tablename__ = "source_observation"
    __table_args__ = (
        Index("idx_source_observation_entity", "entity_type", "entity_key", "field_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("source_batch.id"))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_key: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(100))
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30))
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_reason: Mapped[str | None] = mapped_column(Text)
    conflict_status: Mapped[str] = mapped_column(String(30), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class QualityGateRun(Base):
    __tablename__ = "quality_gate_run"
    __table_args__ = (Index("idx_quality_gate_run_date", "trade_date", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    rule_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[int] = mapped_column(Integer)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class QualityGateCheck(Base):
    __tablename__ = "quality_gate_check"
    __table_args__ = (
        UniqueConstraint("gate_run_id", "check_name", name="uq_quality_gate_check_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    gate_run_id: Mapped[int] = mapped_column(ForeignKey("quality_gate_run.id"))
    check_name: Mapped[str] = mapped_column(String(100))
    actual_value: Mapped[str] = mapped_column(Text)
    threshold_value: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)


class SourceFallback(Base):
    __tablename__ = "source_fallback"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    primary_source: Mapped[str] = mapped_column(String(30))
    fallback_source: Mapped[str] = mapped_column(String(30))
    dataset: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    fields_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    coverage: Mapped[float | None] = mapped_column(Float)
    cross_validation_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshot"
    __table_args__ = (
        Index("idx_analysis_snapshot_date_status", "trade_date", "status"),
        UniqueConstraint("trade_date", "data_version", name="uq_analysis_snapshot_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    rule_version: Mapped[str] = mapped_column(String(50))
    data_version: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[int] = mapped_column(Integer)
    gate_run_id: Mapped[int | None] = mapped_column(ForeignKey("quality_gate_run.id"))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TradingDay(Base):
    __tablename__ = "trading_day"
    __table_args__ = (UniqueConstraint("trade_date", "data_kind", name="uq_trading_day_date_kind"), Index("idx_trading_day_kind_date", "data_kind", "trade_date"))
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    data_kind: Mapped[str] = mapped_column(String(10))
    strict_mode: Mapped[bool] = mapped_column(Boolean)
    completeness_score: Mapped[int] = mapped_column(Integer)
    missing_items: Mapped[str] = mapped_column(Text, default="[]")
    market_regime: Mapped[str] = mapped_column(String(100))
    turnover: Mapped[float | None] = mapped_column(Float)
    turnover_delta: Mapped[float | None] = mapped_column(Float)
    advancers: Mapped[int | None] = mapped_column(Integer)
    decliners: Mapped[int | None] = mapped_column(Integer)
    limit_up_count: Mapped[int | None] = mapped_column(Integer)
    limit_down_count: Mapped[int | None] = mapped_column(Integer)
    max_board_height: Mapped[int | None] = mapped_column(Integer)
    position_min: Mapped[int] = mapped_column(Integer)
    position_max: Mapped[int] = mapped_column(Integer)
    import_id: Mapped[int] = mapped_column(ForeignKey("review_import.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class MarketDaily(Base):
    __tablename__ = "market_daily"
    __table_args__ = (UniqueConstraint("trade_date", name="uq_market_daily_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    data_quality_status: Mapped[str] = mapped_column(String(20))
    data_quality_score: Mapped[int] = mapped_column(Integer)
    turnover: Mapped[float | None] = mapped_column(Float)
    previous_turnover: Mapped[float | None] = mapped_column(Float)
    turnover_delta: Mapped[float | None] = mapped_column(Float)
    turnover_delta_pct: Mapped[float | None] = mapped_column(Float)
    rise_count: Mapped[int | None] = mapped_column(Integer)
    fall_count: Mapped[int | None] = mapped_column(Integer)
    flat_count: Mapped[int | None] = mapped_column(Integer)
    limit_up_count: Mapped[int | None] = mapped_column(Integer)
    limit_down_count: Mapped[int | None] = mapped_column(Integer)
    failed_limit_count: Mapped[int | None] = mapped_column(Integer)
    highest_board: Mapped[int | None] = mapped_column(Integer)
    source_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_data: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Theme(Base):
    __tablename__ = "theme"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ThemeDailyReview(Base):
    __tablename__ = "theme_daily_review"
    __table_args__ = (UniqueConstraint("trading_day_id", "theme_id", name="uq_theme_review_day_theme"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    rank_no: Mapped[int] = mapped_column(Integer)
    base_logic_score: Mapped[int | None] = mapped_column(Integer)
    realization_score: Mapped[int | None] = mapped_column(Integer)
    expectation_gap_score: Mapped[int | None] = mapped_column(Integer)
    persistence_score: Mapped[int | None] = mapped_column(Integer)
    market_confirmation_score: Mapped[int | None] = mapped_column(Integer)
    risk_penalty: Mapped[int | None] = mapped_column(Integer)
    total_score: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[str | None] = mapped_column(String(3))
    lifecycle: Mapped[str] = mapped_column(String(20))
    delta_score: Mapped[int | None] = mapped_column(Integer)
    delta_reason: Mapped[str] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ThemeAlias(Base):
    __tablename__ = "theme_alias"
    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(100), unique=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))


class ThemeDailyScore(Base):
    __tablename__ = "theme_daily_score"
    __table_args__ = (UniqueConstraint("trading_day_id", "theme_id", name="uq_theme_score_day_theme"), Index("idx_theme_score_theme_day", "theme_id", "trading_day_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    rank_no: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(20))
    change_status: Mapped[str] = mapped_column(String(20))
    causal_chain: Mapped[str] = mapped_column(Text)
    base_logic_score: Mapped[int | None] = mapped_column(Integer)
    realization_score: Mapped[int | None] = mapped_column(Integer)
    expectation_gap_score: Mapped[int | None] = mapped_column(Integer)
    persistence_score: Mapped[int | None] = mapped_column(Integer)
    market_confirmation_score: Mapped[int | None] = mapped_column(Integer)
    risk_penalty: Mapped[int | None] = mapped_column(Integer)
    total_score: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[str | None] = mapped_column(String(3))
    logic_quality: Mapped[int | None] = mapped_column(Integer)
    market_strength: Mapped[int | None] = mapped_column(Integer)
    risk_reward: Mapped[int | None] = mapped_column(Integer)
    missing_reasons: Mapped[str] = mapped_column(Text, default="{}")
    delta_score: Mapped[int | None] = mapped_column(Integer)
    delta_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ThemeDriver(Base):
    __tablename__ = "theme_driver"
    __table_args__ = (UniqueConstraint("trading_day_id", "theme_id", "driver_code", name="uq_theme_driver_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    driver_code: Mapped[int] = mapped_column(Integer)
    driver_name: Mapped[str] = mapped_column(String(100))
    evidence_level: Mapped[str] = mapped_column(String(1))


class Stock(Base):
    __tablename__ = "stock"
    stock_code: Mapped[str] = mapped_column(String(6), primary_key=True)
    stock_name: Mapped[str] = mapped_column(String(100))
    exchange: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class StockDailyScore(Base):
    __tablename__ = "stock_daily_score"
    __table_args__ = (UniqueConstraint("trading_day_id", "stock_code", "theme_id", name="uq_stock_score_day_theme"), Index("idx_stock_score_stock_day", "stock_code", "trading_day_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.stock_code"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    role: Mapped[str] = mapped_column(String(20))
    role_detail: Mapped[str | None] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(20))
    catalyst: Mapped[str] = mapped_column(Text)
    benefit_path: Mapped[str] = mapped_column(Text)
    causal_chain: Mapped[str] = mapped_column(Text)
    realization_score: Mapped[int | None] = mapped_column(Integer)
    expectation_gap: Mapped[int | None] = mapped_column(Integer)
    logic_quality: Mapped[int | None] = mapped_column(Integer)
    market_strength: Mapped[int | None] = mapped_column(Integer)
    risk_reward: Mapped[int | None] = mapped_column(Integer)
    total_score: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[str | None] = mapped_column(String(3))
    missing_reasons: Mapped[str] = mapped_column(Text, default="{}")
    delta_score: Mapped[int | None] = mapped_column(Integer)
    delta_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class StockDailyReview(Base):
    __tablename__ = "stock_daily_review"
    __table_args__ = (UniqueConstraint("trading_day_id", "stock_code", "theme_id", name="uq_stock_review_day_theme"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.stock_code"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    role: Mapped[str] = mapped_column(String(20))
    lifecycle: Mapped[str] = mapped_column(String(20))
    total_score: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[str | None] = mapped_column(String(3))
    delta_score: Mapped[int | None] = mapped_column(Integer)
    delta_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ScoreHistory(Base):
    __tablename__ = "score_history"
    __table_args__ = (Index("idx_score_history_entity", "entity_type", "entity_key", "trade_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(100))
    previous_score: Mapped[int | None] = mapped_column(Integer)
    current_score: Mapped[int | None] = mapped_column(Integer)
    delta_score: Mapped[int | None] = mapped_column(Integer)
    delta_reason: Mapped[str] = mapped_column(Text)
    horizon: Mapped[str] = mapped_column(String(20), default="daily_import")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class StockDriver(Base):
    __tablename__ = "stock_driver"
    __table_args__ = (UniqueConstraint("trading_day_id", "stock_code", "theme_id", "driver_code", name="uq_stock_driver_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.stock_code"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme.id"))
    driver_code: Mapped[int] = mapped_column(Integer)
    driver_name: Mapped[str] = mapped_column(String(100))
    evidence_level: Mapped[str] = mapped_column(String(1))


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("idx_evidence_entity", "entity_type", "entity_key", "trading_day_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(100))
    evidence_level: Mapped[str] = mapped_column(String(1))
    evidence_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    excerpt: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class RiskEvent(Base):
    __tablename__ = "risk_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(100))
    risk_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    penalty: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    invalidation_condition: Mapped[str] = mapped_column(Text)


class TomorrowCheck(Base):
    __tablename__ = "tomorrow_check"
    __table_args__ = (Index("idx_check_status", "status", "proposed_day_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proposed_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(100))
    check_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resolved_day_id: Mapped[int | None] = mapped_column(ForeignKey("trading_day.id"))
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ValidationResult(Base):
    __tablename__ = "validation_result"
    __table_args__ = (Index("idx_validation_result_status", "trade_date", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(100))
    validation_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    result: Mapped[str | None] = mapped_column(Text)
    source_check_id: Mapped[int | None] = mapped_column(ForeignKey("tomorrow_check.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class MarketPacketLog(Base):
    __tablename__ = "market_packet_log"
    __table_args__ = (UniqueConstraint("trade_date", "packet_sha256", name="uq_market_packet_log"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    packet_path: Mapped[str] = mapped_column(Text)
    compact_path: Mapped[str] = mapped_column(Text)
    quality_path: Mapped[str] = mapped_column(Text)
    packet_sha256: Mapped[str] = mapped_column(String(64))
    data_quality_status: Mapped[str] = mapped_column(String(20))
    data_quality_score: Mapped[int] = mapped_column(Integer)
    missing_data: Mapped[str] = mapped_column(Text, default="[]")
    generated_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class FactVersion(Base):
    __tablename__ = "fact_version"
    __table_args__ = (
        UniqueConstraint("fact_type", "natural_key", "content_hash", name="uq_fact_version_content"),
        Index("idx_fact_version_current", "fact_type", "natural_key", "is_current"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    fact_type: Mapped[str] = mapped_column(String(40))
    natural_key: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_batch_id: Mapped[int | None] = mapped_column(ForeignKey("source_batch.id"))
    payload_json: Mapped[str] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("fact_version.id"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class FactPartition(Base):
    __tablename__ = "fact_partition"
    __table_args__ = (
        UniqueConstraint("dataset", "trade_date", "content_hash", name="uq_fact_partition_content"),
        Index("idx_fact_partition_dataset_date", "dataset", "trade_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(100))
    trade_date: Mapped[date] = mapped_column(Date)
    content_hash: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer)
    schema_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class OfficialAnnouncement(Base):
    __tablename__ = "official_announcement"
    __table_args__ = (Index("idx_official_announcement_date_stock", "trade_date", "stock_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    stock_code: Mapped[str] = mapped_column(String(6))
    stock_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    confirmed_fact: Mapped[str] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(String(1))
    clarification_flags: Mapped[str] = mapped_column(Text, default="[]")
    risk_flags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class OfficialPolicy(Base):
    __tablename__ = "official_policy"
    __table_args__ = (Index("idx_official_policy_date_agency", "trade_date", "agency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(Text)
    agency: Mapped[str] = mapped_column(String(100))
    published_at: Mapped[str | None] = mapped_column(String(40))
    url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    policy_level: Mapped[str] = mapped_column(String(40))
    related_industries: Mapped[str] = mapped_column(Text, default="[]")
    related_themes: Mapped[str] = mapped_column(Text, default="[]")
    evidence_level: Mapped[str] = mapped_column(String(1))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ThemeRelationship(Base):
    __tablename__ = "theme_relationship"
    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day_id: Mapped[int] = mapped_column(ForeignKey("trading_day.id"))
    parent_theme_id: Mapped[int | None] = mapped_column(ForeignKey("theme.id"))
    child_theme_id: Mapped[int | None] = mapped_column(ForeignKey("theme.id"))
    relation_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
