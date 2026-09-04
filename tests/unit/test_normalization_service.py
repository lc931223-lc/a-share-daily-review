from datetime import date

import pytest

from src.services.normalization_service import (
    normalize_trade_date,
    normalize_turnover_to_yi,
    normalize_ts_code,
    resolve_observations,
)


def test_normalize_stock_code():
    assert normalize_ts_code("sh600000") == "600000.SH"
    assert normalize_ts_code("300750") == "300750.SZ"
    assert normalize_ts_code("688001") == "688001.SH"
    assert normalize_ts_code("830001") == "830001.BJ"


def test_normalize_rejects_unknown_code():
    with pytest.raises(ValueError, match="证券代码"):
        normalize_ts_code("123")


def test_normalize_trade_date():
    assert normalize_trade_date("20260901") == date(2026, 9, 1)
    assert normalize_trade_date("2026-09-01") == date(2026, 9, 1)


def test_normalize_turnover_to_yi_from_tushare_amount():
    assert normalize_turnover_to_yi(1234567.0, "thousand_yuan") == pytest.approx(12.34567)


def test_conflicting_supplement_is_preserved():
    resolved = resolve_observations(primary=94, supplement=97, field="limit_up_count")

    assert resolved.selected_value == 94
    assert resolved.selected_source == "primary"
    assert resolved.conflict is not None
    assert resolved.candidates["supplement"] == 97
