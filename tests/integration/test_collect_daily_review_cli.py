from types import SimpleNamespace

import collect_daily_review
from src.domain.market_data import GateStatus


def test_collect_cli_returns_zero_for_passed(capsys):
    pipeline = SimpleNamespace(
        collect=lambda trade_date, mode: SimpleNamespace(
            batch_ids=[1, 2],
            gate=SimpleNamespace(status=GateStatus.PASSED, checks=[]),
            fallbacks=[],
        )
    )

    exit_code = collect_daily_review.main(
        ["--date", "2026-09-01", "--mode", "close"],
        pipeline_factory=lambda: pipeline,
    )

    assert exit_code == 0
    assert "PASSED" in capsys.readouterr().out


def test_collect_cli_returns_three_for_failed(capsys):
    failed_check = SimpleNamespace(name="daily_quote_required_fields", passed=False)
    pipeline = SimpleNamespace(
        collect=lambda trade_date, mode: SimpleNamespace(
            batch_ids=[],
            gate=SimpleNamespace(status=GateStatus.FAILED, checks=[failed_check]),
            fallbacks=[],
        )
    )

    exit_code = collect_daily_review.main(
        ["--date", "2026-09-01", "--mode", "close"],
        pipeline_factory=lambda: pipeline,
    )

    assert exit_code == 3
    assert "daily_quote_required_fields" in capsys.readouterr().out
