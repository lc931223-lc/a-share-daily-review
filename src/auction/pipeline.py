from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.auction.analysis import build_compact_packet, build_objective_analysis
from src.auction.checkpoints import CHECKPOINTS, map_checkpoints
from src.auction.eltdx_source import AuctionCollection, EltdxAuctionSource
from src.auction.live_runner import LiveAuctionRunner
from src.auction.metrics import build_daily_summary
from src.auction.open_validation import apply_open_validation
from src.auction.post_open import PostOpenQuoteRouter, evaluate_post_open
from src.auction.previous_context import load_previous_context
from src.auction.realtime_open import RealtimeOpenRouter
from src.auction.scoring import score_stock
from src.auction.storage import persist_auction_run, persist_eod_reconciliation
from src.auction.production import update_run, resume_report, freeze_result, save_post_open, write, read
from src.auction.verification import (
    build_report,
    build_sector_breadth,
    expectation_bucket,
    lifecycle_transitions,
    stock_state_machine,
    validate_tomorrow_checks,
)
from src.auction.watchlist import build_watchlist_from_files
from src.config.environment import load_project_environment
from src.market_packet.trading_calendar import TradingCalendarDay, load_trading_calendar
from src.storage.fact_store import FactStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AuctionPipeline:
    def __init__(
        self,
        *,
        root: Path = PROJECT_ROOT,
        source_factory: Callable[[], Any] = EltdxAuctionSource,
        calendar_loader: Callable[[date], list[TradingCalendarDay]] | None = None,
        eod_open_loader: Callable[[date, list[str]], dict[str, float]] | None = None,
        realtime_open_router: RealtimeOpenRouter | None = None,
        post_open_router: PostOpenQuoteRouter | None = None,
    ):
        self.root = root
        self.source_factory = source_factory
        self.calendar_loader = calendar_loader or (
            lambda target: load_trading_calendar(
                target, cache_root=self.root / "data" / "reference"
            )
        )
        self.eod_open_loader = eod_open_loader or self._load_tushare_opens
        self.realtime_open_router = realtime_open_router or RealtimeOpenRouter()
        self.post_open_router = post_open_router or PostOpenQuoteRouter()
        self.fact_store = FactStore(self.root / "data" / "facts")
        self.database_path = self.root / "data" / "a_share_review.db"

    def run_historical(
        self,
        trade_date: date,
        *,
        min_watchlist_size: int = 100,
        max_watchlist_size: int = 200,
        baseline_days: int = 60,
        max_checkpoint_lag_seconds: int = 65,
    ) -> dict[str, Any]:
        if resume_report(self.root, trade_date):
            raise ValueError('historical replay cannot overwrite a frozen live report')
        calendar = self.calendar_loader(trade_date)
        if not any(item.cal_date == trade_date and item.is_open for item in calendar):
            raise ValueError(f"{trade_date.isoformat()} is not an A-share trading day")
        previous_context = load_previous_context(self.root, trade_date, calendar)
        watchlist = build_watchlist_from_files(
            trade_date,
            root=self.root,
            calendar_days=calendar,
            min_size=min_watchlist_size,
            max_size=max_watchlist_size,
        )
        watchlist["sources"]["review_context"] = previous_context["source_paths"]["review_context"]
        stocks = watchlist["stocks"]
        baseline_dates = sorted(
            item.cal_date for item in calendar if item.is_open and item.cal_date < trade_date
        )[-max(0, baseline_days) :]
        baseline_result = self._backfill_formal_baselines(stocks, baseline_dates)

        collection: AuctionCollection = self.source_factory().collect_historical(stocks, trade_date)
        official_opens = self._load_archived_tushare_opens(trade_date)
        validation_source = (
            "tushare_daily_archived_market_packet"
            if official_opens
            else "tushare_daily_unavailable"
        )
        return self._complete_collection(
            trade_date,
            watchlist,
            collection,
            baseline_result,
            official_opens=official_opens,
            validation_source=validation_source,
            live_session=False,
            fallbacks=[],
            max_checkpoint_lag_seconds=max_checkpoint_lag_seconds,
            previous_context=previous_context,
        )

    def run_live(
        self,
        trade_date: date,
        *,
        min_watchlist_size: int = 100,
        max_watchlist_size: int = 200,
        baseline_days: int = 60,
        max_checkpoint_lag_seconds: int = 65,
        now=None,
        sleeper=None,
        force=False,
    ) -> dict[str, Any]:
        now = now or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")))
        if now().date() != trade_date:
            raise ValueError("live requires today's Shanghai date")
        reused = resume_report(self.root, trade_date)
        if reused:
            if force:
                raise ValueError("immutable frozen report cannot be forced")
            return reused
        calendar = self.calendar_loader(trade_date)
        if not any(item.cal_date == trade_date and item.is_open for item in calendar):
            update_run(self.root, trade_date, "NOT_STARTED", status="SKIPPED_NON_TRADING_DAY")
            return {"status": "SKIPPED_NON_TRADING_DAY"}
        update_run(self.root, trade_date, "NOT_STARTED", started_at=now().isoformat())
        previous_context = load_previous_context(self.root, trade_date, calendar)
        watchlist = build_watchlist_from_files(
            trade_date,
            root=self.root,
            calendar_days=calendar,
            min_size=min_watchlist_size,
            max_size=max_watchlist_size,
        )
        watchlist["sources"]["review_context"] = previous_context["source_paths"]["review_context"]
        stocks = watchlist["stocks"]
        baseline_result = {"status": "CACHED_ONLY", "reason": "live never blocks on historical network backfill", "requested_days": baseline_days}
        runner_kwargs = {}
        if now is not None:
            runner_kwargs["now"] = now
        if sleeper is not None:
            runner_kwargs["sleeper"] = sleeper
        runner_kwargs["progress"] = lambda stage, details: update_run(self.root, trade_date, stage, **details)
        raw_path = self.root / 'data/auction_raw_frozen' / f'{trade_date}.json'
        frozen = read(raw_path)
        if frozen:
            import hashlib
            expected = read(self.root / 'data/auction_runs' / f'{trade_date}.json', {}).get('raw_sha256')
            if expected and hashlib.sha256(raw_path.read_bytes()).hexdigest() != expected:
                raise ValueError('immutable raw freeze hash mismatch')
            collection = AuctionCollection(**frozen['collection'])
            watchlist = frozen['watchlist']
            previous_context = frozen['previous_context']
        else:
            collection = LiveAuctionRunner(self.source_factory(), **runner_kwargs).collect(trade_date, stocks)
            write(raw_path, dict(collection=dict(process_rows=collection.process_rows, formal_rows=collection.formal_rows, failures=collection.failures, stats=collection.stats), watchlist=watchlist, previous_context=previous_context))
        import hashlib
        update_run(self.root, trade_date, "AUCTION_FROZEN", raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(), freeze_completed_at=now().isoformat())
        result = self._complete_collection(
            trade_date,
            watchlist,
            collection,
            baseline_result,
            official_opens={},
            validation_source="POST_OPEN_PENDING",
            live_session=True,
            fallbacks=[],
            max_checkpoint_lag_seconds=max_checkpoint_lag_seconds,
            previous_context=previous_context,
        )
        return freeze_result(self.root, trade_date, result, collection.stats, now)

    def reconcile_eod(self, trade_date: date) -> dict[str, Any]:
        packet_path = self.root / "data" / "auction_packets" / f"{trade_date.isoformat()}.json"
        packet = _read_json(packet_path, None)
        if not packet:
            raise FileNotFoundError(f"Auction Packet not found: {packet_path}")
        current = datetime.now(ZoneInfo("Asia/Shanghai"))
        if "auction_report_0925" in packet and (trade_date > current.date() or (trade_date == current.date() and current.time() < time(15,15))):
            raise ValueError("EOD reconciliation requires a closed session after 15:15")
        summaries = packet.get("stock_auction_summary") or []
        codes = [str(item.get("ts_code")) for item in summaries if item.get("ts_code")]
        official_opens = self.eod_open_loader(trade_date, codes)
        for item in summaries:
            item["realtime_open_price"] = item.get("official_open_price")
            item["realtime_open_validation_source"] = item.get("open_price_validation_source")
            item["realtime_open_price_error_pct"] = item.get("open_price_error_pct")
            item["realtime_conflict_status"] = item.get("conflict_status")
        conflicts = apply_open_validation(summaries, official_opens, source="tushare_daily")
        for item in summaries:
            item["eod_open_price"] = item.get("official_open_price")
            item["eod_open_price_error_pct"] = item.get("open_price_error_pct")
            item["eod_conflict_status"] = item.get("conflict_status")
        non_open_conflicts = [
            item
            for item in packet.get("conflicts") or []
            if item.get("type") != "open_price_conflict"
        ]
        packet["conflicts"] = non_open_conflicts + conflicts
        validation_count = sum(
            item.get("eod_open_price_error_pct") is not None for item in summaries
        )
        eod_status = "PASS" if validation_count == len(summaries) and not conflicts else "PARTIAL"
        packet["data_quality"]["eod_reconciliation"] = {
            "status": eod_status,
            "source": "tushare_daily",
            "validation_count": validation_count,
            "stock_count": len(summaries),
            "conflict_count": len(conflicts),
        }
        persist_eod_reconciliation(
            trade_date=trade_date,
            summaries=summaries,
            validation_count=validation_count,
            conflicts=conflicts,
            fact_store=self.fact_store,
            database_path=self.database_path,
            packet_path=packet_path,
        )
        if "auction_report_0925" in packet:
            eod_path = self.root / "data/auction_eod" / f"{trade_date}.json"
            write(eod_path, dict(trade_date=str(trade_date), status=eod_status, summaries=summaries, conflicts=conflicts))
            update_run(self.root, trade_date, "EOD_RECONCILED", status=eod_status, eod_completed_at=current.isoformat() if eod_status == "PASS" else None)
            return dict(packet=packet, path=str(eod_path), compact_path=str(packet_path.with_name(f"{trade_date}_compact.json")), status=eod_status)
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        compact = build_compact_packet(packet)
        compact_path = packet_path.with_name(f"{trade_date.isoformat()}_compact.json")
        compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
        compact_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "auction_packet_compact.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(compact_schema).validate(compact)
        return {
            "packet": packet,
            "compact_packet": compact,
            "path": str(packet_path),
            "compact_path": str(compact_path),
            "status": eod_status,
        }

    def run_post_open(self, trade_date: date, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        if now.date() != trade_date or not time(9,30) <= now.time() < time(10,1):
            raise ValueError("post-open requires today's 09:30-10:00 Shanghai window")
        calendar = self.calendar_loader(trade_date)
        if not any(item.cal_date == trade_date and item.is_open for item in calendar):
            raise ValueError(f"{trade_date.isoformat()} is not an A-share trading day")
        packet_path = self.root / "data" / "auction_packets" / f"{trade_date.isoformat()}.json"
        packet = _read_json(packet_path, None)
        if not packet:
            raise FileNotFoundError(f"Auction Packet not found: {packet_path}")
        summaries = packet.get("stock_auction_summary") or []
        codes = [str(row["ts_code"]) for row in summaries if row.get("ts_code")]
        update_run(self.root, trade_date, "POST_OPEN_VALIDATING", post_open_started_at=now.isoformat())
        source, quotes, fallbacks = self.post_open_router.load(trade_date, codes, now=now)
        results = evaluate_post_open(summaries, quotes, source)
        partition = self.fact_store.write_dataset("auction_post_open_validation", trade_date, results)
        if partition is not None:
            self.fact_store._catalog([partition], self.database_path)
        counts = {
            status: sum(row.get("status") == status for row in results)
            for status in ("confirmed", "partially_confirmed", "weakened", "unverified")
        }
        packet["post_open_validation"] = {
            "status": "AVAILABLE" if quotes else "UNAVAILABLE",
            "source": source,
            "observed_at": max(
                (str(row.get("observed_at")) for row in quotes if row.get("observed_at")),
                default=None,
            ),
            "coverage": len(quotes) / len(codes) if codes else 0.0,
            "status_counts": counts,
            "fallbacks": fallbacks,
            "stocks": results,
        }
        validation = packet["post_open_validation"]
        validation["tomorrow_checks"] = validate_tomorrow_checks(load_previous_context(self.root, trade_date, calendar), [dict(row, **next((v for v in results if v.get("ts_code") == row.get("ts_code")), {})) for row in summaries], packet.get("sector_breadth", []), time_window="post_open")
        saved = save_post_open(self.root, trade_date, validation, now)
        return {"packet": packet, "path": str(self.root / "data/auction_post_open" / f"{trade_date}.json"), "compact_path": str(packet_path.with_name(f"{trade_date}_compact.json")), "post_open": saved}


    def _complete_collection(
        self,
        trade_date: date,
        watchlist: dict[str, Any],
        collection: AuctionCollection,
        baseline_result: dict[str, Any],
        *,
        official_opens: dict[str, float],
        validation_source: str,
        live_session: bool,
        fallbacks: list[dict[str, Any]],
        max_checkpoint_lag_seconds: int,
        previous_context: dict[str, Any],
    ) -> dict[str, Any]:
        stocks = watchlist["stocks"]
        if live_session:
            cutoff = datetime.combine(trade_date, time(9,25), ZoneInfo('Asia/Shanghai'))
            for row in collection.process_rows + collection.formal_rows:
                observed = datetime.fromisoformat(row['snapshot_time'])
                if observed.tzinfo is None or observed.date() != trade_date or observed > cutoff:
                    raise ValueError('09:25 report rejects future or cross-date observations')
        process_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in collection.process_rows:
            process_by_code.setdefault(str(row["ts_code"]), []).append(row)
        formal_by_code = {str(row["ts_code"]): row for row in collection.formal_rows}
        checkpoints: list[dict[str, Any]] = []
        for stock in stocks:
            code = str(stock["ts_code"])
            checkpoints.extend(
                map_checkpoints(
                    trade_date,
                    process_by_code.get(code, []),
                    formal_by_code.get(code),
                    max_lag_seconds=max_checkpoint_lag_seconds,
                    identity={
                        "ts_code": code,
                        "stock_name": stock.get("stock_name"),
                        "source": "eltdx",
                    },
                )
            )

        previous_packet = previous_context.get("market_packet") or {}
        previous_review = previous_context.get("official_review") or {}
        previous_by_code = {
            _with_suffix(str(item.get("stock_code") or item.get("code") or "")): item
            for item in previous_packet.get("stocks") or []
        }
        for row in collection.process_rows + checkpoints:
            previous = previous_by_code.get(str(row.get("ts_code")), {})
            previous_close = _float_or_none(previous.get("close"))
            row["prev_close"] = previous_close
            row["indicative_price"] = row.get("match_price")
            row["indicative_pct"] = (
                (float(row["match_price"]) / previous_close - 1) * 100
                if row.get("match_price") is not None and previous_close
                else None
            )
        historical = self._historical_records(trade_date)
        checkpoint_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in checkpoints:
            checkpoint_by_code.setdefault(str(row.get("ts_code")), []).append(row)
        summaries = []
        for stock in stocks:
            code = str(stock["ts_code"])
            previous = previous_by_code.get(code, {})
            summaries.append(
                build_daily_summary(
                    checkpoint_by_code.get(code, []),
                    previous_close=_float_or_none(previous.get("close")),
                    previous_day_amount=_float_or_none(previous.get("amount")),
                    previous_day_volume=_float_or_none(
                        previous.get("volume") or previous.get("vol")
                    ),
                    historical_auction_amounts=[
                        row["auction_amount"]
                        for row in historical.get(code, [])
                        if row.get("auction_amount") is not None
                    ],
                    historical_auction_records=historical.get(code, []),
                    process_rows=process_by_code.get(code, []),
                )
            )

        conflicts = apply_open_validation(summaries, official_opens, source=validation_source)
        refreshed = self._refreshed_evidence(trade_date)
        sectors = build_sector_breadth(watchlist, summaries, previous_context)
        sector_map = {row["name"]: row for row in sectors}
        from src.auction.score_rules import market_sample
        previous_context["auction_market"] = market_sample(summaries, previous_context, stocks)
        initial_checks = validate_tomorrow_checks(previous_context, summaries, sectors)
        for sector in sectors:
            checks_for_sector = [c for c in initial_checks if c['entity_type']=='theme' and c['entity_key']==sector['name'] and c['validation_status'] != 'unverified']
            sector['tomorrow_check_ratio'] = sum(c['validation_status']=='confirmed' for c in checks_for_sector)/len(checks_for_sector) if checks_for_sector else None
        watch_by_code = {str(row.get("ts_code")): row for row in stocks}
        scored = []
        for summary in summaries:
            watch_stock = watch_by_code.get(str(summary.get("ts_code")), {})
            theme = (watch_stock.get("themes") or [None])[0]
            score = score_stock(
                summary, watch_stock, previous_context, sector_map.get(theme), refreshed["records"]
            )
            summary["composite_score"] = score
            scored.append(
                {
                    "ts_code": summary.get("ts_code"),
                    "stock_name": summary.get("stock_name"),
                    "themes": watch_stock.get("themes") or [],
                    "roles": watch_stock.get("roles") or [],
                    "auction_gap_pct": summary.get("auction_gap_pct"),
                    "auction_amount": summary.get("auction_amount"),
                    "auction_amount_percentile_20d": summary.get("auction_amount_percentile_20d"),
                    "price_change_0920_0925_pct": summary.get("price_change_0920_0925_pct"),
                    "score": score,
                    "expectation_bucket": expectation_bucket(score),
                }
            )
        scored.sort(
            key=lambda row: (
                -row["score"]["final_score"],
                -row["score"]["available_max_score"],
                str(row.get("ts_code")),
            )
        )
        for rank, row in enumerate(scored, 1):
            row["rank"] = rank
        tomorrow_validation = validate_tomorrow_checks(previous_context, summaries, sectors)
        lifecycle = lifecycle_transitions(previous_context, sectors)
        stock_transitions = stock_state_machine(previous_context, summaries, sectors)
        snapshots = collection.process_rows + checkpoints
        metrics = _coverage_metrics(stocks, checkpoints, collection)
        checks = _quality_checks(
            watchlist,
            summaries,
            metrics,
            conflicts,
            live_session=live_session,
            previous_context=previous_context,
            checkpoints=checkpoints,
            catalyst_refresh=refreshed,
        )
        status = "PASS" if all(check["passed"] for check in checks) else "PARTIAL"
        if not snapshots or metrics["stock_completion_rate"] == 0:
            status = "FAIL"
        quality_level = _quality_level(metrics, previous_context)
        if quality_level == "LOW":
            status = "FAIL"
        written = persist_auction_run(
            trade_date=trade_date,
            snapshots=snapshots,
            summaries=summaries,
            source_stats={**collection.stats, **metrics},
            quality_status=status,
            quality_checks=checks,
            conflicts=conflicts,
            failures=collection.failures,
            fact_store=self.fact_store,
            database_path=self.database_path,
            fallbacks=fallbacks,
        )
        readable = bool(self.fact_store.read_dataset("auction_snapshot", trade_date))
        if not readable:
            raise RuntimeError("auction_snapshot Parquet verification failed")

        packet = _build_packet(
            trade_date,
            watchlist,
            summaries,
            collection,
            metrics,
            checks,
            conflicts,
            status=status,
            baseline_result=baseline_result,
            mode="live" if live_session else "historical",
            previous_review=previous_review,
        )
        packet["previous_context"] = {
            key: value
            for key, value in previous_context.items()
            if key not in {"official_review", "review_context", "market_packet"}
        }
        packet["sector_breadth"] = sectors
        packet["auction_market_environment"] = previous_context["auction_market"]
        packet["tomorrow_check_validation"] = tomorrow_validation
        packet["lifecycle_transition_candidates"] = lifecycle
        packet["stock_state_transitions"] = stock_transitions
        packet["scored_stock_ranking"] = scored
        packet["catalyst_refresh"] = refreshed
        packet["scoring_model"] = {
            "gross_max_score": 100,
            "risk_deduction_range": [0, 20],
            "formula": "gross_score - risk_deduction = final_score",
            "missing_components": "N/A and excluded from available_max_score; scores are not rescaled",
        }
        packet["report_status"] = (
            "degraded"
            if previous_context["report_status"] == "degraded" or quality_level == "LOW"
            else "normal"
        )
        packet["data_quality"]["level"] = quality_level
        packet["data_quality"]["coverage"] = {
            "snapshot_coverage": metrics["checkpoint_coverage"],
            "post_920_coverage": metrics["post_0920_checkpoint_coverage"],
            "watchlist_coverage": metrics["stock_completion_rate"],
            "previous_review_loaded": previous_context["official_review_loaded"],
            "catalyst_refresh_time": refreshed["refreshed_at"],
        }
        packet["report"] = build_report(packet)
        packet_dir = self.root / "data" / "auction_packets"
        packet_dir.mkdir(parents=True, exist_ok=True)
        packet_path = packet_dir / f"{trade_date.isoformat()}.json"
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        schema = json.loads(
            (PROJECT_ROOT / "schemas" / "auction_packet.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(packet)
        compact = build_compact_packet(packet)
        compact_path = packet_dir / f"{trade_date.isoformat()}_compact.json"
        compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
        compact_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "auction_packet_compact.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(compact_schema).validate(compact)
        return {
            "packet": packet,
            "compact_packet": compact,
            "partitions": written,
            "paths": {
                "watchlist": watchlist["output_path"],
                "packet": str(packet_path),
                "compact_packet": str(compact_path),
            },
        }

    def _backfill_formal_baselines(
        self, stocks: list[dict[str, Any]], dates: list[date]
    ) -> dict[str, Any]:
        completed = 0
        failed_dates: list[str] = []
        coverage_by_date: dict[str, float] = {}
        stock_count = len(stocks)
        existing_frame = self.fact_store.query_dataset(
            "auction_daily_summary",
            start=min(dates) if dates else None,
            end=max(dates) if dates else None,
        )
        existing_by_date: dict[str, set[str]] = {}
        if not existing_frame.empty:
            for item in existing_frame.to_dict("records"):
                if item.get("auction_amount") is None:
                    continue
                existing_by_date.setdefault(str(item.get("trade_date"))[:10], set()).add(
                    str(item.get("ts_code") or "")
                )
        for baseline_date in dates:
            existing = self.fact_store.read_dataset("auction_daily_summary", baseline_date)
            existing_codes = existing_by_date.get(baseline_date.isoformat(), set())
            missing_stocks = [
                stock for stock in stocks if str(stock["ts_code"]) not in existing_codes
            ]
            if not missing_stocks:
                coverage_by_date[baseline_date.isoformat()] = 1.0
                completed += 1
                continue
            source = self.source_factory()
            if not hasattr(source, "collect_formal_only"):
                coverage = len(existing_codes) / stock_count if stock_count else 0.0
                coverage_by_date[baseline_date.isoformat()] = coverage
                if coverage >= 0.95:
                    completed += 1
                else:
                    failed_dates.append(baseline_date.isoformat())
                continue
            result: AuctionCollection = source.collect_formal_only(missing_stocks, baseline_date)
            baseline_snapshots = []
            baseline_summaries = []
            for row in result.formal_rows:
                checkpoint = dict(row)
                checkpoint["checkpoint_time"] = "09:25:00"
                checkpoint["checkpoint_lag_ms"] = 0
                checkpoint["observation_kind"] = "checkpoint"
                baseline_snapshots.append(checkpoint)
                baseline_summaries.append(
                    build_daily_summary(
                        [checkpoint],
                        previous_close=None,
                        previous_day_amount=None,
                        historical_auction_amounts=[],
                    )
                )
            collected_codes = {str(row.get("ts_code")) for row in result.formal_rows}
            coverage = len(existing_codes | collected_codes) / stock_count if stock_count else 0.0
            coverage_by_date[baseline_date.isoformat()] = coverage
            baseline_status = (
                "PASS" if coverage >= 0.95 else ("PARTIAL" if coverage > 0 else "FAIL")
            )
            if baseline_snapshots:
                persist_auction_run(
                    trade_date=baseline_date,
                    snapshots=baseline_snapshots,
                    summaries=existing + baseline_summaries,
                    source_stats=result.stats,
                    quality_status=baseline_status,
                    quality_checks=[
                        {
                            "name": "formal_opening_match_coverage",
                            "actual": coverage,
                            "threshold": 0.95,
                            "passed": coverage >= 0.95,
                        }
                    ],
                    conflicts=[],
                    failures=result.failures,
                    fact_store=self.fact_store,
                    database_path=self.database_path,
                )
            if coverage >= 0.95:
                completed += 1
            else:
                failed_dates.append(baseline_date.isoformat())
        return {
            "requested_dates": len(dates),
            "completed_dates": completed,
            "failed_dates": failed_dates,
            "minimum_stock_coverage": min(coverage_by_date.values()) if coverage_by_date else None,
        }

    def _historical_records(self, before: date) -> dict[str, list[dict[str, Any]]]:
        frame = self.fact_store.query_dataset("auction_daily_summary", end=before)
        if frame.empty:
            return {}
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for row in frame.to_dict("records"):
            row_date = str(row.get("trade_date"))[:10]
            code = str(row.get("ts_code") or "")
            if row_date >= before.isoformat():
                continue
            result.setdefault(code, {})[row_date] = row
        return {
            code: [row for _, row in sorted(values.items())[-60:]]
            for code, values in result.items()
        }

    def _historical_amounts(self, before: date) -> dict[str, list[float]]:
        return {
            code: [float(row["auction_amount"]) for row in rows if row.get("auction_amount") is not None]
            for code, rows in self._historical_records(before).items()
        }

    def _refreshed_evidence(self, trade_date: date) -> dict[str, Any]:
        packet = _read_json(
            self.root / "data" / "market_packets" / f"{trade_date.isoformat()}.json", {}
        )
        cutoff = f"{trade_date.isoformat()}T09:25:00+08:00"
        records = []
        for section in ("announcements", "policies"):
            for row in (packet.get(section) or {}).get("records") or []:
                published = str(row.get("published_at") or "")
                if not published or published[:10] != trade_date.isoformat():
                    continue
                # Date-only records cannot prove that the evidence existed before 09:25.
                if "T" not in published and " " not in published:
                    continue
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    cutoff_at = datetime.fromisoformat(cutoff)
                except ValueError:
                    continue
                if published_at.tzinfo is None or published_at > cutoff_at:
                    continue
                if str(row.get("evidence_level") or "") not in {"A", "B", "C", "D"}:
                    continue
                records.append(dict(row, as_of=cutoff))
        return {
            "status": "AVAILABLE" if records else "EMPTY_VALID" if packet else "UNAVAILABLE",
            "as_of": cutoff,
            "refreshed_at": (packet.get("meta") or {}).get("generated_at")
            or (packet.get("meta") or {}).get("as_of"),
            "record_count": len(records),
            "records": records,
        }

    @staticmethod
    def _load_tushare_opens(trade_date: date, codes: list[str]) -> dict[str, float]:
        load_project_environment()
        from src.adapters.tushare_market import TushareMarketAdapter

        record = TushareMarketAdapter().stock_daily(trade_date)
        wanted = set(codes)
        return {
            str(row["ts_code"]): float(row["open"])
            for row in record.payload
            if row.get("ts_code") in wanted and row.get("open") is not None
        }

    def _load_archived_tushare_opens(self, trade_date: date) -> dict[str, float]:
        raw_record = _read_json(
            self.root
            / "data"
            / "raw"
            / "market_packets"
            / trade_date.isoformat()
            / "tushare_daily_all.json",
            {},
        )
        if raw_record:
            source_date = str(raw_record.get("data_date") or "")[:10]
            if source_date != trade_date.isoformat():
                raise ValueError(
                    f"archived Tushare daily date mismatch: requested={trade_date.isoformat()} source={source_date}"
                )
            return {
                _with_suffix(str(row.get("ts_code") or "")): float(row["open"])
                for row in raw_record.get("rows") or []
                if row.get("ts_code") and row.get("open") is not None
            }

        packet = _read_json(
            self.root / "data" / "market_packets" / f"{trade_date.isoformat()}.json", {}
        )
        result: dict[str, float] = {}
        for row in packet.get("stocks") or []:
            if "tushare_daily" not in (row.get("sources") or []) or row.get("open") is None:
                continue
            result[_with_suffix(str(row.get("stock_code") or row.get("code") or ""))] = float(
                row["open"]
            )
        return result


def _coverage_metrics(
    stocks: list[dict[str, Any]], checkpoints: list[dict[str, Any]], collection: AuctionCollection
) -> dict[str, Any]:
    denominator = len(stocks) * len(CHECKPOINTS)
    valid = sum(row.get("match_price") is not None for row in checkpoints)
    post_rows = [row for row in checkpoints if str(row.get("checkpoint_time")) >= "09:20:00"]
    post_valid = sum(row.get("match_price") is not None for row in post_rows)
    formal_rate = len(collection.formal_rows) / len(stocks) if stocks else 0.0
    return {
        "checkpoint_coverage": valid / denominator if denominator else 0.0,
        "post_0920_checkpoint_coverage": post_valid / (len(stocks) * 6) if stocks else 0.0,
        "formal_opening_match_success_rate": formal_rate,
        "stock_completion_rate": float(collection.stats.get("stock_completion_rate") or 0),
    }


def _quality_checks(
    watchlist: dict[str, Any],
    summaries: list[dict[str, Any]],
    metrics: dict[str, Any],
    conflicts: list[dict[str, Any]],
    *,
    live_session: bool,
    previous_context: dict[str, Any],
    checkpoints: list[dict[str, Any]],
    catalyst_refresh: dict[str, Any],
) -> list[dict[str, Any]]:
    validated = sum(item.get("open_price_error_pct") is not None for item in summaries)
    validation_rate = validated / len(summaries) if summaries else 0.0
    baseline_20 = sum((item.get("baseline_observation_count_20d") or 0) >= 20 for item in summaries)
    baseline_rate = baseline_20 / len(summaries) if summaries else 0.0
    values = [
        (
            "watchlist_size",
            watchlist["stock_count"],
            watchlist["min_size"],
            watchlist["quality_status"] == "PASS",
        ),
        (
            "stock_completion_rate",
            metrics["stock_completion_rate"],
            0.95,
            metrics["stock_completion_rate"] >= 0.95,
        ),
        (
            "checkpoint_coverage",
            metrics["checkpoint_coverage"],
            0.90,
            metrics["checkpoint_coverage"] >= 0.90,
        ),
        (
            "post_0920_checkpoint_coverage",
            metrics["post_0920_checkpoint_coverage"],
            0.90,
            metrics["post_0920_checkpoint_coverage"] >= 0.90,
        ),
        (
            "formal_opening_match_success_rate",
            metrics["formal_opening_match_success_rate"],
            0.95,
            metrics["formal_opening_match_success_rate"] >= 0.95,
        ),
        ("open_price_validation_rate", validation_rate, 0.95, validation_rate >= 0.95),
        ("baseline_20d_coverage", baseline_rate, 0.90, baseline_rate >= 0.90),
        (
            "previous_review_exact_date",
            previous_context["official_review_loaded"],
            True,
            previous_context["official_review_loaded"],
        ),
        (
            "previous_review_context_exact_date",
            previous_context["review_context_loaded"],
            True,
            previous_context["review_context_loaded"],
        ),
        (
            "evidence_refresh",
            catalyst_refresh["status"],
            "AVAILABLE_OR_EMPTY_VALID",
            catalyst_refresh["status"] in {"AVAILABLE", "EMPTY_VALID"},
        ),
        ("live_session_acceptance", live_session, True, live_session),
        ("open_price_conflicts", len(conflicts), 0, not conflicts),
    ]
    for checkpoint_time in ("09:20:00", "09:21:00", "09:22:00", "09:23:00", "09:24:00", "09:25:00"):
        available = sum(
            row.get("match_price") is not None and row.get("checkpoint_time") == checkpoint_time
            for row in checkpoints
        )
        coverage = available / watchlist["stock_count"] if watchlist["stock_count"] else 0.0
        values.append(
            (
                f"checkpoint_{checkpoint_time[:5].replace(':', '')}_coverage",
                coverage,
                0.90,
                coverage >= 0.90,
            )
        )
    return [
        {
            "name": name,
            "actual": actual,
            "threshold": threshold,
            "passed": passed,
            "reason": "historical runs cannot satisfy live-session acceptance"
            if name == "live_session_acceptance" and not passed
            else "",
        }
        for name, actual, threshold, passed in values
    ]


def _quality_level(metrics, previous_context):
    if (
        metrics["formal_opening_match_success_rate"] < 0.90
        or metrics["post_0920_checkpoint_coverage"] < 0.80
    ):
        return "LOW"
    if (
        metrics["formal_opening_match_success_rate"] >= 0.95
        and metrics["post_0920_checkpoint_coverage"] >= 0.95
        and metrics["checkpoint_coverage"] >= 0.90
        and previous_context["official_review_loaded"]
        and previous_context["review_context_loaded"]
    ):
        return "HIGH"
    return "MEDIUM"


def _build_packet(
    trade_date: date,
    watchlist: dict[str, Any],
    summaries: list[dict[str, Any]],
    collection: AuctionCollection,
    metrics: dict[str, Any],
    checks: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    *,
    status: str,
    baseline_result: dict[str, Any],
    mode: str,
    previous_review: dict[str, Any],
) -> dict[str, Any]:
    valid_gaps = [
        item["auction_gap_pct"] for item in summaries if item.get("auction_gap_pct") is not None
    ]
    market_summary = {
        **collection.stats,
        **metrics,
        "high_open_count": sum(value > 0 for value in valid_gaps),
        "low_open_count": sum(value < 0 for value in valid_gaps),
        "high_open_3pct_count": sum(value >= 3 for value in valid_gaps),
        "baseline_backfill": baseline_result,
    }
    objective_analysis = build_objective_analysis(watchlist, summaries, previous_review)
    anomaly_candidates = sorted(
        (item for item in summaries if item.get("anomaly_labels")),
        key=lambda item: (
            -(item.get("auction_volume_anomaly_score") or 0),
            -(item.get("auction_amount_ratio_20d") or 0),
            str(item.get("ts_code") or ""),
        ),
    )
    return {
        "meta": {
            "schema_version": "auction_packet.1",
            "trade_date": trade_date.isoformat(),
            "mode": mode,
            "process_primary": "eltdx",
            "process_fallback": "klineshare_v2_disabled",
            "final_judgement_owner": "chatgpt",
        },
        "watchlist": {
            key: value for key, value in watchlist.items() if key not in {"stocks", "output_path"}
        }
        | {"stocks": watchlist["stocks"]},
        "market_auction_summary": market_summary,
        "stock_auction_summary": summaries,
        "volume_anomaly_candidates": anomaly_candidates,
        "objective_analysis": objective_analysis,
        "data_quality": {"status": status, "checks": checks, "source_stats": collection.stats},
        "conflicts": conflicts,
    }


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_source_path(root: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else root / path


def _with_suffix(code: str) -> str:
    if "." in code:
        return code.replace(".SS", ".SH")
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("8", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None
