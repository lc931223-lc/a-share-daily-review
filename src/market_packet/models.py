from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PacketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceMeta(PacketModel):
    source: str
    retrieved_at: datetime
    data_date: date | None = None
    freshness: Literal["same_day", "historical", "current_only", "missing", "unknown"]
    quality: Literal["PASS", "PARTIAL", "FAIL"]
    is_cached: bool = False
    path: str | None = None
    error: str | None = None


class QualityCheck(PacketModel):
    item: str
    status: Literal["PASS", "PARTIAL", "FAIL"]
    source: str | None = None
    detail: str


class DataQuality(PacketModel):
    status: Literal["EXCELLENT", "GOOD", "PARTIAL", "INCOMPLETE"]
    score: int = Field(ge=0, le=100)
    checks: list[QualityCheck]
    sources: list[SourceMeta]
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


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
