from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceName(StrEnum):
    TUSHARE = "tushare"
    TENCENT = "tencent"
    THS = "ths"
    EASTMONEY = "eastmoney"
    CNINFO = "cninfo"
    EXCHANGE = "exchange"


class BatchStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class GateStatus(StrEnum):
    PASSED = "PASSED"
    DRAFT_ONLY = "DRAFT_ONLY"
    FAILED = "FAILED"


class ReportStatus(StrEnum):
    PASSED = "PASSED"
    DRAFT_ONLY = "DRAFT_ONLY"
    FAILED = "FAILED"


class GateCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    actual: float | int | str | bool
    threshold: float | int | str | bool
    passed: bool
    reason: str = Field(min_length=1)


class SourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceName
    dataset: str = Field(min_length=1)
    trade_date: date
    fetched_at: datetime
    payload: list[dict[str, Any]]
    is_fallback: bool = False
    fallback_reason: str | None = None


class GateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: GateStatus
    rule_version: str = Field(min_length=1)
    checks: tuple[GateCheck, ...]
    confidence: int = Field(ge=0, le=100)
