from collections.abc import Callable
from datetime import UTC, date, datetime
import time
from typing import Any

import requests

from src.adapters.base import AdapterDataError, AdapterSchemaError, AdapterTimeout
from src.config.runtime import DataPipelineConfig
from src.domain.market_data import SourceName, SourceRecord


class FallbackScopeError(RuntimeError):
    pass


DATASET_FIELDS = {
    "market_breadth": {"advancers", "decliners"},
    "limit_pool": {"limit_up", "limit_down", "failed_limit", "board_height"},
    "failed_limit": {"failed_limit"},
    "theme_membership": {"theme_name", "theme_membership"},
}
EASTMONEY_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_INDEX = "https://push2.eastmoney.com/api/qt/ulist.np/get"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
FORBIDDEN_CORE_DATASETS = {
    "stock_daily",
    "trade_calendar",
    "index_daily",
    "adj_factor",
    "financials",
    "announcements",
}


class EastmoneyFallbackAdapter:
    def __init__(
        self,
        config: DataPipelineConfig,
        loader: Callable[[str, date], dict[str, Any] | list[dict[str, Any]]] | None = None,
    ):
        self.config = config
        self.loader = loader or self._load_remote
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self._last_call = 0.0

    def fetch(self, dataset: str, trade_date: date, reason: str = "supplemental source unavailable"):
        if dataset in FORBIDDEN_CORE_DATASETS:
            raise FallbackScopeError(f"东方财富不能替代核心数据集：{dataset}")
        fields = DATASET_FIELDS.get(dataset)
        allowed = set(self.config.eastmoney_fallback_fields)
        if not fields or not fields <= allowed:
            raise FallbackScopeError(f"东方财富降级字段不在白名单内：{dataset}")

        payload = self.loader(dataset, trade_date)
        rows = payload if isinstance(payload, list) else [payload]
        if not rows:
            raise AdapterSchemaError("eastmoney", dataset, "空响应")
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset=dataset,
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
            is_fallback=True,
            fallback_reason=reason,
        )

    def trade_calendar(self, trade_date: date) -> SourceRecord:
        rows = self._rows("trade_calendar", trade_date)
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset="trade_calendar",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def stock_basic(self, trade_date: date) -> SourceRecord:
        rows = self._rows("stock_basic", trade_date)
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset="stock_basic",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def stock_daily(self, trade_date: date) -> SourceRecord:
        rows = self._rows("stock_daily", trade_date)
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset="daily",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def index_daily(self, trade_date: date, major_indices: list[str]) -> SourceRecord:
        rows = self._rows("index_daily", trade_date)
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset="index_daily",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=[
                row for row in rows
                if not major_indices or row.get("ts_code") in major_indices or row.get("code") in major_indices
            ],
        )

    def adj_factor(self, trade_date: date) -> SourceRecord:
        rows = self._rows("adj_factor", trade_date)
        return SourceRecord(
            source=SourceName.EASTMONEY,
            dataset="adj_factor",
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=rows,
        )

    def _rows(self, dataset: str, trade_date: date) -> list[dict[str, Any]]:
        payload = self.loader(dataset, trade_date)
        rows = payload if isinstance(payload, list) else [payload]
        if not rows:
            raise AdapterSchemaError("eastmoney", dataset, "空响应")
        return rows

    def _load_remote(self, dataset: str, trade_date: date):
        if dataset == "trade_calendar":
            rows = self._remote_stock_rows(page_size=1)
            return [{"cal_date": trade_date.strftime("%Y%m%d"), "is_open": int(bool(rows))}]
        if dataset == "stock_basic":
            return [
                {
                    "ts_code": self._ts_code(row),
                    "symbol": str(row.get("f12", "")),
                    "name": row.get("f14", ""),
                    "exchange": self._exchange(row),
                    "list_status": "L",
                }
                for row in self._remote_stock_rows()
            ]
        if dataset == "stock_daily":
            return [
                {
                    "ts_code": self._ts_code(row),
                    "trade_date": trade_date.strftime("%Y%m%d"),
                    "open": row.get("f17"),
                    "high": row.get("f15"),
                    "low": row.get("f16"),
                    "close": row.get("f2"),
                    "pre_close": row.get("f18"),
                    "change": row.get("f4"),
                    "pct_chg": row.get("f3"),
                    "vol": row.get("f5"),
                    "amount": row.get("f6"),
                }
                for row in self._remote_stock_rows()
            ]
        if dataset == "index_daily":
            rows = self._remote_index_rows()
            return [
                {
                    "ts_code": self._index_ts_code(row),
                    "trade_date": trade_date.strftime("%Y%m%d"),
                    "close": row.get("f2"),
                    "pct_chg": row.get("f3"),
                    "amount": row.get("f6"),
                }
                for row in rows
            ]
        if dataset == "adj_factor":
            return [
                {
                    "trade_date": trade_date.strftime("%Y%m%d"),
                    "source_note": "东方财富默认主源不提供 Tushare adj_factor 等价字段",
                }
            ]
        raise AdapterDataError("eastmoney", dataset, "unsupported_dataset")

    def _remote_stock_rows(self, page_size: int = 500) -> list[dict[str, Any]]:
        fields = "f2,f3,f4,f5,f6,f12,f13,f14,f15,f16,f17,f18"
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._em_json(
                EASTMONEY_CLIST,
                {
                    "pn": page,
                    "pz": page_size,
                    "po": 1,
                    "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                    "fields": fields,
                },
            )
            diff = data.get("data", {}).get("diff") or []
            rows.extend(diff)
            total = int(data.get("data", {}).get("total") or 0)
            if page_size == 1 or len(rows) >= total or not diff:
                break
            page += 1
        return rows

    def _remote_index_rows(self) -> list[dict[str, Any]]:
        data = self._em_json(
            EASTMONEY_INDEX,
            {
                "fltt": 2,
                "invt": 2,
                "fields": "f12,f13,f14,f2,f3,f4,f6",
                "secids": "1.000001,0.399001,0.399006,1.000688",
            },
        )
        return data.get("data", {}).get("diff") or []

    def _em_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        wait = 1.1 - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            response = self.session.get(url, params=params, timeout=self.config.request_timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise AdapterTimeout("eastmoney", "remote", str(exc)) from exc
        except requests.RequestException as exc:
            raise AdapterDataError("eastmoney", "remote", str(exc)) from exc
        finally:
            self._last_call = time.time()

    @staticmethod
    def _exchange(row: dict[str, Any]) -> str:
        if row.get("f13") == 1:
            return "SSE"
        code = str(row.get("f12", ""))
        return "BSE" if code.startswith(("8", "9")) else "SZSE"

    @classmethod
    def _ts_code(cls, row: dict[str, Any]) -> str:
        code = str(row.get("f12", ""))
        suffix = "SH" if row.get("f13") == 1 else ("BJ" if code.startswith(("8", "9")) else "SZ")
        return f"{code}.{suffix}"

    @staticmethod
    def _index_ts_code(row: dict[str, Any]) -> str:
        code = str(row.get("f12", ""))
        suffix = "SH" if row.get("f13") == 1 else "SZ"
        return f"{code}.{suffix}"
