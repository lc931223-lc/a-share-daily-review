from datetime import date

import pytest

from src.adapters.base import AdapterError
from src.config.runtime import RuntimeSettings
from src.domain.market_data import GateStatus
from src.services.market_pipeline import build_pipeline


@pytest.mark.real_data
def test_historical_day_end_to_end(tmp_path):
    try:
        settings = RuntimeSettings.load()
    except RuntimeError as exc:
        pytest.skip(f"缺少真实数据凭据：{exc}")

    try:
        result = build_pipeline(settings, database_path=tmp_path / "real.db").collect(
            date(2026, 9, 1),
            mode="close",
        )
    except AdapterError as exc:
        pytest.skip(f"真实公开数据源暂不可达：{exc}")
    if result.gate.status != GateStatus.PASSED:
        failed = ", ".join(check.name for check in result.gate.checks if not check.passed)
        pytest.skip(f"真实公开数据源未达到正式门禁：{failed}")

    assert result.gate.status == GateStatus.PASSED
    assert result.snapshot is not None
    assert result.snapshot.status == "PASSED"
    assert result.snapshot.source_batches
