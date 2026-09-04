import copy

import pytest
from sqlalchemy import select

from src.services.import_service import ReviewImportError, import_review
from src.storage.database import create_db_engine, session_factory
from src.storage.models import TomorrowCheck
from tests.integration.test_import_daily_review import write_review
from tests.unit.test_review_validation import valid_review


@pytest.mark.parametrize("status", ["confirmed", "weakened", "invalidated"])
def test_next_review_resolves_pending_check_without_overwriting_origin(tmp_path, status):
    first = valid_review()
    db = tmp_path / f"{status}.db"
    archive = tmp_path / "archive"
    import_review(write_review(tmp_path, first, f"{status}-first.json"), db, archive)

    second = copy.deepcopy(first)
    second["date"] = "2026-09-02"
    second["tomorrow_checks"] = []
    second["tomorrow_check_updates"] = [
        {"check_id": 1, "status": status, "result": "根据次日市场数据完成验证"}
    ]
    import_review(write_review(tmp_path, second, f"{status}-second.json"), db, archive)

    with session_factory(create_db_engine(db))() as session:
        check = session.scalar(select(TomorrowCheck))
        assert check.status == status
        assert check.description == "板块成交额是否继续扩大"
        assert check.proposed_day_id == 1
        assert check.resolved_day_id == 2


def test_resolved_check_cannot_be_resolved_twice(tmp_path):
    first = valid_review()
    db = tmp_path / "review.db"
    archive = tmp_path / "archive"
    import_review(write_review(tmp_path, first, "first.json"), db, archive)
    second = copy.deepcopy(first)
    second["date"] = "2026-09-02"
    second["tomorrow_check_updates"] = [
        {"check_id": 1, "status": "confirmed", "result": "已确认"}
    ]
    import_review(write_review(tmp_path, second, "second.json"), db, archive)
    third = copy.deepcopy(second)
    third["date"] = "2026-09-03"
    with pytest.raises(ReviewImportError, match="不存在或已解决"):
        import_review(write_review(tmp_path, third, "third.json"), db, archive)


def test_update_cannot_use_pending_status(tmp_path):
    payload = valid_review()
    payload["tomorrow_check_updates"] = [
        {"check_id": 1, "status": "pending", "result": "错误状态"}
    ]
    with pytest.raises(ReviewImportError, match="tomorrow_check_updates"):
        import_review(
            write_review(tmp_path, payload),
            tmp_path / "review.db",
            tmp_path / "archive",
        )
