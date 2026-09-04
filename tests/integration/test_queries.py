from datetime import date

import pytest

from src.queries.dashboard_queries import check_summary, latest_day, list_days, market_summary, top_themes
from src.queries.evidence_queries import evidence_list
from src.queries.statistics_queries import driver_statistics, lifecycle_statistics
from src.queries.stock_queries import search_stocks, stock_detail, stock_history
from src.queries.theme_queries import list_themes, theme_detail, theme_history
from src.services.import_service import import_review
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import AnalysisSnapshot, ReviewImport, TradingDay
from tests.integration.test_import_daily_review import write_review
from tests.unit.test_review_validation import valid_review


@pytest.fixture()
def seeded_session(tmp_path):
    db = tmp_path / "queries.db"
    first = valid_review()
    first["date"] = "2026-08-31"
    second = valid_review()
    second["date"] = "2026-09-01"
    import_review(write_review(tmp_path, first, "first.json"), db, tmp_path / "archive")
    import_review(write_review(tmp_path, second, "second.json"), db, tmp_path / "archive")
    with session_factory(create_db_engine(db))() as session:
        yield session


def test_dashboard_lists_only_passed_real_days(tmp_path):
    engine = create_db_engine(tmp_path / "formal.db")
    create_schema(engine)
    factory = session_factory(engine)
    with factory.begin() as session:
        imports = [
            ReviewImport(
                source_path=f"{status}.json",
                sha256=status * 8,
                archive_path="x",
                status="success",
            )
            for status in ("passed", "draft")
        ]
        session.add_all(imports)
        session.flush()
        session.add_all(
            [
                TradingDay(
                    trade_date=date(2026, 9, 1),
                    data_kind="real",
                    strict_mode=True,
                    completeness_score=100,
                    missing_items="[]",
                    market_regime="测试",
                    position_min=0,
                    position_max=2,
                    import_id=imports[0].id,
                ),
                TradingDay(
                    trade_date=date(2026, 9, 2),
                    data_kind="real",
                    strict_mode=True,
                    completeness_score=80,
                    missing_items="[]",
                    market_regime="测试",
                    position_min=0,
                    position_max=2,
                    import_id=imports[1].id,
                ),
            ]
        )
        session.add_all(
            [
                AnalysisSnapshot(
                    trade_date=date(2026, 9, 1),
                    status="PASSED",
                    rule_version="test",
                    data_version="passed",
                    confidence=100,
                    result_json="{}",
                ),
                AnalysisSnapshot(
                    trade_date=date(2026, 9, 2),
                    status="DRAFT_ONLY",
                    rule_version="test",
                    data_version="draft",
                    confidence=80,
                    result_json="{}",
                ),
            ]
        )
    with factory() as session:
        assert [row.trade_date.isoformat() for row in list_days(session)] == ["2026-09-01"]


def test_dashboard_queries_use_formal_real_snapshots(seeded_session):
    assert len(list_days(seeded_session)) == 2
    day = latest_day(seeded_session)
    assert market_summary(day)["advancers"] == 3386
    themes = top_themes(seeded_session, day.id)
    assert len(themes) == 1
    assert check_summary(seeded_session, day.id)["pending"] == 1


def test_theme_and_stock_history_are_queryable(seeded_session):
    theme = next(theme for theme in list_themes(seeded_session) if theme.canonical_name == "主题甲")
    detail = theme_detail(seeded_session, theme.id)

    assert detail["name"] == "主题甲"
    assert len(theme_history(seeded_session, theme.id)) == 2
    assert search_stocks(seeded_session, "300308")[0]["name"] == "测试中军"
    assert stock_detail(seeded_session, "300308")["role"] == "中军"
    assert len(stock_history(seeded_session, "300308")) == 2


def test_statistics_ignore_null_scores_and_cover_fixed_catalog(seeded_session):
    stats = driver_statistics(seeded_session)

    assert len(stats) == 41
    assert any(item["average_score"] is not None for item in stats)
    assert sum(item["count"] for item in lifecycle_statistics(seeded_session)) == 2


def test_evidence_filters_and_empty_database(tmp_path, seeded_session):
    assert len(evidence_list(seeded_session, level="B", verified=True)) == 2
    engine = create_db_engine(tmp_path / "empty.db")
    create_schema(engine)
    with session_factory(engine)() as empty:
        assert latest_day(empty) is None
        assert list_days(empty) == []
        assert search_stocks(empty, "任何") == []
