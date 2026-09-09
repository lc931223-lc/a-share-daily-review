"""Production recovery constraints, using isolated synthetic fixtures only."""

import hashlib
import json
from pathlib import Path

import pytest

from src.auction.production import optional_review_input
from src.formal_review.objective_inputs import build_inputs
from src.formal_review.theme_types import classify_theme, selection_types
from src.formal_review.persistence import import_record, load_previous_formal
from tests.integration.test_first_formal_review_handoff import formal
from tests.unit.test_chatgpt_objective_inputs import DAY, root  # noqa: F401
from tests.integration.test_first_formal_review_handoff import DAYS, write


@pytest.mark.parametrize(
    "name,kind",
    [
        ("基金重仓", "OWNERSHIP_TAG"),
        ("保险重仓", "OWNERSHIP_TAG"),
        ("融资融券", "FINANCING_TAG"),
        ("含H股", "STYLE_TAG"),
        ("业绩预增", "PERFORMANCE_TAG"),
        ("业绩预降", "PERFORMANCE_TAG"),
        ("通信设备", "INDUSTRY"),
        ("半导体", "INDUSTRY"),
        ("CPO", "CONCEPT"),
        ("机器人", "CONCEPT"),
        ("沪深300", "INDEX_TAG"),
    ],
)
def test_theme_type_classification(name, kind):
    assert classify_theme({"theme_name": name}, {"通信设备", "半导体"}) == kind


def test_type_rules_precede_misleading_source_category():
    assert classify_theme({"theme_name": "融资融券", "source": "industry proxy"}) == "FINANCING_TAG"
    assert classify_theme({"theme_name": "未知分类"}) == "OTHER"
    assert classify_theme({"theme_name": "source-defined", "source_category": "event"}) == "EVENT"


def test_types_do_not_change_compact_mechanical_selection(root):
    path = root / f"data/market_packets/{DAY}.json"
    market = json.loads(path.read_text(encoding="utf-8"))
    market["themes"] = [
        {"theme_name": name, "amount": 100 - i}
        for i, name in enumerate(
            ["基金重仓", "融资融券", "CPO"] + [f"fixture-{n}" for n in range(10)]
        )
    ]
    write(path, market)
    packet = build_inputs(root, DAY, DAYS)
    compact = json.loads(
        (root / f"data/chatgpt_review_inputs/{DAY}_compact.json").read_text(encoding="utf-8")
    )
    assert compact["theme_candidates"][0]["theme_type"] == "OWNERSHIP_TAG"
    assert compact["theme_candidates"][1]["theme_type"] == "FINANCING_TAG"
    assert len(compact["theme_candidates"]) == 10
    assert sum(compact["selection_metadata"]["truncated_by_type"].values()) == 3
    assert compact["selection_metadata"]["type_filter_applied"] is False
    assert compact["selection_metadata"] == selection_types(
        packet["theme_candidates"], compact["theme_candidates"]
    )


def test_failed_market_packet_blocks_chatgpt_input(root):
    path = root / f"data/market_packets/{DAY}.json"
    market = json.loads(path.read_text(encoding="utf-8"))
    market["data_quality"]["checks"][0]["status"] = "FAIL"
    write(path, market)
    with pytest.raises(ValueError, match="production gate"):
        build_inputs(root, DAY, DAYS)
    assert not (root / f"data/chatgpt_review_inputs/{DAY}.json").exists()


def test_previous_formal_provenance_is_git_newline_stable(root):
    imported = import_record(root, formal(), DAYS)
    path = Path(imported["path"])
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    _, prior = load_previous_formal(root, DAY, DAYS)
    assert prior["sha256"] == imported["sha256"]
    assert import_record(root, formal(), DAYS)["status"] == "UNCHANGED"


def frozen_fixture(root):
    # Only acceptance mechanics are under test; upstream payload schemas are fixtures.
    for name in ("auction_packet", "auction_packet_compact"):
        write(root / f"schemas/{name}.schema.json", {"type": "object", "required": ["meta"]})
    packet = {
        "meta": {"trade_date": str(DAY), "auction_frozen_at": f"{DAY}T09:25:02+08:00"},
        "data_quality": {"status": "PASS"},
        "auction_timeliness": {"status": "PASS"},
    }
    paths = [
        root / f"data/auction_packets/{DAY}.json",
        root / f"data/auction_packets/{DAY}_compact.json",
        root / f"data/auction_raw_frozen/{DAY}.json",
    ]
    for path in paths:
        write(path, packet)
    receipt = {"trade_date": str(DAY)} | {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in zip(("packet_sha256", "compact_sha256", "raw_sha256"), paths)
    }
    write(root / f"data/auction_runs/{DAY}.json", receipt)
    return paths


def test_valid_auction_optional_input(root):
    frozen_fixture(root)
    accepted, health = optional_review_input(root, DAY)
    assert accepted and health["status"] == "AVAILABLE"
    assert all(health["checks"].values())


@pytest.mark.parametrize(
    "problem", ["cross_date", "unfrozen", "quality", "timing", "sha", "schema", "raw_sha"]
)
def test_invalid_auction_is_unavailable_not_blocking(root, problem):
    paths = frozen_fixture(root)
    packet = json.loads(paths[0].read_text(encoding="utf-8"))
    if problem == "cross_date":
        packet["meta"]["trade_date"] = "2026-09-08"
    elif problem == "unfrozen":
        packet["meta"].pop("auction_frozen_at")
    elif problem in {"quality", "timing"}:
        packet["data_quality" if problem == "quality" else "auction_timeliness"]["status"] = "FAIL"
    elif problem == "schema":
        packet.pop("meta")
    write(paths[0], packet)
    receipt_path = root / f"data/auction_runs/{DAY}.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if problem != "sha":
        receipt["packet_sha256"] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    else:
        receipt["packet_sha256"] = "0" * 64
    if problem == "raw_sha":
        receipt.pop("raw_sha256")
    write(receipt_path, receipt)
    assert optional_review_input(root, DAY)[1]["status"] == "UNAVAILABLE"
    output = build_inputs(root, DAY, DAYS)
    assert output["source_manifest"]["auction_packets"]["status"] == "UNAVAILABLE"
