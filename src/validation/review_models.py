from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.constants import CHANGE_STATUSES, DRIVER_TYPES, EvidenceLevel, LifecycleStage, StockRole
from src.domain.scoring import calculate_total, rating_for_score


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Completeness(StrictModel):
    score: int = Field(ge=0, le=100)
    missing_items: list[str] = Field(default_factory=list)


class DriverRef(StrictModel):
    code: int = Field(ge=1, le=41)
    name: str
    evidence_level: EvidenceLevel

    @model_validator(mode="after")
    def validate_catalog_match(self):
        if DRIVER_TYPES[self.code] != self.name:
            raise ValueError(
                f"驱动力 {self.code} 的标准名称应为“{DRIVER_TYPES[self.code]}”"
            )
        return self


class ThemeScores(StrictModel):
    base_logic_score: int | None = Field(default=None, ge=0, le=40)
    realization_score: int | None = Field(default=None, ge=0, le=25)
    expectation_gap_score: int | None = Field(default=None, ge=0, le=15)
    persistence_score: int | None = Field(default=None, ge=0, le=10)
    market_confirmation_score: int | None = Field(default=None, ge=0, le=10)
    risk_penalty: int | None = Field(default=None, ge=-20, le=0)
    total_score: int | None = Field(default=None, ge=-20, le=100)
    rating: Literal["S+", "S", "A", "B", "C", "D"] | None = None
    logic_quality: int | None = Field(default=None, ge=0, le=100)
    market_strength: int | None = Field(default=None, ge=0, le=100)
    risk_reward: int | None = Field(default=None, ge=0, le=100)
    missing_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_score_consistency(self):
        dimensions = {
            "base_logic": self.base_logic_score,
            "realization": self.realization_score,
            "expectation_gap": self.expectation_gap_score,
            "persistence": self.persistence_score,
            "market_confirmation": self.market_confirmation_score,
            "risk_penalty": self.risk_penalty,
        }
        nullable = {
            "base_logic_score": self.base_logic_score,
            "realization_score": self.realization_score,
            "expectation_gap_score": self.expectation_gap_score,
            "persistence_score": self.persistence_score,
            "market_confirmation_score": self.market_confirmation_score,
            "risk_penalty": self.risk_penalty,
            "total_score": self.total_score,
            "rating": self.rating,
            "logic_quality": self.logic_quality,
            "market_strength": self.market_strength,
            "risk_reward": self.risk_reward,
        }
        for field_name, value in nullable.items():
            if value is None and not self.missing_reasons.get(field_name, "").strip():
                raise ValueError(f"{field_name} 为 null 时必须提供 missing_reasons")

        if all(value is not None for value in dimensions.values()):
            expected = calculate_total({name: int(value) for name, value in dimensions.items()})
            if self.total_score != expected:
                raise ValueError(f"total_score 应为 {expected}")
            expected_rating = rating_for_score(expected)
            if self.rating != expected_rating:
                raise ValueError(f"rating 应为 {expected_rating}")
        elif self.total_score is not None or self.rating is not None:
            raise ValueError("评分分项不完整时 total_score 和 rating 必须为 null")
        return self


class StockScores(StrictModel):
    realization_score: int | None = Field(default=None, ge=0, le=100)
    expectation_gap: int | None = Field(default=None, ge=0, le=100)
    logic_quality: int | None = Field(default=None, ge=0, le=100)
    market_strength: int | None = Field(default=None, ge=0, le=100)
    risk_reward: int | None = Field(default=None, ge=0, le=100)
    total_score: int | None = Field(default=None, ge=0, le=100)
    rating: Literal["S+", "S", "A", "B", "C", "D"] | None = None
    missing_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_null_reasons(self):
        values = self.model_dump(exclude={"missing_reasons"})
        for field_name, value in values.items():
            if value is None and not self.missing_reasons.get(field_name, "").strip():
                raise ValueError(f"{field_name} 为 null 时必须提供 missing_reasons")
        return self


class ThemeReview(StrictModel):
    name: str = Field(min_length=1)
    rank_no: int = Field(ge=1)
    stage: LifecycleStage
    change_status: Literal[
        "new", "strengthened", "weakened", "expanded", "realized", "invalidated", "unchanged"
    ]
    causal_chain: list[str] = Field(min_length=2)
    drivers: list[DriverRef] = Field(min_length=1)
    scores: ThemeScores
    delta_reason: str = Field(min_length=1)


class StockReview(StrictModel):
    name: str = Field(min_length=1)
    code: str = Field(pattern=r"^(00|30|60|68|43|8[3-9]|92)\d{4}$")
    theme: str = Field(min_length=1)
    role: StockRole
    role_detail: str | None = None
    stage: LifecycleStage
    drivers: list[DriverRef] = Field(min_length=1)
    catalyst: str = Field(min_length=1)
    benefit_path: list[str] = Field(min_length=2)
    causal_chain: list[str] = Field(min_length=2)
    scores: StockScores
    delta_reason: str = Field(min_length=1)


class EvidenceReview(StrictModel):
    entity_type: Literal["market", "theme", "stock", "industry"]
    entity_key: str = Field(min_length=1)
    evidence_level: EvidenceLevel
    evidence_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_url: str | None = None
    published_at: datetime | None = None
    excerpt: str = Field(min_length=1)
    verified: bool = False


class RiskEventReview(StrictModel):
    entity_type: Literal["market", "theme", "stock"]
    entity_key: str = Field(min_length=1)
    risk_type: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    penalty: int = Field(ge=-20, le=0)
    description: str = Field(min_length=1)
    invalidation_condition: str = Field(min_length=1)


class TomorrowCheckReview(StrictModel):
    entity_type: Literal["market", "theme", "stock"]
    entity_key: str = Field(min_length=1)
    check_type: str = Field(min_length=1)
    description: str = Field(min_length=1)


class TomorrowCheckUpdate(StrictModel):
    check_id: int = Field(gt=0)
    status: Literal["confirmed", "weakened", "invalidated"]
    result: str = Field(min_length=1)


class ChangesVsPreviousDay(StrictModel):
    new: list[str] = Field(default_factory=list)
    strengthened: list[str] = Field(default_factory=list)
    weakened: list[str] = Field(default_factory=list)
    expanded: list[str] = Field(default_factory=list)
    realized: list[str] = Field(default_factory=list)
    invalidated: list[str] = Field(default_factory=list)


class IndexMetric(StrictModel):
    name: str = Field(min_length=1)
    close: float
    change_pct: float
    turnover_yi: float | None = Field(default=None, ge=0)


class SentimentDashboard(StrictModel):
    temperature: str = Field(min_length=1)
    breadth: str = Field(min_length=1)
    liquidity: str = Field(min_length=1)
    risk_appetite: str = Field(min_length=1)
    limit_pool: str = Field(min_length=1)
    loss_feedback: str = Field(min_length=1)


class SectorRow(StrictModel):
    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class LimitLadderRow(StrictModel):
    height: str = Field(min_length=1)
    stocks: str = Field(min_length=1)
    read: str = Field(min_length=1)


class DragonTigerSummary(StrictModel):
    date: date
    amount_yi: float = Field(ge=0)
    stock_count: int = Field(ge=0)
    institution_net_buy_count: int = Field(ge=0)
    read: str = Field(min_length=1)


class TomorrowPlanRow(StrictModel):
    item: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class DataQualityDetail(StrictModel):
    status: str = Field(min_length=1)
    primary_source: str = Field(min_length=1)
    resolved_gaps: list[str] = Field(default_factory=list)
    source_disagreements: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class EngineDailyMetric(StrictModel):
    date: str = Field(min_length=1)
    limit_up_count: int = Field(ge=0)
    failed_limit_count: int = Field(ge=0)
    failed_limit_rate: float = Field(ge=0)
    limit_down_count: int = Field(ge=0)
    highest_board: int = Field(ge=0)
    multi_board_count: int = Field(ge=0)
    prev_limit_avg_pct: float | None = None
    prev_limit_positive_rate: float | None = None
    sentiment_score: int = Field(ge=0, le=100)
    sentiment_state: str = Field(min_length=1)
    position_band: str = Field(min_length=1)
    discipline: str = Field(min_length=1)


class EngineThemeRank(StrictModel):
    rank: int = Field(ge=1)
    theme_name: str = Field(min_length=1)
    theme_score: float = Field(ge=0, le=100)
    limit_up_count: int = Field(ge=0)
    failed_limit_count: int = Field(ge=0)
    failed_limit_rate: float = Field(ge=0)
    highest_board: int = Field(ge=0)
    persistence_days: int = Field(ge=0)
    cycle_phase: str = Field(min_length=1)
    top_stocks: str = Field(min_length=1)


class EngineStockRole(StrictModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    theme_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    role_score: int = Field(ge=0, le=100)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class SentimentEngineDetail(StrictModel):
    data_dir: str = Field(min_length=1)
    data_sources: list[str] = Field(default_factory=list)
    daily_metric: EngineDailyMetric
    theme_ranking: list[EngineThemeRank] = Field(default_factory=list)
    stock_role_classification: list[EngineStockRole] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class DailyReview(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    date: date
    data_kind: Literal["real"] = "real"
    strict_mode: bool
    completeness: Completeness
    market_regime: str = Field(min_length=1)
    turnover: float | None = Field(default=None, ge=0)
    turnover_delta: float | None = None
    advancers: int | None = Field(default=None, ge=0)
    decliners: int | None = Field(default=None, ge=0)
    limit_up_count: int | None = Field(default=None, ge=0)
    limit_down_count: int | None = Field(default=None, ge=0)
    max_board_height: int | None = Field(default=None, ge=0)
    position_min: int = Field(ge=0, le=10)
    position_max: int = Field(ge=0, le=10)
    market_commentary: list[str] = Field(default_factory=list)
    indices: list[IndexMetric] = Field(default_factory=list)
    sentiment_dashboard: SentimentDashboard | None = None
    sector_strength: list[SectorRow] = Field(default_factory=list)
    sector_weakness: list[SectorRow] = Field(default_factory=list)
    limit_ladder: list[LimitLadderRow] = Field(default_factory=list)
    dragon_tiger: DragonTigerSummary | None = None
    tomorrow_plan: list[TomorrowPlanRow] = Field(default_factory=list)
    data_quality_detail: DataQualityDetail | None = None
    sentiment_engine: SentimentEngineDetail | None = None
    main_themes: list[ThemeReview] = Field(min_length=1)
    stocks: list[StockReview] = Field(default_factory=list)
    evidence: list[EvidenceReview] = Field(default_factory=list)
    risk_events: list[RiskEventReview] = Field(default_factory=list)
    tomorrow_checks: list[TomorrowCheckReview] = Field(default_factory=list)
    tomorrow_check_updates: list[TomorrowCheckUpdate] = Field(default_factory=list)
    changes_vs_previous_day: ChangesVsPreviousDay

    @model_validator(mode="after")
    def validate_review_mode_and_references(self):
        if self.data_kind == "real" and not self.strict_mode:
            raise ValueError("真实数据必须启用 strict_mode")
        if self.position_min > self.position_max:
            raise ValueError("position_min 不能大于 position_max")
        theme_names = {theme.name for theme in self.main_themes}
        missing = sorted({stock.theme for stock in self.stocks} - theme_names)
        if missing:
            raise ValueError(f"个股引用了未定义主线：{', '.join(missing)}")
        ranks = [theme.rank_no for theme in self.main_themes]
        if len(ranks) != len(set(ranks)):
            raise ValueError("主线 rank_no 不可重复")
        return self
