from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from src.adapters.base import AdapterSchemaError
from src.domain.market_data import SourceName, SourceRecord


class TencentMarketAdapter:
    def __init__(self, loader: Callable[[date], str] | None = None):
        self.loader = loader or self._load_remote

    def quotes(self, trade_date: date) -> SourceRecord:
        text = self.loader(trade_date)
        rows = [_parse_quote(line) for line in text.splitlines() if line.strip()]
        if not rows:
            raise AdapterSchemaError("tencent", "quotes", "空响应")
        return SourceRecord(
            source=SourceName.TENCENT,
            dataset="quotes",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def _load_remote(self, trade_date: date):
        raise NotImplementedError("Tencent remote fetch will be wired by the pipeline")


def _parse_quote(line: str) -> dict[str, Any]:
    try:
        raw = line.split('"', 1)[1].rsplit('"', 1)[0]
    except IndexError as exc:
        raise AdapterSchemaError("tencent", "quotes", "字段格式变化") from exc
    parts = raw.split("~")
    if len(parts) <= 9:
        raise AdapterSchemaError("tencent", "quotes", "字段数量不足")
    code = parts[2]
    name = parts[1]
    price = _to_float(parts[3])
    previous_close = _to_float(parts[4])
    amount = _to_float(parts[37]) if len(parts) > 37 else _to_float(parts[9])
    timestamp = parts[30] if len(parts) > 30 else parts[-1]
    return {
        "code": code,
        "name": name,
        "price": price,
        "previous_close": previous_close,
        "amount": amount,
        "timestamp": timestamp,
    }


def _to_float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise AdapterSchemaError("tencent", "quotes", "数值字段无法解析") from exc
