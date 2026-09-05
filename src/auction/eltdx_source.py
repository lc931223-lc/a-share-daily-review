from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as dt_time
from typing import Any, Callable
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class AuctionCollection:
    process_rows: list[dict[str, Any]]
    formal_rows: list[dict[str, Any]]
    failures: list[dict[str, str]]
    stats: dict[str, Any]


class EltdxAuctionSource:
    def __init__(self, client_factory: Callable[[], Any] | None = None, *, max_reconnects: int = 1):
        self.client_factory = client_factory or self._default_client
        self.max_reconnects = max_reconnects
        self.client = None
        self.request_count = 0
        self.reconnect_count = 0
        self.latencies_ms: list[float] = []

    @staticmethod
    def _default_client():
        try:
            from eltdx import Client
        except ImportError as exc:  # pragma: no cover - dependency contract
            raise RuntimeError("eltdx is required for auction collection") from exc
        return Client(timeout=3.0, probe_timeout=0.6, server_count=3)

    def collect_historical(self, stocks: list[dict[str, Any]], trade_date: date) -> AuctionCollection:
        self._connect()
        process_rows: list[dict[str, Any]] = []
        formal_rows: list[dict[str, Any]] = []
        failures_by_code: dict[str, dict[str, str]] = {}
        try:
            for stock in stocks:
                ts_code = str(stock["ts_code"])
                name = str(stock.get("stock_name") or "")
                try:
                    series = self._request(lambda: self.client.auctions.series(ts_code[:6], trade_date.isoformat()))
                    normalized = self._normalize_process(series, trade_date, ts_code, name)
                    if not normalized:
                        raise RuntimeError("auction process unavailable")
                    process_rows.extend(normalized)
                except Exception as exc:
                    failures_by_code[ts_code] = {"ts_code": ts_code, "error_type": type(exc).__name__, "error": str(exc)[:200]}
            codes = [str(stock["ts_code"]) for stock in stocks]
            names = {str(stock["ts_code"]): str(stock.get("stock_name") or "") for stock in stocks}
            try:
                openings = self._request(lambda: self.client.trades.opening_match_history(
                    [code[:6] for code in codes], trade_date.isoformat(), batch_size=25, max_pages=4,
                ))
                by_digits = {str(key)[-6:]: value for key, value in (openings or {}).items()}
                for ts_code in codes:
                    opening = by_digits.get(ts_code[:6])
                    if opening is None:
                        failures_by_code[ts_code] = {"ts_code": ts_code, "error_type": "Unavailable", "error": "formal opening match unavailable"}
                        continue
                    formal_rows.append(self._normalize_formal(opening, trade_date, ts_code, names[ts_code]))
            except Exception:
                for ts_code in codes:
                    try:
                        opening = self._request(lambda code=ts_code: self.client.trades.opening_match_history(
                            code[:6], trade_date.isoformat(), max_pages=4,
                        ))
                        if opening is None:
                            raise RuntimeError("formal opening match unavailable")
                        formal_rows.append(self._normalize_formal(opening, trade_date, ts_code, names[ts_code]))
                    except Exception as exc:
                        failures_by_code[ts_code] = {"ts_code": ts_code, "error_type": type(exc).__name__, "error": str(exc)[:200]}
        finally:
            self.close()
        process_codes = {str(row["ts_code"]) for row in process_rows}
        formal_codes = {str(row["ts_code"]) for row in formal_rows}
        success_codes = process_codes & formal_codes
        failures = [item for code, item in failures_by_code.items() if code not in success_codes]
        success_count = len(success_codes)
        return AuctionCollection(
            process_rows=process_rows,
            formal_rows=formal_rows,
            failures=failures,
            stats={
                "request_count": self.request_count,
                "success_count": success_count,
                "failure_count": len(failures),
                "reconnect_count": self.reconnect_count,
                "median_latency_ms": round(statistics.median(self.latencies_ms), 3) if self.latencies_ms else None,
                "p95_latency_ms": round(_percentile(self.latencies_ms, 0.95), 3) if self.latencies_ms else None,
                "stock_completion_rate": success_count / len(stocks) if stocks else 0.0,
            },
        )

    def collect_formal_only(self, stocks: list[dict[str, Any]], trade_date: date, *, batch_size: int = 25) -> AuctionCollection:
        self._connect()
        formal_rows: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        try:
            codes = [str(stock["ts_code"]) for stock in stocks]
            names = {str(stock["ts_code"]): str(stock.get("stock_name") or "") for stock in stocks}
            result = self._request(lambda: self.client.trades.opening_match_history(
                [code[:6] for code in codes], trade_date.isoformat(), batch_size=batch_size, max_pages=4,
            ))
            by_digits = {str(key)[-6:]: value for key, value in (result or {}).items()}
            for ts_code in codes:
                opening = by_digits.get(ts_code[:6])
                if opening is None:
                    failures.append({"ts_code": ts_code, "error_type": "Unavailable", "error": "formal opening match unavailable"})
                    continue
                formal_rows.append(self._normalize_formal(opening, trade_date, ts_code, names[ts_code]))
        except Exception:
            formal_rows.clear()
            failures.clear()
            for stock in stocks:
                ts_code = str(stock["ts_code"])
                try:
                    opening = self._request(lambda code=ts_code: self.client.trades.opening_match_history(
                        code[:6], trade_date.isoformat(), max_pages=4,
                    ))
                    if opening is None:
                        raise RuntimeError("formal opening match unavailable")
                    formal_rows.append(self._normalize_formal(opening, trade_date, ts_code, str(stock.get("stock_name") or "")))
                except Exception as exc:
                    failures.append({"ts_code": ts_code, "error_type": type(exc).__name__, "error": str(exc)[:200]})
        finally:
            self.close()
        success_count = len(stocks) - len(failures)
        return AuctionCollection(
            process_rows=[], formal_rows=formal_rows, failures=failures,
            stats={
                "request_count": self.request_count, "success_count": success_count,
                "failure_count": len(failures), "reconnect_count": self.reconnect_count,
                "median_latency_ms": round(statistics.median(self.latencies_ms), 3) if self.latencies_ms else None,
                "p95_latency_ms": round(_percentile(self.latencies_ms, 0.95), 3) if self.latencies_ms else None,
                "stock_completion_rate": success_count / len(stocks) if stocks else 0.0,
            },
        )

    def connect(self) -> None:
        self._connect()

    def collect_live_process(self, stocks: list[dict[str, Any]], trade_date: date) -> AuctionCollection:
        self._connect()
        rows: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        completed = 0
        for stock in stocks:
            ts_code = str(stock["ts_code"])
            try:
                series = self._request(lambda code=ts_code: self.client.auctions.series(code[:6]))
                normalized = self._normalize_process(series, trade_date, ts_code, str(stock.get("stock_name") or ""))
                if not normalized:
                    raise RuntimeError("auction process unavailable")
                rows.extend(normalized)
                completed += 1
            except Exception as exc:
                failures.append({"ts_code": ts_code, "error_type": type(exc).__name__, "error": str(exc)[:200]})
        return AuctionCollection(rows, [], failures, self._stats(completed, len(stocks)))

    def collect_live_formal(self, stocks: list[dict[str, Any]], trade_date: date, *, batch_size: int = 25) -> AuctionCollection:
        self._connect()
        failures: list[dict[str, str]] = []
        rows: list[dict[str, Any]] = []
        codes = [str(stock["ts_code"]) for stock in stocks]
        names = {str(stock["ts_code"]): str(stock.get("stock_name") or "") for stock in stocks}
        try:
            result = self._request(lambda: self.client.trades.opening_match_today(
                [code[:6] for code in codes], batch_size=batch_size, max_pages=4,
            ))
            by_digits = {str(key)[-6:]: value for key, value in (result or {}).items()}
            for code in codes:
                opening = by_digits.get(code[:6])
                if opening is None:
                    failures.append({"ts_code": code, "error_type": "Unavailable", "error": "formal opening match unavailable"})
                    continue
                rows.append(self._normalize_formal(opening, trade_date, code, names[code]))
        except Exception as exc:
            failures = [
                {"ts_code": code, "error_type": type(exc).__name__, "error": str(exc)[:200]}
                for code in codes
            ]
        return AuctionCollection([], rows, failures, self._stats(len(rows), len(stocks)))

    def _stats(self, completed: int, total: int) -> dict[str, Any]:
        return {
            "request_count": self.request_count, "success_count": completed,
            "failure_count": total - completed, "reconnect_count": self.reconnect_count,
            "median_latency_ms": round(statistics.median(self.latencies_ms), 3) if self.latencies_ms else None,
            "p95_latency_ms": round(_percentile(self.latencies_ms, 0.95), 3) if self.latencies_ms else None,
            "stock_completion_rate": completed / total if total else 0.0,
        }

    def _request(self, operation: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_reconnects + 1):
            started = time.perf_counter()
            self.request_count += 1
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt < self.max_reconnects:
                    self._reconnect()
            finally:
                self.latencies_ms.append((time.perf_counter() - started) * 1000)
        assert last_error is not None
        raise last_error

    def _connect(self) -> None:
        if self.client is None:
            self.client = self.client_factory()
            self.client.connect()

    def _reconnect(self) -> None:
        self.close()
        self.reconnect_count += 1
        self._connect()

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def _normalize_process(self, series: Any, trade_date: date, ts_code: str, name: str) -> list[dict[str, Any]]:
        rows = []
        retrieved_at = datetime.now(UTC).isoformat()
        for point in series.points:
            if not 33_300 <= int(point.time_seconds) <= 33_900:
                continue
            source_dt = datetime.combine(trade_date, dt_time.fromisoformat(point.time_label), SHANGHAI_TZ)
            raw_volume = int(point.matched_volume)
            price = float(point.price)
            signed_raw = getattr(point, "unmatched_signed_raw", None)
            signed_shares = int(signed_raw) * 100 if signed_raw is not None else None
            row = _snapshot_base(trade_date, ts_code, name, retrieved_at, source_dt.isoformat())
            row.update({
                "match_price": price,
                "matched_volume": raw_volume * 100,
                "matched_amount": price * raw_volume * 100,
                "unmatched_signed_volume": signed_shares,
                "unmatched_direction_raw": getattr(point, "unmatched_direction_raw", None),
                "raw_matched_volume": raw_volume,
                "raw_volume_unit": "lot",
                "matched_amount_value_kind": "DERIVED",
                "quality_status": "PASS",
                "observation_kind": "raw_process",
            })
            row["content_hash"] = _hash_row(row)
            rows.append(row)
        return rows

    def _normalize_formal(self, opening: Any, trade_date: date, ts_code: str, name: str) -> dict[str, Any]:
        retrieved_at = datetime.now(UTC).isoformat()
        source_dt = datetime.combine(trade_date, dt_time(9, 25), SHANGHAI_TZ)
        raw_volume = int(opening.volume)
        price = float(opening.price)
        amount = getattr(opening, "trade_amount_yuan", None)
        row = _snapshot_base(trade_date, ts_code, name, retrieved_at, source_dt.isoformat())
        row.update({
            "match_price": price,
            "matched_volume": raw_volume * 100,
            "matched_amount": float(amount) if amount is not None else price * raw_volume * 100,
            "raw_matched_volume": raw_volume,
            "raw_volume_unit": "lot",
            "matched_amount_value_kind": "DERIVED",
            "is_formal_opening_match": True,
            "quality_status": "PASS",
            "observation_kind": "formal_opening_match",
        })
        row["content_hash"] = _hash_row(row)
        return row


def _snapshot_base(trade_date: date, ts_code: str, name: str, retrieved_at: str, source_time: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date.isoformat(), "ts_code": ts_code, "stock_name": name,
        "snapshot_time": source_time, "checkpoint_time": None, "match_price": None,
        "matched_volume": None, "matched_amount": None, "unmatched_signed_volume": None,
        "unmatched_direction_raw": None, "unmatched_buy": None, "unmatched_sell": None,
        "raw_matched_volume": None, "raw_volume_unit": None, "matched_amount_value_kind": None,
        "source": "eltdx", "source_batch_id": None, "retrieved_at": retrieved_at,
        "source_data_time": source_time, "checkpoint_lag_ms": None,
        "is_formal_opening_match": False, "quality_status": "FAIL", "content_hash": "",
        "schema_version": "auction_snapshot.1", "observation_kind": "raw_process",
    }


def _hash_row(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key not in {"content_hash", "source_batch_id", "retrieved_at"}}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = int(percentile * (len(ordered) - 1))
    return ordered[index]
