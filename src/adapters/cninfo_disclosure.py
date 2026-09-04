from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from src.adapters.base import AdapterSchemaError
from src.domain.market_data import SourceName, SourceRecord


REQUIRED_ANNOUNCEMENT_FIELDS = {"code", "title", "published_at", "source_url", "summary"}


class CninfoDisclosureAdapter:
    def __init__(self, loader: Callable[[date], list[dict[str, Any]]] | None = None):
        self.loader = loader or self._load_remote

    def announcements(self, trade_date: date) -> SourceRecord:
        rows = self.loader(trade_date)
        _require_fields("cninfo", "announcements", rows, REQUIRED_ANNOUNCEMENT_FIELDS)
        return SourceRecord(
            source=SourceName.CNINFO,
            dataset="announcements",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def _load_remote(self, trade_date: date):
        raise NotImplementedError("CNINFO remote fetch will be wired by the pipeline")


def _require_fields(source: str, dataset: str, rows: list[dict[str, Any]], required: set[str]) -> None:
    if not rows:
        raise AdapterSchemaError(source, dataset, "空响应")
    for row in rows:
        missing = sorted(required - set(row))
        if missing:
            raise AdapterSchemaError(source, dataset, f"缺少字段：{', '.join(missing)}")
