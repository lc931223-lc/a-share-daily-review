from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from src.adapters.base import AdapterDataError, AdapterPermissionError, AdapterSchemaError
from src.config.runtime import RuntimeSettings
from src.domain.market_data import SourceName, SourceRecord


REQUIRED_COLUMNS = {
    "trade_cal": {"cal_date", "is_open"},
    "stock_basic": {"ts_code", "symbol", "name", "list_date", "exchange", "list_status"},
    "daily": {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"},
    "index_daily": {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"},
    "adj_factor": {"ts_code", "trade_date", "adj_factor"},
}


class TushareMarketAdapter:
    def __init__(self, pro: Any | None = None, settings: RuntimeSettings | None = None):
        if pro is None:
            if settings is None:
                settings = RuntimeSettings.load()
            import tushare as ts

            pro = ts.pro_api(settings.tushare_token)
        self.pro = pro

    def trade_calendar(self, trade_date: date) -> SourceRecord:
        date_text = _format_trade_date(trade_date)
        frame = self._call(
            "trade_cal",
            exchange="",
            start_date=date_text,
            end_date=date_text,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        return self._record("trade_cal", trade_date, frame, date_column="cal_date")

    def stock_basic(self, trade_date: date) -> SourceRecord:
        frame = self._call(
            "stock_basic",
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,list_date,market,exchange,list_status",
        )
        return self._record("stock_basic", trade_date, frame, require_unique_ts_code=True)

    def stock_daily(self, trade_date: date) -> SourceRecord:
        date_text = _format_trade_date(trade_date)
        frame = self._call("daily", trade_date=date_text)
        return self._record(
            "daily",
            trade_date,
            frame,
            date_column="trade_date",
            require_unique_ts_code=True,
        )

    def index_daily(self, trade_date: date, indices: list[str] | None = None) -> SourceRecord:
        date_text = _format_trade_date(trade_date)
        frames = []
        for ts_code in indices or ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
            frames.append(self._call("index_daily", ts_code=ts_code, trade_date=date_text))
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self._record(
            "index_daily",
            trade_date,
            frame,
            date_column="trade_date",
            require_unique_ts_code=True,
        )

    def adj_factor(self, trade_date: date) -> SourceRecord:
        date_text = _format_trade_date(trade_date)
        frame = self._call("adj_factor", trade_date=date_text)
        return self._record(
            "adj_factor",
            trade_date,
            frame,
            date_column="trade_date",
            require_unique_ts_code=True,
        )

    def _call(self, dataset: str, **kwargs: Any) -> pd.DataFrame:
        try:
            frame = getattr(self.pro, dataset)(**kwargs)
        except Exception as exc:
            message = str(exc)
            if "权限" in message or "permission" in message.lower():
                raise AdapterPermissionError("tushare", dataset, "Tushare interface permission denied") from exc
            raise AdapterDataError("tushare", dataset, "Tushare request failed") from exc
        if not isinstance(frame, pd.DataFrame):
            raise AdapterSchemaError("tushare", dataset, "Tushare response is not a DataFrame")
        return frame

    def _record(
        self,
        dataset: str,
        trade_date: date,
        frame: pd.DataFrame,
        *,
        date_column: str | None = None,
        require_unique_ts_code: bool = False,
    ) -> SourceRecord:
        required = REQUIRED_COLUMNS[dataset]
        missing = sorted(required - set(frame.columns))
        if missing:
            raise AdapterSchemaError("tushare", dataset, f"缺少字段：{', '.join(missing)}")
        if frame.empty:
            raise AdapterDataError("tushare", dataset, "空响应")
        if date_column is not None:
            expected = _format_trade_date(trade_date)
            observed = {str(value) for value in frame[date_column].dropna().unique()}
            if observed != {expected}:
                raise AdapterDataError("tushare", dataset, "交易日期与请求日期不一致")
        if require_unique_ts_code and frame["ts_code"].duplicated().any():
            raise AdapterDataError("tushare", dataset, "ts_code 重复")
        payload = frame.where(pd.notna(frame), None).to_dict(orient="records")
        return SourceRecord(
            source=SourceName.TUSHARE,
            dataset=dataset,
            trade_date=trade_date,
            fetched_at=datetime.now(UTC),
            payload=payload,
        )


def _format_trade_date(value: date) -> str:
    return value.strftime("%Y%m%d")
