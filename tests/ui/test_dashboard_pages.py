import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.services.import_service import import_review
from tests.integration.test_import_daily_review import write_review


ROOT = Path(__file__).resolve().parents[2]
PAGES = list((ROOT / "pages").glob("*.py"))
FIXTURE = ROOT / "tests" / "fixtures" / "reviews" / "market_alpha_complete.json"


def review_fixture():
    return json.loads(FIXTURE.read_text("utf-8"))


def rendered_markdown(app):
    return "\n".join(item.value for item in app.markdown)


@pytest.mark.parametrize("page", PAGES, ids=lambda path: path.stem)
def test_page_runs_without_uncaught_exception(page, tmp_path, monkeypatch):
    db = tmp_path / "pages.db"
    import_review(write_review(tmp_path, review_fixture(), "real.json"), db, tmp_path / "archive")
    monkeypatch.setenv("A_SHARE_DB_PATH", str(db))
    app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    app = app.switch_page(page.relative_to(ROOT).as_posix()).run()
    assert not app.exception


def test_quality_page_discloses_status(tmp_path, monkeypatch):
    db = tmp_path / "quality.db"
    import_review(write_review(tmp_path, review_fixture(), "real.json"), db, tmp_path / "archive")
    monkeypatch.setenv("A_SHARE_DB_PATH", str(db))
    app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    app = app.switch_page("pages/6_数据质量.py").run()

    assert not app.exception
    assert "数据质量" in str(app)
    assert "正式真实数据" in rendered_markdown(app)
