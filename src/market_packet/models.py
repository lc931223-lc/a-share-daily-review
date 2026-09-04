from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


QualityStatus = Literal["PASS", "PARTIAL", "FAIL", "EMPTY_VALID", "UNAVAILABLE", "STALE", "INVALID"]


class PacketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceMeta(PacketModel):
    source: str
    dataset: str
    retrieved_at: datetime
    data_date: date | None = None
    freshness: Literal["same_day", "historical", "current_only", "missing", "unknown"]
    quality: QualityStatus
    is_cached: bool = False
    path: str | None = None
    error: str | None = None
    record_count: int = 0
    cache_created_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error_type: str | None = None
    retry_after: datetime | None = None


class QualityCheck(PacketModel):
    item: str
    status: QualityStatus
    source: str | None = None
    detail: str
    domain: str | None = None
    hard_gate: bool = False


class DataQuality(PacketModel):
    status: QualityStatus
    score: int = Field(ge=0, le=100)
    checks: list[QualityCheck]
    sources: list[SourceMeta]
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    domains: dict[str, dict[str, Any]] = Field(default_factory=dict)
    invalid_items: list[str] = Field(default_factory=list)
    stale_items: list[str] = Field(default_factory=list)
    unavailable_items: list[str] = Field(default_factory=list)
    conflict_count: int = 0


class PacketMeta(PacketModel):
    schema_version: Literal["market_packet.1"]
    trade_date: date
    generated_at: datetime
    generated_by: Literal["codex_market_packet_phase1"]
    codex_role: Literal["data_engineer_data_validator_research_clerk"]
    final_judgement_owner: Literal["chatgpt"]


class MarketPacket(PacketModel):
    meta: PacketMeta
    data_quality: DataQuality
    market_overview: dict[str, Any]
    indices: list[dict[str, Any]]
    market_breadth: dict[str, Any]
    liquidity: dict[str, Any]
    limit_up_down: dict[str, Any]
    industries: list[dict[str, Any]]
    themes: list[dict[str, Any]]
    stocks: list[dict[str, Any]]
    leader_candidates: list[dict[str, Any]]
    leader_board: list[dict[str, Any]]
    capital_flow: dict[str, Any]
    announcements: dict[str, Any]
    policies: dict[str, Any]
    industry_events: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    previous_review: dict[str, Any]
    tomorrow_check_context: dict[str, Any]
    missing_data: list[str]
