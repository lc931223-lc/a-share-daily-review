"""Durable stage receipts and immutable 09:25 reports; no market inference."""

import hashlib
import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
STAGES = (
    "SCHEDULER_STARTED",
    "PREFLIGHT_RUNNING",
    "PREFLIGHT_FAILED",
    "SOURCE_CONNECTED",
    "COLLECTION_FAILED",
    "GIT_SYNC_PENDING",
    "GIT_SYNC_FAILED",
    "PUSHED",
    "NOT_STARTED",
    "COLLECTING",
    "FORMAL_MATCH_PENDING",
    "AUCTION_FROZEN",
    "REPORT_READY",
    "POST_OPEN_VALIDATING",
    "POST_OPEN_COMPLETE",
    "EOD_RECONCILED",
)


def log_event(root, day, event, **details):
    path = root / "data/auction_logs" / str(day) / "live.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(timestamp=datetime.now(TZ).isoformat(), event=event, **details)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return entry


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def update_run(root, day, stage, **values):
    if stage not in STAGES:
        raise ValueError("unknown auction stage")
    path = root / "data/auction_runs" / f"{day}.json"
    record = read(path, {})
    if not record:
        record = dict(
            trade_date=str(day),
            started_at=datetime.now(TZ).isoformat(),
            auction_frozen_at=None,
            report_generated_at=None,
            post_open_started_at=None,
            post_open_completed_at=None,
            eod_completed_at=None,
            status="RUNNING",
            failures=[],
            retry_count=0,
            packet_path=None,
            compact_path=None,
            workflow_run_id=os.getenv("GITHUB_RUN_ID"),
        )
    record.update(stage=stage, status=values.pop("status", stage), **values)
    if not stage.endswith("FAILED"):
        record["last_successful_stage"] = stage
    entry = log_event(root, day, stage, **values)
    record.setdefault("stage_history", []).append(entry)
    write(path, record)
    return record


def timeliness(day, stats, generated, formal_rows):
    start = datetime.fromisoformat(stats["collection_start_time"])
    frozen = datetime.fromisoformat(stats["auction_frozen_at"])
    base = datetime.combine(day, time(9, 25), TZ)
    latency = (generated - base).total_seconds()
    formal_times = [str(r.get("snapshot_time") or "") for r in formal_rows]
    formal_ok = bool(formal_rows) and all("09:25" in value for value in formal_times)
    on_time = start <= datetime.combine(day, time(9, 15, 5), TZ)
    status = (
        "PASS"
        if on_time and formal_ok and 0 <= latency <= 60
        else "PARTIAL"
        if formal_ok and 0 <= latency <= 120
        else "FAIL"
    )
    if start > datetime.combine(day, time(9, 16), TZ):
        status = "FAIL"
    return dict(
        collection_start_time=start.isoformat(),
        last_checkpoint_time="09:25:00" if formal_ok else None,
        formal_match_time="09:25:00" if formal_ok else None,
        frozen_at=frozen.isoformat(),
        report_generated_at=generated.isoformat(),
        latency_from_0925_seconds=latency,
        status=status,
    )


def freeze_result(root, day, result, stats, now):
    packet = result["packet"]
    generated = now().astimezone(TZ)
    formal = [{"snapshot_time": value} for value in stats.get("formal_match_times", [])]
    timing = timeliness(day, stats, generated, formal)
    packet["auction_timeliness"] = timing
    packet["meta"].update(
        auction_frozen_at=stats["auction_frozen_at"],
        auction_report_generated_at=generated.isoformat(),
        auction_report_latency_seconds=timing["latency_from_0925_seconds"],
    )
    packet["auction_report_0925"] = packet["report"]
    packet["data_quality"]["production"] = dict(
        scheduler_started_on_time=not stats["late_start"],
        auction_frozen_before_open=datetime.fromisoformat(stats["auction_frozen_at"]).time()
        < time(9, 30),
        report_ready_before_0930=generated.time() < time(9, 30),
        previous_formal_review_status="READY"
        if packet["previous_context"]["official_review_loaded"]
        else "MISSING",
        post_open_independent=True,
        source_health="PASS"
        if packet["market_auction_summary"].get("stock_completion_rate") == 1
        else "PARTIAL",
        workflow_run_id=os.getenv("GITHUB_RUN_ID"),
        live_acceptance=timing["status"],
        production_readiness="LIVE_ACCEPTANCE_PENDING",
        late_start=stats["late_start"],
    )
    if stats["late_start"] or timing["status"] != "PASS":
        packet["report_status"] = "degraded"
    from src.auction.analysis import build_compact_packet

    compact = build_compact_packet(packet)
    compact.update(auction_timeliness=timing, auction_report_0925=packet["auction_report_0925"])
    path, compact_path = Path(result["paths"]["packet"]), Path(result["paths"]["compact_packet"])
    write(path, packet)
    write(compact_path, compact)
    update_run(
        root,
        day,
        "REPORT_READY",
        status="LATE_START" if stats["late_start"] else "REPORT_READY",
        auction_frozen_at=stats["auction_frozen_at"],
        report_generated_at=generated.isoformat(),
        packet_path=str(path),
        compact_path=str(compact_path),
        packet_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        compact_sha256=hashlib.sha256(compact_path.read_bytes()).hexdigest(),
    )
    result["compact_packet"] = compact
    return result


def resume_report(root, day):
    receipt = read(root / "data/auction_runs" / f"{day}.json", {})
    path = root / "data/auction_packets" / f"{day}.json"
    if not receipt.get("packet_sha256"):
        return None
    if (
        not path.exists()
        or hashlib.sha256(path.read_bytes()).hexdigest() != receipt["packet_sha256"]
    ):
        raise ValueError("frozen auction report hash mismatch; explicit --force required")
    compact_path = path.with_name(f"{day}_compact.json")
    if receipt.get("compact_sha256") and (
        not compact_path.exists()
        or hashlib.sha256(compact_path.read_bytes()).hexdigest() != receipt["compact_sha256"]
    ):
        raise ValueError("frozen compact report hash mismatch")
    return dict(
        packet=read(path),
        compact_packet=read(compact_path),
        reused=True,
        paths=dict(packet=str(path), compact_packet=str(compact_path), watchlist=None),
    )


def save_post_open(root, day, validation, now):
    path = root / "data/auction_post_open" / f"{day}.json"
    packet = root / "data/auction_packets" / f"{day}.json"
    digest = hashlib.sha256(packet.read_bytes()).hexdigest()
    result = read(path, {"trade_date": str(day), "auction_packet_sha256": digest, "snapshots": {}})
    if result["auction_packet_sha256"] != digest:
        raise ValueError("post-open belongs to a different frozen auction report")
    # Use actual observation time, never relabel a delayed scheduler as 09:35.
    key = validation.get("observed_at") or now.isoformat()
    result["snapshots"][key] = validation
    write(path, result)
    complete = (
        now.time() >= time(10, 0)
        and bool(validation.get("stocks"))
        and validation.get("coverage") == 1
    )
    update_run(
        root,
        day,
        "POST_OPEN_COMPLETE" if complete else "POST_OPEN_VALIDATING",
        status="POST_OPEN_COMPLETE" if complete else "PARTIAL",
        post_open_completed_at=now.isoformat() if complete else None,
    )
    return result
