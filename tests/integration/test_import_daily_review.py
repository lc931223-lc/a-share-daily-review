import copy
import json

import pytest
from sqlalchemy import func, select

from src.services.import_service import ReviewImportError, import_review
from src.storage.database import create_db_engine, session_factory
from src.storage.models import ReviewImport, Theme, ThemeDailyScore, TradingDay
from tests.unit.test_review_validation import valid_review


def write_review(tmp_path, payload, name="review.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_writes_auditable_complete_day(tmp_path):
    db = tmp_path / "review.db"
    result = import_review(write_review(tmp_path, valid_review()), db, tmp_path / "archive")
    assert result["themes"] == 1
    assert (tmp_path / "archive" / result["sha256"][:2] / f"{result['sha256']}.json").exists()
    with session_factory(create_db_engine(db))() as session:
        assert session.scalar(select(func.count()).select_from(TradingDay)) == 1
        assert session.scalar(select(ReviewImport.status)) == "success"
        assert session.scalar(select(Theme.canonical_name)) == "主题甲"


def test_duplicate_date_and_kind_is_rejected_without_partial_day(tmp_path):
    db = tmp_path / "review.db"
    path = write_review(tmp_path, valid_review())
    import_review(path, db, tmp_path / "archive")
    with pytest.raises(ReviewImportError, match="重复导入|已存在"):
        import_review(path, db, tmp_path / "archive")
    with session_factory(create_db_engine(db))() as session:
        assert session.scalar(select(func.count()).select_from(TradingDay)) == 1
        assert session.scalar(select(func.count()).select_from(ReviewImport)) == 2


def test_invalid_payload_keeps_failed_audit_but_no_business_data(tmp_path):
    payload = valid_review()
    payload["main_themes"][0]["scores"]["base_logic_score"] = 99
    db = tmp_path / "review.db"
    with pytest.raises(ReviewImportError, match="base_logic_score"):
        import_review(write_review(tmp_path, payload), db, tmp_path / "archive")
    with session_factory(create_db_engine(db))() as session:
        assert session.scalar(select(func.count()).select_from(TradingDay)) == 0
        assert session.scalar(select(ReviewImport.status)) == "failed"


def test_delta_uses_previous_day_of_same_kind(tmp_path):
    first = valid_review()
    first.update({"date": "2026-08-31", "data_kind": "real", "strict_mode": True})
    second = copy.deepcopy(first)
    second["date"] = "2026-09-01"
    scores = second["main_themes"][0]["scores"]
    scores["base_logic_score"] = 40
    scores["total_score"] = 86
    db = tmp_path / "review.db"
    import_review(write_review(tmp_path, first, "first.json"), db, tmp_path / "archive")
    import_review(write_review(tmp_path, second, "second.json"), db, tmp_path / "archive")
    with session_factory(create_db_engine(db))() as session:
        rows = session.scalars(select(ThemeDailyScore).order_by(ThemeDailyScore.id)).all()
        assert rows[0].delta_score is None
        assert rows[1].delta_score == 2
