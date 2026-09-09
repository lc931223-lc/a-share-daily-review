from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from src.market_packet.trading_calendar import load_trading_calendar
from src.opportunity_radar.contracts import CATEGORIES, SHANGHAI, VERSION, digest, objective_guard, stamp, visible
from src.opportunity_radar.changes import latest_changes
from src.opportunity_radar.feedback import measure, market_validation_rows
from src.opportunity_radar.relations import transmission_paths
from src.opportunity_radar.schema import schema
from src.opportunity_radar.storage import ObservationStore, receipt_matches

LIMITS = {"positive_change_candidates": 20, "negative_risk_candidates": 10, "theme_candidates": 15,
          "company_specific_candidates": 20, "commodity_observations": 20, "macro_observations": 15,
          "overseas_lead_observations": 20, "industry_transmission_mapping": 50}
POSITIVE_EVENTS = {"ORDER_CONFIRMED", "SHIPMENT_CONFIRMED", "MASS_PRODUCTION", "COMMERCIAL_REVENUE", "TENDER_WIN", "BUYBACK", "INCREASE_HOLDING", "SMALL_BATCH", "PRODUCTION_STARTED", "FUNDING", "PROJECT", "PROCUREMENT", "SUBSIDY"}
NEGATIVE_EVENTS = {"ORDER_CANCELLED", "CUSTOMER_LOSS", "DECREASE_HOLDING", "REGULATORY_TIGHTENING"}


def mechanical_key(row):
    change = row.get("changes", {}).get("change_1d")
    return (row.get("source_tier", 4), -(abs(change) if change is not None else 0),
            -stamp(row["first_seen_at"]).timestamp() if stamp(row.get("first_seen_at")) else 0,
            len(row.get("data_gaps", [])), row.get("observation_id", ""))


def candidates(observations):
    positive, negative = [], []
    for row in observations:
        delta = row["changes"].get("delta")
        event = row["facts"].get("current_stage") or row["facts"].get("event_type") or row["facts"].get("action") or row["facts"].get("policy_stage")
        direction = None
        if delta is not None and delta != 0:
            direction = "INCREASE" if delta > 0 else "DECREASE"
            if row.get("metric") in {"inventory", "credit_spread"}:
                direction = "DECREASE" if delta > 0 else "INCREASE"
        elif row.get("body_evidence"):
            direction = "INCREASE" if event in POSITIVE_EVENTS else "DECREASE" if event in NEGATIVE_EVENTS else None
        if direction is None:
            continue
        candidate = {"entity": row["entity"], "theme": row["theme"], "stock_code": row["stock_code"],
                     "candidate_type": "COMPANY_SPECIFIC_CANDIDATE" if row["stock_code"] else "THEME_LEVEL_CANDIDATE",
                     "signal_type": row["signal_type"], "observation_id": row["observation_id"],
                     "signal_first_seen_date": max(stamp(row["first_seen_at"]), stamp(row["published_at"]) or stamp(row["first_seen_at"])).date().isoformat(),
                     "signal_first_seen_at": max(stamp(row["first_seen_at"]), stamp(row["published_at"]) or stamp(row["first_seen_at"])).isoformat(),
                     "source_date": row["source_date"], "direction": direction,
                     "semantics": "OBSERVED_CHANGE_NOT_EXPECTED_STOCK_RETURN",
                     "changes": row["changes"], "source_tier": row["source_tier"],
                     "first_seen_at": row["first_seen_at"], "data_gaps": row["data_gaps"]}
        (positive if direction == "INCREASE" else negative).append(candidate)
    return sorted(positive, key=mechanical_key), sorted(negative, key=mechanical_key)


def validate(packet):
    objective_guard(packet)
    Draft202012Validator(schema()).validate(packet)
    cutoff = stamp(packet["meta"]["as_of"])
    if cutoff is None or cutoff.date().isoformat() != packet["meta"]["trade_date"]:
        raise ValueError("SNAPSHOT_AS_OF_DATE_MISMATCH")
    if packet["meta"]["snapshot_type"] == "MORNING" and cutoff.time() > time(8, 20):
        raise ValueError("MORNING_FREEZE_DEADLINE_PASSED")
    for field in CATEGORIES.values():
        for row in packet[field]:
            if not visible(row, cutoff) or not row["as_of_valid"]:
                raise ValueError("AS_OF_GATE_FAILED")


def compact(packet):
    result = copy.deepcopy(packet)
    counts = {k: len(result[k]) for k in CATEGORIES.values()}
    counts.update({k: len(result[k]) for k in LIMITS})
    for field, limit in LIMITS.items():
        result[field] = result[field][:limit]
    disclosures = [row for key in CATEGORIES.values() if key not in {"commodity_observations", "macro_observations", "overseas_lead_observations", "market_structure_observations"} for row in result[key]]
    keep = {r["observation_id"] for r in sorted(disclosures, key=mechanical_key)[:30]}
    for field in CATEGORIES.values():
        if field not in {"commodity_observations", "macro_observations", "overseas_lead_observations", "market_structure_observations"}:
            result[field] = [r for r in result[field] if r["observation_id"] in keep]
    result["market_structure_observations"] = result["market_structure_observations"][:20]
    retained = {r["observation_id"] for field in CATEGORIES.values() for r in result[field]}
    for field in ("positive_change_candidates", "negative_risk_candidates", "theme_candidates", "company_specific_candidates", "factor41_mapping"):
        result[field] = [r for r in result[field] if r["observation_id"] in retained]
    for field in CATEGORIES.values():
        for row in result[field]:
            row["history_references"] = row["history_references"][-20:]
    result["signal_history"] = result["signal_history"][-100:]
    result["lead_time_statistics"]["records"] = result["lead_time_statistics"]["records"][:50]
    result["compact_metadata"] = {"selection": "source_tier, absolute_change, freshness, completeness, stable_id",
                                  "available_counts": counts,
                                  "retained_counts": {k: len(result[k]) for k in counts},
                                  "full_packet_required_for_complete_history": True}
    validate(result)
    return result


def _exclusive_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def _freeze_receipt(full, small, packet):
    receipt = full.with_name(full.stem + "_receipt.json")
    if not receipt.exists():
        payload = {"full_canonical_sha256": digest(packet),
                   "compact_canonical_sha256": digest(json.loads(small.read_text(encoding="utf-8"))),
                   "snapshot_as_of": packet["meta"]["as_of"],
                   "recorded_at": datetime.now(SHANGHAI).isoformat()}
        _exclusive_json(receipt, payload)
    recorded = json.loads(receipt.read_text(encoding="utf-8"))
    if recorded["full_canonical_sha256"] != digest(packet) or recorded["compact_canonical_sha256"] != digest(json.loads(small.read_text(encoding="utf-8"))):
        raise ValueError("FROZEN_SNAPSHOT_HASH_MISMATCH")


def _verify_sources(root, packet):
    for source in packet["source_manifest"]:
        sha = (source.get("provenance") or {}).get("sha256")
        original = Path(root) / str(source.get("path") or "")
        archive = Path(root) / "data/raw/opportunity_radar/provenance" / f"{sha}.json"
        if not any(p.is_file() and p.resolve().is_relative_to(Path(root).resolve()) and receipt_matches(p.read_bytes(), sha) for p in (original, archive)):
            raise ValueError("RADAR_SOURCE_PROVENANCE_UNAVAILABLE")


class RadarPipeline:
    def __init__(self, root, *, now=None):
        self.root = Path(root)
        self.now = now or (lambda: datetime.now(SHANGHAI))
        self.store = ObservationStore(self.root)

    def build(self, day, snapshot, *, as_of=None, replay=False, rows=None):
        current = self.now().astimezone(SHANGHAI)
        if snapshot not in {"MORNING", "EOD"}:
            raise ValueError("UNSUPPORTED_SNAPSHOT")
        end = datetime.combine(day, time(8, 20) if snapshot == "MORNING" else time(23, 59, 59), SHANGHAI)
        cutoff = stamp(as_of) if as_of else min(end, current)
        if cutoff is None or cutoff > end or cutoff > current or cutoff.date() != day:
            raise ValueError("INVALID_AS_OF")
        if not replay and snapshot == "MORNING" and current > end:
            raise ValueError("MORNING_FREEZE_DEADLINE_PASSED_USE_REPLAY")
        if not replay and day < current.date():
            raise ValueError("HISTORICAL_SNAPSHOT_REQUIRES_REPLAY")
        if not replay and snapshot == "EOD" and current < datetime.combine(day, time(15, 5), SHANGHAI):
            raise ValueError("MARKET_NOT_CLOSED")
        history = rows if rows is not None else self.store.all()
        selected = latest_changes(history, cutoff)
        # A stale/non-reconciled partial daily history is not a daily change signal.
        calendar = load_trading_calendar(day, cache_root=self.root / "data/reference")
        opens = [r.cal_date.isoformat() for r in calendar if r.is_open]
        for row in selected:
            if row["signal_type"] == "MARKET_STRUCTURE_AND_FLOW":
                dates = sorted({r["source_date"] for r in history if r["observation_id"] in row["history_references"]})
                expected = [d for d in opens if dates[0] <= d <= dates[-1]] if dates else []
                if dates != expected:
                    row["changes"] = {}
                    row["data_gaps"] = sorted(set(row["data_gaps"] + ["INCOMPLETE_TRADING_DAY_SERIES"]))
        positive, negative = candidates(selected)
        self._inherit_episode_dates(positive + negative, cutoff)
        combined = sorted(positive + negative, key=mechanical_key)
        gaps = [{"signal_type": category, "status": "UNAVAILABLE", "reason": "NO_AS_OF_ADMISSIBLE_OBSERVATIONS"}
                for category in CATEGORIES if not any(r["signal_type"] == category for r in selected)]
        excluded = sum(not visible(r, cutoff) for r in history)
        if excluded:
            gaps.append({"status": "UNAVAILABLE", "reason": "FUTURE_OR_UNTIMED_OBSERVATIONS_EXCLUDED", "count": excluded})
        gaps += [{"signal_type": r["signal_type"], "observation_id": r["observation_id"], "status": r["data_quality"],
                  "reason": ";".join(r["data_gaps"])} for r in selected if r["data_gaps"]]
        relation_path = self.root / "data/reference/opportunity_relations.json"
        edges = json.loads(relation_path.read_text(encoding="utf-8")) if relation_path.exists() else []
        relations = transmission_paths(edges, cutoff)
        if not relations:
            gaps.append({"status": "UNAVAILABLE", "reason": "NO_VERIFIED_COMPANY_OR_TRANSMISSION_EDGES; taxonomy is not evidence"})
        taxonomy = json.loads((self.root / "config/opportunity_radar_taxonomy.json").read_text(encoding="utf-8"))
        market_context = {"status": "UNAVAILABLE", "source_date": None}
        previous = max((r.cal_date for r in calendar if r.is_open and r.cal_date < day), default=None)
        market_day = previous if snapshot == "MORNING" else day
        market_path = self.root / "data/market_packets" / f"{market_day}.json"
        if market_path.exists():
            market = json.loads(market_path.read_text(encoding="utf-8"))
            seen = stamp(market.get("meta", {}).get("generated_at"))
            if seen and seen <= cutoff and market.get("meta", {}).get("trade_date") == str(market_day):
                market_context = {"status": market["data_quality"]["status"], "source_date": str(market_day),
                                  "usage": "PREVIOUS_CLOSE_REFERENCE" if snapshot == "MORNING" else "CURRENT_CLOSE",
                                  "total_market_turnover": market.get("liquidity", {}).get("total_market_turnover"),
                                  "rise_count": market.get("market_breadth", {}).get("rise_count"),
                                  "fall_count": market.get("market_breadth", {}).get("fall_count")}
        manifest = {r["source_path"] or r["url"]: {"path": r["source_path"], "url": r["url"],
                    "source": r["source"], "provenance": r["provenance"], "source_tier": r["source_tier"]} for r in history if visible(r, cutoff)}
        packet = {"meta": {"schema_version": VERSION, "trade_date": str(day), "snapshot_type": snapshot,
                           "as_of": cutoff.isoformat(), "data_role": "OBJECTIVE_OPPORTUNITY_EVIDENCE",
                           "final_judgement_owner": "chatgpt", "execution_mode": "AS_OF_REPLAY" if replay else "LIVE"},
                  **{field: sorted([r for r in selected if r["signal_type"] == category], key=mechanical_key) for category, field in CATEGORIES.items()},
                  "market_context": market_context, "technology_supply_chain_mapping": taxonomy,
                  "industry_transmission_mapping": relations,
                  "positive_change_candidates": positive, "negative_risk_candidates": negative,
                  "theme_candidates": [r for r in combined if not r["stock_code"]],
                  "company_specific_candidates": [r for r in combined if r["stock_code"]],
                  "factor41_mapping": [{k: r[k] for k in ("observation_id", "mapped_factor_ids", "mapping_method", "mapping_source", "mapping_confidence")} for r in selected],
                  "signal_history": [{k: r[k] for k in ("observation_id", "entity", "metric", "value", "source_date", "first_seen_at")} for r in history if visible(r, cutoff)],
                  "lead_time_statistics": measure(combined, market_validation_rows(history, opens, cutoff), opens, day),
                  "data_gaps": gaps, "source_manifest": list(manifest.values())}
        validate(packet)
        return packet

    def _inherit_episode_dates(self, candidates_now, cutoff):
        previous = []
        for path in (self.root / "data/opportunity_radar").glob("????-??-??_*.json"):
            if path.stem.split("_")[-1] not in {"morning", "eod"}:
                continue
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
                meta = packet["meta"]
                if meta["execution_mode"] != "LIVE" or stamp(meta["as_of"]) > cutoff:
                    continue
                verified = read_context(self.root, date.fromisoformat(meta["trade_date"]), meta["snapshot_type"])
                previous.append(verified["packet"])
            except (ValueError, KeyError, OSError):
                continue
        if not previous:
            return
        latest = max(previous, key=lambda p: stamp(p["meta"]["as_of"]))
        key = lambda r: (r["entity"], r["signal_type"], r["direction"])
        old = {key(r): r for r in latest["positive_change_candidates"] + latest["negative_risk_candidates"]}
        for candidate in candidates_now:
            prior = old.get(key(candidate))
            if prior:
                candidate["signal_first_seen_date"] = prior["signal_first_seen_date"]
                candidate["signal_first_seen_at"] = prior.get("signal_first_seen_at", prior["first_seen_at"])

    def write(self, packet):
        validate(packet)
        _verify_sources(self.root, packet)
        meta = packet["meta"]
        folder = self.root / "data/opportunity_radar"
        if meta["execution_mode"] == "AS_OF_REPLAY":
            folder /= "replay"
        path = folder / f"{meta['trade_date']}_{meta['snapshot_type'].lower()}.json"
        small = path.with_name(path.stem + "_compact.json")
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            validate(existing)
            # Frozen snapshots are immutable; an interrupted compact write is repairable.
            if not small.exists():
                _exclusive_json(small, compact(existing))
            _freeze_receipt(path, small, existing)
            return path, small, existing
        _exclusive_json(path, packet)
        _exclusive_json(small, compact(packet))
        _freeze_receipt(path, small, packet)
        return path, small, packet


def read_context(root, day, snapshot="MORNING"):
    path = Path(root) / "data/opportunity_radar" / f"{day}_{snapshot.lower()}.json"
    if not path.exists():
        return {"status": "UNAVAILABLE", "path": None, "score_effect": 0}
    packet = json.loads(path.read_text(encoding="utf-8"))
    validate(packet)
    small = path.with_name(path.stem + "_compact.json")
    receipt = path.with_name(path.stem + "_receipt.json")
    if not receipt.exists() or not small.exists():
        raise ValueError("RADAR_FREEZE_RECEIPT_UNAVAILABLE")
    recorded = json.loads(receipt.read_text(encoding="utf-8"))
    if recorded["full_canonical_sha256"] != digest(packet) or recorded["compact_canonical_sha256"] != digest(json.loads(small.read_text(encoding="utf-8"))):
        raise ValueError("FROZEN_SNAPSHOT_HASH_MISMATCH")
    if packet["meta"]["trade_date"] != str(day) or packet["meta"]["execution_mode"] != "LIVE":
        raise ValueError("RADAR_CONTEXT_DATE_OR_MODE_MISMATCH")
    _verify_sources(root, packet)
    return {"status": "AVAILABLE", "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "score_effect": 0, "packet": packet}


def read_only_summary(root, day):
    """Optional adapter for Auction and Daily Review; never changes scores."""
    try:
        context = read_context(root, day)
    except (OSError, ValueError, KeyError, ValidationError):
        return {"status": "UNAVAILABLE", "score_effect": 0, "reason": "RADAR_RECEIPT_OR_SCHEMA_INVALID"}
    if context["status"] != "AVAILABLE":
        return context
    packet = context.pop("packet")
    records = packet["positive_change_candidates"] + packet["negative_risk_candidates"]
    leads = {(r["entity"], r["signal_type"]): r.get("lead_trading_days") for r in packet["lead_time_statistics"].get("records", [])}
    context["signals"] = [{"entity": r["entity"], "theme": r["theme"], "stock_code": r["stock_code"],
                           "radar_first_seen_date": r["signal_first_seen_date"],
                           "radar_signal_types": [r["signal_type"]],
                           "lead_days_before_market_confirmation": leads.get((r["entity"], r["signal_type"])),
                           "observation_id": r["observation_id"]} for r in records[:30]]
    context["as_of"] = packet["meta"]["as_of"]
    return context
