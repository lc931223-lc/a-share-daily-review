import json
from datetime import date
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from src.reports.pdf_report import FormalReportBlocked, generate_pdf


def embedded_font_names(reader):
    names = set()
    for page in reader.pages:
        fonts = page.get("/Resources", {}).get("/Font", {})
        for font in fonts.values():
            base = font.get_object().get("/BaseFont")
            if base:
                names.add(str(base))
    return names


def extract_text(output):
    reader = PdfReader(output)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.fixture
def passed_snapshot():
    return SimpleNamespace(
        trade_date=date(2026, 9, 1),
        status="PASSED",
        rule_version="2026.09.02.1",
        data_version="fixture",
        confidence=92,
        result_json=json.dumps(
            {
                "schema_version": "2.0",
                "date": "2026-09-01",
                "market_regime": "修复",
                "position_min": 3,
                "position_max": 5,
                "advancers": 3200,
                "decliners": 1800,
                "limit_up_count": 88,
                "limit_down_count": 5,
                "main_themes": [{"name": "主题甲", "delta_reason": "真实观测"}],
                "stocks": [{"name": "测试中军", "code": "300308", "role_detail": "容量中军"}],
                "tomorrow_checks": [{"entity_key": "market", "description": "观察量能"}],
            },
            ensure_ascii=False,
        ),
    )


@pytest.fixture
def draft_snapshot(passed_snapshot):
    return SimpleNamespace(**{**vars(passed_snapshot), "status": "DRAFT_ONLY"})


def test_pdf_requires_passed_snapshot(tmp_path, draft_snapshot):
    with pytest.raises(FormalReportBlocked):
        generate_pdf(draft_snapshot, tmp_path / "draft.pdf")


def test_pdf_embeds_source_han_and_black_body(tmp_path, passed_snapshot):
    output = generate_pdf(passed_snapshot, tmp_path / "report.pdf")
    reader = PdfReader(output)

    assert len(reader.pages) >= 1
    assert any("SourceHanSans" in name for name in embedded_font_names(reader))
    assert extract_text(output).find("数据质量") >= 0
