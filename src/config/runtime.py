import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "data_pipeline.json"


class GateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    security_status_explained: float = Field(ge=0, le=1)
    daily_quote_required_fields: float = Field(ge=0, le=1)
    major_index_coverage: float = Field(ge=0, le=1)
    limit_candidate_coverage: float = Field(ge=0, le=1)
    supplemental_abs_diff: int = Field(ge=0)
    supplemental_ratio_diff: float = Field(ge=0, le=1)
    critical_conflicts: int = Field(ge=0)


class DataPipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: str = Field(min_length=1)
    primary_market_source: Literal["eastmoney", "tushare"] = "eastmoney"
    tushare_role: Literal["required_primary", "optional_cross_check"] = "optional_cross_check"
    request_timeout_seconds: int = Field(gt=0)
    max_retries: int = Field(ge=0)
    major_indices: list[str] = Field(min_length=1)
    thresholds: GateThresholds
    eastmoney_fallback_fields: list[str] = Field(default_factory=list)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tushare_token: str | None = Field(default=None)
    pipeline: DataPipelineConfig
    config_path: Path

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "RuntimeSettings":
        load_dotenv()
        token = os.environ.get("TUSHARE_TOKEN", "").strip()

        resolved_config_path = Path(
            config_path or os.environ.get("DATA_PIPELINE_CONFIG") or DEFAULT_CONFIG_PATH
        )
        config = DataPipelineConfig.model_validate(
            json.loads(resolved_config_path.read_text(encoding="utf-8"))
        )
        if config.primary_market_source == "tushare" and not token:
            raise RuntimeError("TUSHARE_TOKEN is required when Tushare is configured as primary")
        return cls(
            tushare_token=token or None,
            pipeline=config,
            config_path=resolved_config_path,
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "pipeline": self.pipeline.model_dump(),
        }
