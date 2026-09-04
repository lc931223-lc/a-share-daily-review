import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from sqlalchemy import func, select

from src.services.import_service import import_review
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import MarketDaily, MarketPacketLog, OfficialAnnouncement, OfficialPolicy, ScoreHistory, StockDailyReview, ThemeDailyReview, ValidationResult
from tests.integration.test_import_daily_review import write_review
from tests.unit.test_review_validation import valid_review
from tools.update_validation_results import main as update_validation_results_main
from tools.run_daily_pipeline import main as run_daily_pipeline_main


ROOT = Path(__file__).resolve().parents[2]


def test_official_review_schema_accepts_chatgpt_review_contract():
    schema = json.loads((ROOT / "schemas" / "official_review.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(valid_review())


def test_official_review_import_writes_three_layer_tables(tmp_path):
    db = tmp_path / "review.db"
    import_review(write_review(tmp_path, valid_review()), db, tmp_path / "archive")
    with session_factory(create_db_engine(db))() as session:
        assert session.scalar(select(func.count()).select_from(ThemeDailyReview)) == 1
        assert session.scalar(select(func.count()).select_from(StockDailyReview)) == 1
        assert session.scalar(select(func.count()).select_from(ScoreHistory)) == 2


def test_update_validation_results_persists_pending_snapshot(tmp_path):
    db = tmp_path / "review.db"
    import_review(write_review(tmp_path, valid_review()), db, tmp_path / "archive")
    assert update_validation_results_main(["--date", "2026-09-01", "--database", str(db)]) == 0
    with session_factory(create_db_engine(db))() as session:
        row = session.scalar(select(ValidationResult))
        assert row.status == "pending"
        assert row.entity_key == "主题甲"


def test_resolved_tomorrow_check_creates_validation_result(tmp_path):
    db = tmp_path / "review.db"
    archive = tmp_path / "archive"
    import_review(write_review(tmp_path, valid_review(), "first.json"), db, archive)
    second = copy.deepcopy(valid_review())
    second["date"] = "2026-09-02"
    second["tomorrow_checks"] = []
    second["tomorrow_check_updates"] = [{"check_id": 1, "status": "weakened", "result": "次日承接转弱"}]
    import_review(write_review(tmp_path, second, "second.json"), db, archive)
    with session_factory(create_db_engine(db))() as session:
        row = session.scalar(select(ValidationResult).where(ValidationResult.status == "weakened"))
        assert row.result == "次日承接转弱"


def test_market_packet_tables_exist_in_schema(tmp_path):
    engine = create_db_engine(tmp_path / "packet.db")
    create_schema(engine)
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(MarketDaily)) == 0
        assert session.scalar(select(func.count()).select_from(MarketPacketLog)) == 0
        assert session.scalar(select(func.count()).select_from(OfficialAnnouncement)) == 0
        assert session.scalar(select(func.count()).select_from(OfficialPolicy)) == 0


def test_daily_pipeline_waits_when_official_review_is_missing(monkeypatch, tmp_path, capsys):
    import tools.run_daily_pipeline as pipeline

    packet = {
        "data_quality": {"status": "GOOD", "score": 91},
        "meta": {"trade_date": "2026-09-02"},
    }
    monkeypatch.setattr(pipeline, "build_market_packet", lambda trade_date, refresh=False: packet)
    monkeypatch.setattr(pipeline, "write_outputs", lambda packet: {"packet": tmp_path / "packet.json"})
    code = run_daily_pipeline_main(["--date", "2026-09-02", "--database", str(tmp_path / "review.db")])
    output = capsys.readouterr().out
    assert code == 0
    assert "packet_status=SUCCESS" in output
    assert "official_review_status=WAITING" in output
