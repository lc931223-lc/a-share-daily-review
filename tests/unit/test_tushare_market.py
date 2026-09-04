import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from src.adapters.base import AdapterDataError, AdapterPermissionError
from src.adapters.tushare_market import TushareMarketAdapter


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "tushare"


def frame(name):
    return pd.DataFrame(json.loads((FIXTURE_ROOT / f"{name}.json").read_text("utf-8")))


def frame_with_trade_date(value):
    rows = json.loads((FIXTURE_ROOT / "daily.json").read_text("utf-8"))
    rows[0]["trade_date"] = value
    return pd.DataFrame(rows)


@pytest.fixture
def pro():
    client = Mock()
    client.trade_cal.return_value = frame("trade_cal")
    client.stock_basic.return_value = frame("stock_basic")
    client.daily.return_value = frame("daily")
    client.index_daily.return_value = frame("index_daily")
    client.adj_factor.return_value = frame("adj_factor")
    return client


@pytest.fixture
def adapter(pro):
    return TushareMarketAdapter(pro=pro)


def test_tushare_daily_uses_ts_code_and_trade_date(adapter):
    record = adapter.stock_daily(date(2026, 9, 1))
    rows = record.payload

    assert rows
    assert set(rows[0]) >= {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"}
    assert rows[0]["ts_code"].endswith((".SH", ".SZ", ".BJ"))
    assert rows[0]["trade_date"] == "20260901"


def test_tushare_rejects_wrong_date(adapter, pro):
    pro.daily.return_value = frame_with_trade_date("20260831")

    with pytest.raises(AdapterDataError, match="交易日期"):
        adapter.stock_daily(date(2026, 9, 1))


def test_tushare_rejects_duplicate_ts_code(adapter, pro):
    duplicate = pd.concat([frame("daily"), frame("daily")], ignore_index=True)
    pro.daily.return_value = duplicate

    with pytest.raises(AdapterDataError, match="重复"):
        adapter.stock_daily(date(2026, 9, 1))


def test_tushare_wraps_permission_error(adapter, pro):
    pro.daily.side_effect = Exception("没有权限访问该接口")

    with pytest.raises(AdapterPermissionError, match="daily"):
        adapter.stock_daily(date(2026, 9, 1))


def test_core_datasets_return_source_records(adapter):
    target = date(2026, 9, 1)

    assert adapter.trade_calendar(target).dataset == "trade_cal"
    assert adapter.stock_basic(target).dataset == "stock_basic"
    assert adapter.index_daily(target, ["000001.SH"]).dataset == "index_daily"
    assert adapter.adj_factor(target).dataset == "adj_factor"
