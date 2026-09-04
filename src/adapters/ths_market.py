from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from src.adapters.base import AdapterSchemaError
from src.domain.market_data import SourceName, SourceRecord


class ThsMarketAdapter:
    def __init__(self, loader: Callable[[date], dict[str, Any]] | None = None):
        self.loader = loader or self._load_remote

    def limit_pool(self, trade_date: date) -> SourceRecord:
        payload = self.loader(trade_date)
        rows: list[dict[str, Any]] = []
        for dataset in ("limit_up", "limit_down", "failed_limit"):
            for item in payload.get(dataset, []):
                _require_keys("ths", dataset, item, {"code", "name"})
                rows.append({"dataset": dataset, **item})
        for theme in payload.get("themes", []):
            _require_keys("ths", "theme_membership", theme, {"theme_name", "members"})
            rows.append({"dataset": "theme_membership", **theme})
        if not rows:
            raise AdapterSchemaError("ths", "limit_pool", "空响应")
        return SourceRecord(
            source=SourceName.THS,
            dataset="limit_pool",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def _load_remote(self, trade_date: date):
        raise NotImplementedError("THS remote fetch will be wired by the pipeline")


def _require_keys(source: str, dataset: str, row: dict[str, Any], required: set[str]) -> None:
    missing = sorted(required - set(row))
    if missing:
        raise AdapterSchemaError(source, dataset, f"缺少字段：{', '.join(missing)}")
