from types import SimpleNamespace

import pytest

from src.domain.market_data import GateStatus
from src.services.review_builder import FormalReviewBlocked, build_review


@pytest.fixture
def snapshot():
    return SimpleNamespace(
        trade_date="2026-09-01",
        gate=SimpleNamespace(status=GateStatus.PASSED, confidence=92),
        theme_memberships={"主题甲": ["600001.SH"]},
        stocks=[
            SimpleNamespace(
                ts_code="600001.SH",
                code="600001",
                name="测试银行",
                theme="主题甲",
                board_height=2,
                amount=30,
            )
        ],
        advancers=3200,
        decliners=1800,
        limit_up_count=88,
        limit_down_count=5,
        failed_limit_count=12,
        max_board_height=6,
        index_pct_chg=0.6,
    )


def test_analysis_contains_only_observed_themes(snapshot):
    result = build_review(snapshot)
    observed = set(snapshot.theme_memberships)

    assert {theme.name for theme in result.main_themes} <= observed


def test_unobserved_examples_never_appear(snapshot):
    rendered = build_review(snapshot).model_dump_json()

    assert "AI算力" not in rendered
    assert "中际旭创" not in rendered


def test_review_builder_blocks_non_passed_gate(snapshot):
    snapshot.gate.status = GateStatus.FAILED

    with pytest.raises(FormalReviewBlocked):
        build_review(snapshot)
