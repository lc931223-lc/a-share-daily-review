from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from src.market_packet.packet_builder import log_packet_outputs
from src.storage.database import create_db_engine, session_factory
from src.storage.models import FactVersion, OfficialPolicy, QualityGateRun, SourceBatch, SourceFallback, SourceObservation


ROOT = Path(__file__).resolve().parents[2]


def test_market_packet_logging_is_audited_and_fact_versions_are_append_only(tmp_path):
    packet = json.loads((ROOT / "data" / "market_packets" / "2026-09-02.json").read_text(encoding="utf-8"))
    packet["policies"]["records"] = [{
        "title": "关于测试数据治理的通知", "normalized_title": "关于测试数据治理的通知", "agency": "测试部门",
        "published_at": "2026-09-02T10:00:00+08:00", "url": "https://example.gov.cn/policy/1",
        "summary": "第一版", "policy_level": "ministerial", "related_industries": [], "related_themes": [], "evidence_level": "A",
    }]
    paths = {name: tmp_path / f"{name}.json" for name in ("packet", "compact", "quality")}
    paths["packet"].write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    paths["compact"].write_text("{}", encoding="utf-8")
    paths["quality"].write_text("{}", encoding="utf-8")
    database = tmp_path / "audit.db"
    log_packet_outputs(packet, paths, database)

    second = copy.deepcopy(packet)
    second["meta"]["generated_at"] = (datetime.fromisoformat(packet["meta"]["generated_at"]) + timedelta(seconds=1)).isoformat()
    second["policies"]["records"][0]["summary"] = "第二版"
    paths["packet"].write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    log_packet_outputs(second, paths, database)

    factory = session_factory(create_db_engine(database))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceBatch)) > 0
        assert session.scalar(select(func.count()).select_from(SourceObservation)) > 0
        assert session.scalar(select(func.count()).select_from(SourceFallback)) > 0
        assert session.scalar(select(func.count()).select_from(QualityGateRun)) == 2
        versions = session.scalars(select(FactVersion).where(FactVersion.fact_type == "policy")).all()
        assert len(versions) == 2
        assert sum(item.is_current for item in versions) == 1
        assert session.scalar(select(func.count()).select_from(OfficialPolicy)) == 1
