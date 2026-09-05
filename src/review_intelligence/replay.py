from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


def summarize_replay(root: Path, start: date, end: date) -> dict[str, Any]:
    folder = root / "data" / "review_intelligence"
    packets = []
    for path in sorted(folder.glob("????-??-??.json")):
        if start.isoformat() <= path.stem <= end.isoformat():
            packets.append(json.loads(path.read_text(encoding="utf-8")))
    cycle_counts = Counter(label for packet in packets for label in packet.get("cycle_candidates", []))
    dominant_styles = [_top_key(packet.get("style_strength_ranking", []), "style") for packet in packets]
    top_themes = [_top_key(packet.get("theme_features", []), "theme_name") for packet in packets]
    scenarios = {
        "main_up_stage": [packet["meta"]["trade_date"] for packet in packets if "MAIN_UP_CANDIDATE" in packet.get("cycle_candidates", [])],
        "retreat_stage": [packet["meta"]["trade_date"] for packet in packets if "RETREAT_CANDIDATE" in packet.get("cycle_candidates", [])],
        "high_low_switch": _high_low_switch_dates(packets),
        "new_old_theme_switch": _change_dates(packets, top_themes),
        "leader_strengthening": _leader_strengthening_dates(packets),
        "catch_up": [packet["meta"]["trade_date"] for packet in packets if any(row.get("role_candidate") == "CATCH_UP_CANDIDATE" for row in packet.get("role_candidates", []))],
        "false_breakout": [packet["meta"]["trade_date"] for packet in packets if any(row.get("risk_flags") for row in packet.get("trend_chip_candidates", []))],
    }
    return {
        "schema_version": "review_intelligence_replay.1", "start_date": start.isoformat(),
        "end_date": end.isoformat(), "trading_day_count": len(packets),
        "cycle_candidate_counts": dict(cycle_counts),
        "dominant_style_change_count": sum(left != right for left, right in zip(dominant_styles, dominant_styles[1:])),
        "top_theme_change_count": sum(left != right for left, right in zip(top_themes, top_themes[1:])),
        "role_candidate_count": sum(len(packet.get("role_candidates", [])) for packet in packets),
        "scenario_evidence_dates": scenarios,
        "limitations": [
            "Theme history before archived Market Packets uses an industry aggregation proxy.",
            "Candidate labels are objective screening outputs, not final market-cycle conclusions.",
        ],
    }


def _top_key(rows, key):
    return rows[0].get(key) if rows else None


def _change_dates(packets, values):
    return [packets[index]["meta"]["trade_date"] for index in range(1, len(values)) if values[index] != values[index - 1]]


def _leader_strengthening_dates(packets):
    dates = []
    previous = {}
    for packet in packets:
        current = {f"{row['theme']}:{row['ts_code']}": row.get("role_scores", {}).get("leader") for row in packet.get("role_candidates", [])}
        if any(key in previous and value is not None and previous[key] is not None and value > previous[key] for key, value in current.items()):
            dates.append(packet["meta"]["trade_date"])
        previous = current
    return dates


def _high_low_switch_dates(packets):
    dates, previous_sign = [], None
    for packet in packets:
        scores = {row.get("style"): row.get("style_strength_score") for row in packet.get("style_strength_ranking", [])}
        differences = []
        for high, low in (("high_price_position", "low_price_position"), ("large_cap", "small_cap")):
            if scores.get(high) is not None and scores.get(low) is not None:
                differences.append(scores[high] - scores[low])
        current_sign = None if not differences else 1 if sum(differences) > 0 else -1
        if previous_sign is not None and current_sign is not None and current_sign != previous_sign:
            dates.append(packet["meta"]["trade_date"])
        if current_sign is not None:
            previous_sign = current_sign
    return dates
