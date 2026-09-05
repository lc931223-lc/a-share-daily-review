import json
from datetime import date

from src.inflection.fundamentals import load_fundamental_features


def test_future_announcements_are_rejected(tmp_path):
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    packet = {"announcements": {"records": [
        {"stock_code": "000001", "title": "未来业绩", "category": "earnings", "published_at": "2026-09-05T08:00:00+08:00", "confirmed_fact": True, "evidence_level": "A", "quality_status": "PASS"},
        {"stock_code": "000001", "title": "当日订单", "category": "order", "published_at": "2026-09-04T10:00:00+08:00", "confirmed_fact": True, "evidence_level": "A", "quality_status": "PASS"},
    ]}}
    (packet_dir / "2026-09-04.json").write_text(json.dumps(packet), encoding="utf-8")

    features, status = load_fundamental_features(tmp_path, date(2026, 9, 4))

    assert status["future_rejected"] == 1
    assert features["000001.SZ"]["main_catalyst"] == "当日订单"
    assert features["000001.SZ"]["catalyst_stage"] == "VALIDATING"


def test_confirmed_earnings_catalyst_is_realized(tmp_path):
    packet_dir = tmp_path / "data" / "market_packets"
    packet_dir.mkdir(parents=True)
    packet = {"announcements": {"records": [{
        "stock_code": "600001", "title": "业绩超预期", "category": "earnings",
        "published_at": "2026-09-04T14:00:00+08:00", "confirmed_fact": "净利润同比增长",
        "evidence_level": "A", "quality_status": "PASS",
    }]}}
    (packet_dir / "2026-09-04.json").write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    features, _ = load_fundamental_features(tmp_path, date(2026, 9, 4))

    assert features["600001.SH"]["fundamental_inflection_score"] == 10
    assert features["600001.SH"]["catalyst_stage"] == "REALIZED"
