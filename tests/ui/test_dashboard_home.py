import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.services.import_service import import_review
from tests.integration.test_import_daily_review import write_review


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "reviews" / "market_alpha_complete.json"


def review_fixture():
    return json.loads(FIXTURE.read_text("utf-8"))


def rendered_markdown(app):
    return "\n".join(item.value for item in app.markdown)


def test_dashboard_home_runs_with_real_data(tmp_path, monkeypatch):
    db = tmp_path / "dashboard.db"
    import_review(write_review(tmp_path, review_fixture(), "real.json"), db, tmp_path / "archive")
    monkeypatch.setenv("A_SHARE_DB_PATH", str(db))
    app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "A股市场复盘 Dashboard"
    assert any(metric.label == "两市成交额" for metric in app.metric)
    assert not any(getattr(control, "label", "") == "数据类型" for control in app.selectbox)
    assert "模拟演示数据" not in rendered_markdown(app)
    assert "正式真实数据" in rendered_markdown(app)


def test_dashboard_home_has_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("A_SHARE_DB_PATH", str(tmp_path / "empty.db"))
    app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    assert not app.exception
    assert app.info[0].value == "当前筛选条件下暂无复盘数据"
