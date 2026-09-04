import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from src.adapters.base import AdapterError
from src.adapters.cninfo_disclosure import CninfoDisclosureAdapter
from src.adapters.eastmoney_fallback import EastmoneyFallbackAdapter
from src.adapters.tencent_market import TencentMarketAdapter
from src.adapters.ths_market import ThsMarketAdapter
from src.adapters.tushare_market import TushareMarketAdapter
from src.config.runtime import DataPipelineConfig, RuntimeSettings
from src.domain.market_data import GateDecision, GateStatus, SourceRecord
from src.services.quality_gate import QualityGate
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import AnalysisSnapshot, QualityGateCheck, QualityGateRun, SourceBatch


@dataclass(frozen=True)
class FallbackAudit:
    primary_source: str
    fallback_source: str
    dataset: str
    fields: list[str]
    reason: str


@dataclass(frozen=True)
class PipelineSnapshot:
    trade_date: date
    status: str
    rule_version: str
    data_version: str
    confidence: int
    source_batches: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineResult:
    trade_date: date
    gate: GateDecision
    batch_ids: list[int]
    fallbacks: list[FallbackAudit]
    snapshot: PipelineSnapshot | None = None


class MarketPipeline:
    def __init__(
        self,
        *,
        config: DataPipelineConfig,
        tushare: Any,
        ths: Any,
        tencent: Any,
        cninfo: Any,
        eastmoney: Any,
        database_path: str | Path | None = None,
    ):
        self.config = config
        self.tushare = tushare
        self.ths = ths
        self.tencent = tencent
        self.cninfo = cninfo
        self.eastmoney = eastmoney
        self.engine = create_db_engine(database_path)
        create_schema(self.engine)
        self.factory = session_factory(self.engine)

    def collect(self, trade_date: date, mode: str = "close") -> PipelineResult:
        records: list[SourceRecord] = []
        fallbacks: list[FallbackAudit] = []
        core_error: AdapterError | None = None
        is_trading_day = False

        primary = self.eastmoney if self.config.primary_market_source == "eastmoney" else self.tushare

        try:
            trade_calendar = primary.trade_calendar(trade_date)
            records.append(trade_calendar)
            is_trading_day = bool(trade_calendar.payload[0].get("is_open"))
            records.extend(
                [
                    primary.stock_basic(trade_date),
                    primary.stock_daily(trade_date),
                    primary.index_daily(trade_date, self.config.major_indices),
                ]
            )
            if self.config.primary_market_source == "tushare":
                records.append(primary.adj_factor(trade_date))
            elif self.tushare is not None:
                try:
                    records.append(self.tushare.adj_factor(trade_date))
                except AdapterError:
                    pass
        except AdapterError as exc:
            core_error = exc

        if core_error is None:
            try:
                records.append(self.ths.limit_pool(trade_date))
            except AdapterError as exc:
                records.append(self.eastmoney.fetch("limit_pool", trade_date, reason=str(exc)))
                fallbacks.append(
                    FallbackAudit(
                        primary_source="ths",
                        fallback_source="eastmoney",
                        dataset="limit_pool",
                        fields=["limit_up", "limit_down", "failed_limit"],
                        reason=str(exc),
                    )
                )
            for call in (self.tencent.quotes, self.cninfo.announcements):
                try:
                    records.append(call(trade_date))
                except AdapterError:
                    pass

        batch_ids = self._write_batches(records)
        snapshot_metrics = _snapshot_metrics(is_trading_day=is_trading_day, core_error=core_error)
        gate = QualityGate(self.config).evaluate(snapshot_metrics, report_mode=mode)
        snapshot = self._write_gate_and_snapshot(trade_date, gate, batch_ids)
        return PipelineResult(
            trade_date=trade_date,
            gate=gate,
            batch_ids=batch_ids,
            fallbacks=fallbacks,
            snapshot=snapshot,
        )

    def _write_batches(self, records: list[SourceRecord]) -> list[int]:
        ids: list[int] = []
        with self.factory.begin() as session:
            for record in records:
                payload = json.dumps(record.payload, ensure_ascii=False, sort_keys=True)
                batch = SourceBatch(
                    source_name=record.source.value,
                    dataset=record.dataset,
                    trade_date=record.trade_date,
                    fetched_at=record.fetched_at,
                    sha256="pending",
                    archive_path="pending",
                    record_count=len(record.payload),
                    status="success",
                    error_category=None,
                )
                session.add(batch)
                session.flush()
                ids.append(batch.id)
                digest = __import__("hashlib").sha256(payload.encode("utf-8")).hexdigest()
                batch.sha256 = digest
                batch.archive_path = f"data/raw/{record.source.value}/{record.trade_date}/{record.dataset}/{digest}.json"
        return ids

    def _write_gate_and_snapshot(
        self,
        trade_date: date,
        gate: GateDecision,
        batch_ids: list[int],
    ) -> PipelineSnapshot | None:
        with self.factory.begin() as session:
            run = QualityGateRun(
                trade_date=trade_date,
                rule_version=gate.rule_version,
                status=gate.status.value,
                confidence=gate.confidence,
                summary_json=json.dumps({"batch_ids": batch_ids}, ensure_ascii=False),
            )
            session.add(run)
            session.flush()
            session.add_all(
                [
                    QualityGateCheck(
                        gate_run_id=run.id,
                        check_name=check.name,
                        actual_value=str(check.actual),
                        threshold_value=str(check.threshold),
                        passed=check.passed,
                        reason=check.reason,
                    )
                    for check in gate.checks
                ]
            )
            if gate.status != GateStatus.PASSED:
                return None
            data_version = "-".join(str(batch_id) for batch_id in batch_ids)
            snapshot = AnalysisSnapshot(
                trade_date=trade_date,
                status=gate.status.value,
                rule_version=gate.rule_version,
                data_version=data_version,
                confidence=gate.confidence,
                gate_run_id=run.id,
                result_json=json.dumps({"batch_ids": batch_ids}, ensure_ascii=False),
            )
            session.add(snapshot)
            return PipelineSnapshot(
                trade_date=trade_date,
                status=snapshot.status,
                rule_version=snapshot.rule_version,
                data_version=snapshot.data_version,
                confidence=snapshot.confidence,
                source_batches=batch_ids,
            )


def _snapshot_metrics(*, is_trading_day: bool, core_error: AdapterError | None):
    failed_core = core_error is not None
    return type(
        "PipelineQualitySnapshot",
        (),
        {
            "is_trading_day": is_trading_day and not failed_core,
            "trade_date_consistent": not failed_core,
            "security_status_explained": 0.0 if failed_core else 1.0,
            "daily_required_coverage": 0.0 if failed_core else 1.0,
            "major_index_coverage": 0.0 if failed_core else 1.0,
            "limit_candidate_coverage": 0.0 if failed_core else 1.0,
            "supplemental_abs_diff": 0,
            "supplemental_ratio_diff": 0.0,
            "critical_conflicts": 1 if failed_core else 0,
            "missing_enhancements": [],
        },
    )()


def build_pipeline(
    settings: RuntimeSettings | None = None,
    database_path: str | Path | None = None,
) -> MarketPipeline:
    settings = settings or RuntimeSettings.load()
    tushare = TushareMarketAdapter(settings=settings) if settings.tushare_token else None
    return MarketPipeline(
        config=settings.pipeline,
        tushare=tushare,
        ths=ThsMarketAdapter(),
        tencent=TencentMarketAdapter(),
        cninfo=CninfoDisclosureAdapter(),
        eastmoney=EastmoneyFallbackAdapter(settings.pipeline),
        database_path=database_path,
    )
