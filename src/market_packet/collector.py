from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover - reported through source metadata
    ak = None

try:
    import tushare as ts
except Exception:  # pragma: no cover - reported through source metadata
    ts = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_SYMBOLS = {
    "sh000001": ("上证指数", "000001.SH"),
    "sz399001": ("深证成指", "399001.SZ"),
    "sz399006": ("创业板指", "399006.SZ"),
    "sh000688": ("科创50", "000688.SH"),
    "bj899050": ("北证50", "899050.BJ"),
}
ANNOUNCEMENT_CATEGORIES = {
    "业绩": "earnings",
    "预告": "earnings",
    "订单": "order",
    "中标": "order",
    "合同": "contract",
    "客户": "customer",
    "产品": "product",
    "产能": "capacity",
    "投产": "capacity",
    "重组": "restructuring",
    "收购": "restructuring",
    "回购": "buyback",
    "增持": "increase_holding",
    "减持": "decrease_holding",
    "澄清": "clarification",
    "风险": "risk_warning",
    "监管": "regulatory",
    "问询": "regulatory",
    "异常波动": "clarification",
}
CLARIFICATION_KEYWORDS = ("尚未形成订单", "未形成订单", "尚未形成收入", "业务占比低", "仍在研发", "尚未认证", "异常波动", "澄清")
RISK_KEYWORDS = ("风险提示", "风险", "异常波动", "减持", "监管", "问询", "处罚")


@dataclass(frozen=True)
class CollectedDataset:
    name: str
    source: str
    data_date: date | None
    retrieved_at: datetime
    rows: list[dict[str, Any]]
    quality: str
    freshness: str
    is_cached: bool
    path: str | None = None
    error: str | None = None


class MarketPacketCollector:
    def __init__(self, *, raw_root: Path | None = None, refresh: bool = False):
        self.raw_root = raw_root or PROJECT_ROOT / "data" / "raw" / "market_packets"
        self.refresh = refresh

    def collect(self, trade_date: date) -> dict[str, CollectedDataset]:
        datasets: dict[str, CollectedDataset] = {}
        calls: list[tuple[str, str, Callable[[], pd.DataFrame], date | None, str]] = [
            ("limit_up", "akshare.stock_zt_pool_em", lambda: ak.stock_zt_pool_em(date=_compact(trade_date)), trade_date, "historical"),
            ("failed_limit", "akshare.stock_zt_pool_zbgc_em", lambda: ak.stock_zt_pool_zbgc_em(date=_compact(trade_date)), trade_date, "historical"),
            ("limit_down", "akshare.stock_zt_pool_dtgc_em", lambda: ak.stock_zt_pool_dtgc_em(date=_compact(trade_date)), trade_date, "historical"),
            ("previous_limit", "akshare.stock_zt_pool_previous_em", lambda: ak.stock_zt_pool_previous_em(date=_compact(trade_date)), trade_date, "historical"),
            ("dragon_tiger_daily", "akshare.stock_lhb_detail_em", lambda: ak.stock_lhb_detail_em(start_date=_compact(trade_date), end_date=_compact(trade_date)), trade_date, "historical"),
            ("northbound_hist", "akshare.stock_hsgt_hist_em", lambda: ak.stock_hsgt_hist_em(symbol="北向资金"), None, "historical"),
            ("hsgt_summary", "akshare.stock_hsgt_fund_flow_summary_em", lambda: ak.stock_hsgt_fund_flow_summary_em(), None, "current_only"),
            ("szse_margin", "akshare.stock_margin_szse", lambda: ak.stock_margin_szse(date=_compact(trade_date)), trade_date, "historical"),
            ("szse_margin_detail", "akshare.stock_margin_detail_szse", lambda: ak.stock_margin_detail_szse(date=_compact(trade_date)), trade_date, "historical"),
            ("industry_fund_flow_current", "akshare.stock_fund_flow_industry", lambda: ak.stock_fund_flow_industry(symbol="即时"), None, "current_only"),
            ("concept_fund_flow_current", "akshare.stock_fund_flow_concept", lambda: ak.stock_fund_flow_concept(symbol="即时"), None, "current_only"),
        ]
        for name, source, fn, data_date, freshness in calls:
            datasets[name] = self._collect_frame(name, source, fn, trade_date, data_date, freshness)
        self._collect_tushare_core(datasets, trade_date)
        datasets["stock_top_ohlcv"] = self._collect_stock_top_ohlcv(trade_date, datasets)
        datasets["official_announcements"] = self._collect_announcements(trade_date, datasets)
        datasets["official_policies"] = self._collect_policies(trade_date)
        datasets["industry_board_daily"] = self._collect_board_daily(trade_date, "industry")
        datasets["concept_board_daily"] = self._collect_board_daily(trade_date, "concept")
        for symbol, (label, ts_code) in INDEX_SYMBOLS.items():
            datasets[f"index_{ts_code}"] = self._collect_frame(
                f"index_{ts_code}",
                "akshare.stock_zh_index_daily",
                lambda symbol=symbol: ak.stock_zh_index_daily(symbol=symbol),
                trade_date,
                trade_date,
                "historical",
            )
        return datasets

    def _collect_tushare_core(self, datasets: dict[str, CollectedDataset], trade_date: date) -> None:
        token = os.environ.get("TUSHARE_TOKEN")
        if ts is None or not token:
            for name in ("tushare_trade_cal", "tushare_stock_basic", "tushare_daily_all", "tushare_previous_daily_all", "tushare_daily_basic_all", "tushare_adj_factor_all"):
                datasets[name] = CollectedDataset(
                    name,
                    "tushare.pro",
                    trade_date,
                    datetime.now(UTC),
                    [],
                    "FAIL",
                    "missing",
                    False,
                    error="TUSHARE_TOKEN missing or tushare import failed",
                )
            return

        pro = ts.pro_api(token)
        cal_start = trade_date - timedelta(days=14)
        datasets["tushare_trade_cal"] = self._collect_tushare_trade_cal(pro, trade_date)
        previous_trade_date = _previous_trade_date(datasets["tushare_trade_cal"].rows, trade_date)
        datasets["tushare_stock_basic"] = self._collect_tushare_stock_basic(pro, trade_date)
        datasets["tushare_daily_all"] = self._collect_frame(
            "tushare_daily_all",
            "tushare.daily",
            lambda: pro.daily(trade_date=_compact(trade_date)),
            trade_date,
            trade_date,
            "historical",
        )
        datasets["tushare_previous_daily_all"] = self._collect_tushare_previous_daily(pro, trade_date, previous_trade_date)
        datasets["tushare_daily_basic_all"] = self._collect_frame(
            "tushare_daily_basic_all",
            "tushare.daily_basic",
            lambda: pro.daily_basic(trade_date=_compact(trade_date), fields="ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv"),
            trade_date,
            trade_date,
            "historical",
        )
        datasets["tushare_adj_factor_all"] = self._collect_frame(
            "tushare_adj_factor_all",
            "tushare.adj_factor",
            lambda: pro.adj_factor(trade_date=_compact(trade_date)),
            trade_date,
            trade_date,
            "historical",
        )

    def _collect_tushare_trade_cal(self, pro, trade_date: date) -> CollectedDataset:
        name = "tushare_trade_cal"
        ref_path = PROJECT_ROOT / "data" / "reference" / f"{name}_{trade_date.year}.json"
        if ref_path.exists() and not self.refresh:
            payload = json.loads(ref_path.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            return CollectedDataset(name, "tushare.trade_cal", trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", True, str(ref_path), payload.get("error"))
        start = date(trade_date.year, 1, 1)
        end = date(trade_date.year, 12, 31)
        return self._collect_reference_frame(
            name,
            "tushare.trade_cal",
            lambda: pro.trade_cal(exchange="", start_date=_compact(start), end_date=_compact(end)),
            trade_date,
            ref_path,
        )

    def _collect_tushare_stock_basic(self, pro, trade_date: date) -> CollectedDataset:
        name = "tushare_stock_basic"
        ref_path = PROJECT_ROOT / "data" / "reference" / f"{name}.json"
        if ref_path.exists() and not self.refresh:
            payload = json.loads(ref_path.read_text(encoding="utf-8"))
            retrieved_date = _date_from_payload(str(payload.get("retrieved_at", ""))[:10])
            if retrieved_date and retrieved_date >= datetime.now(UTC).date():
                rows = payload.get("rows", [])
                return CollectedDataset(name, "tushare.stock_basic", trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", True, str(ref_path), payload.get("error"))
        return self._collect_reference_frame(
            name,
            "tushare.stock_basic",
            lambda: pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,market,list_date"),
            trade_date,
            ref_path,
        )

    def _collect_reference_frame(
        self,
        name: str,
        source: str,
        fn: Callable[[], pd.DataFrame],
        data_date: date,
        path: Path,
    ) -> CollectedDataset:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = _frame_to_rows(fn())
            payload = {"source": source, "dataset": name, "retrieved_at": datetime.now(UTC).isoformat(), "data_date": data_date.isoformat(), "rows": rows, "error": None if rows else "empty response"}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return CollectedDataset(name, source, data_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", False, str(path), payload["error"])
        except Exception as exc:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload.get("rows", [])
                if rows:
                    return CollectedDataset(name, source, data_date, datetime.now(UTC), rows, "PASS", "historical", True, str(path), f"refresh failed: {exc.__class__.__name__}: {exc}")
            error = f"{exc.__class__.__name__}: {exc}"
            path.write_text(json.dumps({"source": source, "dataset": name, "retrieved_at": datetime.now(UTC).isoformat(), "data_date": data_date.isoformat(), "rows": [], "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
            return CollectedDataset(name, source, data_date, datetime.now(UTC), [], "FAIL", "historical", False, str(path), error)

    def _collect_tushare_previous_daily(self, pro, trade_date: date, previous_trade_date: date | None) -> CollectedDataset:
        name = "tushare_previous_daily_all"
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload["rows"]
            data_date = _date_from_payload(payload.get("data_date"))
            error = payload.get("error")
            return CollectedDataset(name, "tushare.daily", data_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical" if rows else "missing", True, str(cache), error)
        candidates = []
        if previous_trade_date:
            candidates.append(previous_trade_date)
        for offset in range(1, 8):
            candidate = trade_date - timedelta(days=offset)
            if candidate not in candidates:
                candidates.append(candidate)
        errors: list[str] = []
        for candidate in candidates:
            try:
                frame = pro.daily(trade_date=_compact(candidate))
                rows = _frame_to_rows(frame)
                if rows:
                    path = self._write_cache(trade_date, name, "tushare.daily", candidate, rows)
                    return CollectedDataset(name, "tushare.daily", candidate, datetime.now(UTC), rows, "PASS", "historical", False, str(path))
            except Exception as exc:
                errors.append(f"{candidate.isoformat()}:{exc.__class__.__name__}")
        path = self._write_cache(trade_date, name, "tushare.daily", previous_trade_date, [])
        error = f"no previous trading daily rows; sample_errors={errors[:5]}" if errors else "empty response"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["error"] = error
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return CollectedDataset(name, "tushare.daily", previous_trade_date, datetime.now(UTC), [], "FAIL", "missing", False, str(path), error)

    def _collect_stock_top_ohlcv(
        self,
        trade_date: date,
        datasets: dict[str, CollectedDataset],
        *,
        limit: int = 120,
    ) -> CollectedDataset:
        name = "stock_top_ohlcv"
        source = "akshare.stock_zh_a_hist; fallback akshare.stock_zh_a_hist_tx/stock_zh_a_daily"
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload["rows"]
            error = payload.get("error")
            quality = "PASS" if len(rows) >= 80 else "PARTIAL" if rows else "FAIL"
            return CollectedDataset(name, source, trade_date, datetime.now(UTC), rows, quality, "historical", True, str(cache), error)
        if ak is None:
            return CollectedDataset(name, source, trade_date, datetime.now(UTC), [], "FAIL", "missing", False, error="akshare import failed")
        codes = _stock_pool_codes(datasets, limit)
        tushare_rows = _stock_ohlcv_from_tushare_daily(datasets.get("tushare_daily_all"), codes)
        if tushare_rows:
            path = self._write_cache(trade_date, name, "tushare.daily", trade_date, tushare_rows)
            quality = "PASS" if len(tushare_rows) >= min(80, len(codes)) else "PARTIAL"
            return CollectedDataset(name, "tushare.daily", trade_date, datetime.now(UTC), tushare_rows, quality, "historical", False, str(path))
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for code in codes:
            try:
                frame = _fetch_stock_daily_frame(code, trade_date)
                for row in _frame_to_rows(frame):
                    row["source_stock_code"] = code
                    rows.append(row)
            except Exception as exc:
                errors.append(f"{code}:{exc.__class__.__name__}")
        path = self._write_cache(trade_date, name, source, trade_date, rows)
        if rows and errors:
            quality = "PARTIAL"
            error = f"{len(errors)} failed symbols; sample={errors[:8]}"
        elif rows:
            quality = "PASS" if len(rows) >= min(80, len(codes)) else "PARTIAL"
            error = None
        else:
            quality = "FAIL"
            error = f"empty response; failed symbols={errors[:8]}" if errors else "empty response"
        if error:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            payload["requested_symbols"] = codes
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return CollectedDataset(name, source, trade_date, datetime.now(UTC), rows, quality, "historical", False, str(path), error)

    def _collect_announcements(self, trade_date: date, datasets: dict[str, CollectedDataset], *, limit: int = 12) -> CollectedDataset:
        name = "official_announcements"
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            return CollectedDataset(name, payload.get("source", "cninfo"), trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", True, str(cache), payload.get("error"))
        seed_path = PROJECT_ROOT / "data" / "announcement_sources" / f"{trade_date.isoformat()}.json"
        if seed_path.exists() and not self.refresh:
            rows = json.loads(seed_path.read_text(encoding="utf-8"))
            path = self._write_cache(trade_date, name, "local.official_announcement_sources", trade_date, rows)
            return CollectedDataset(name, "local.official_announcement_sources", trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", False, str(path))
        if os.environ.get("MARKET_PACKET_REMOTE_ANNOUNCEMENTS") != "1":
            path = self._write_cache(trade_date, name, "cninfo.stock_zh_a_disclosure_report_cninfo", trade_date, [])
            error = "remote announcement lookups disabled; set MARKET_PACKET_REMOTE_ANNOUNCEMENTS=1 or provide data/announcement_sources/YYYY-MM-DD.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return CollectedDataset(name, "cninfo.stock_zh_a_disclosure_report_cninfo", trade_date, datetime.now(UTC), [], "FAIL", "historical", False, str(path), error)
        if ak is None:
            return CollectedDataset(name, "cninfo", trade_date, datetime.now(UTC), [], "FAIL", "missing", False, error="akshare import failed")
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        stock_names = _stock_names_by_code(datasets)
        for code in _stock_pool_codes(datasets, limit):
            try:
                frame = ak.stock_zh_a_disclosure_report_cninfo(symbol=code, start_date=_compact(trade_date), end_date=_compact(trade_date))
                for raw in _frame_to_rows(frame):
                    item = _normalize_announcement(raw, code, stock_names.get(code, ""))
                    if item and item["title"] not in {row["title"] for row in rows}:
                        rows.append(item)
            except Exception as exc:
                errors.append(f"{code}:{exc.__class__.__name__}")
        path = self._write_cache(trade_date, name, "cninfo.stock_zh_a_disclosure_report_cninfo", trade_date, rows)
        error = None
        if errors:
            error = f"{len(errors)} announcement lookups failed; sample={errors[:8]}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        quality = "PASS" if rows else "FAIL"
        return CollectedDataset(name, "cninfo.stock_zh_a_disclosure_report_cninfo", trade_date, datetime.now(UTC), rows, quality, "historical", False, str(path), error if not rows else None)

    def _collect_policies(self, trade_date: date) -> CollectedDataset:
        name = "official_policies"
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            return CollectedDataset(name, payload.get("source", "official_policy_sources"), trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", True, str(cache), payload.get("error"))
        seed_path = PROJECT_ROOT / "data" / "policy_sources" / f"{trade_date.isoformat()}.json"
        rows = []
        if seed_path.exists():
            rows = json.loads(seed_path.read_text(encoding="utf-8"))
        path = self._write_cache(trade_date, name, "official_policy_sources", trade_date, rows)
        error = None if rows else "official policy crawler not configured with stable historical source for this date"
        if error:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return CollectedDataset(name, "official_policy_sources", trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", False, str(path), error)

    def _collect_board_daily(self, trade_date: date, board_type: str, *, limit: int = 120) -> CollectedDataset:
        name = f"{board_type}_board_daily"
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            return CollectedDataset(name, payload.get("source", "akshare.eastmoney_board_hist"), trade_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", True, str(cache), payload.get("error"))
        if ak is None:
            return CollectedDataset(name, "akshare.eastmoney_board_hist", trade_date, datetime.now(UTC), [], "FAIL", "missing", False, error="akshare import failed")
        try:
            board_list = ak.stock_board_industry_name_em() if board_type == "industry" else ak.stock_board_concept_name_em()
        except Exception as exc:
            path = self._write_cache(trade_date, name, "akshare.eastmoney_board_hist", trade_date, [])
            error = f"board list failed: {exc.__class__.__name__}: {exc}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return CollectedDataset(name, "akshare.eastmoney_board_hist", trade_date, datetime.now(UTC), [], "FAIL", "historical", False, str(path), error)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for board in _frame_to_rows(board_list)[:limit]:
            board_name = _first_text(board, ["板块名称", "名称", "name", "板块"])
            if not board_name:
                continue
            try:
                hist_fn = ak.stock_board_industry_hist_em if board_type == "industry" else ak.stock_board_concept_hist_em
                hist = hist_fn(symbol=board_name, start_date=_compact(trade_date), end_date=_compact(trade_date))
                hist_rows = _frame_to_rows(hist)
                if not hist_rows:
                    continue
                item = dict(hist_rows[-1])
                item["board_type"] = board_type
                item["board_name"] = board_name
                item["board_code"] = _first_text(board, ["板块代码", "代码", "code"])
                item["source_data_date"] = trade_date.isoformat()
                rows.append(item)
            except Exception as exc:
                errors.append(f"{board_name}:{exc.__class__.__name__}")
        path = self._write_cache(trade_date, name, "akshare.eastmoney_board_hist", trade_date, rows)
        error = None
        if errors:
            error = f"{len(errors)} board history lookups failed; sample={errors[:8]}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        quality = "PASS" if len(rows) >= (30 if board_type == "industry" else 50) else "PARTIAL" if rows else "FAIL"
        return CollectedDataset(name, "akshare.eastmoney_board_hist", trade_date, datetime.now(UTC), rows, quality, "historical", False, str(path), error)

    def _collect_frame(
        self,
        name: str,
        source: str,
        fn: Callable[[], pd.DataFrame],
        trade_date: date,
        data_date: date | None,
        freshness: str,
    ) -> CollectedDataset:
        cache = self._cache_path(trade_date, name)
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            rows = payload["rows"]
            error = payload.get("error")
            if rows:
                return CollectedDataset(name, source, data_date, datetime.now(UTC), rows, "PASS", freshness, True, str(cache))
            if error and not self.refresh:
                return CollectedDataset(name, source, data_date, datetime.now(UTC), rows, "FAIL", freshness, True, str(cache), error)
        if ak is None:
            return CollectedDataset(name, source, data_date, datetime.now(UTC), [], "FAIL", "missing", False, error="akshare import failed")
        try:
            frame = fn()
            rows = _frame_to_rows(frame)
            path = self._write_cache(trade_date, name, source, data_date, rows)
            return CollectedDataset(name, source, data_date, datetime.now(UTC), rows, "PASS" if rows else "FAIL", freshness, False, str(path))
        except Exception as exc:
            path = self._write_cache(trade_date, name, source, data_date, [])
            error = f"{exc.__class__.__name__}: {exc}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return CollectedDataset(name, source, data_date, datetime.now(UTC), [], "FAIL", freshness, False, str(path), error)

    def _cache_path(self, trade_date: date, name: str) -> Path:
        return self.raw_root / trade_date.isoformat() / f"{name}.json"

    def _write_cache(
        self,
        trade_date: date,
        name: str,
        source: str,
        data_date: date | None,
        rows: list[dict[str, Any]],
    ) -> Path:
        path = self._cache_path(trade_date, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "dataset": name,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "data_date": data_date.isoformat() if data_date else None,
            "rows": rows,
            "error": None if rows else "empty response",
        }
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        payload["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def _fetch_stock_daily_frame(code: str, trade_date: date) -> pd.DataFrame:
    last_error: Exception | None = None
    for fn in (_fetch_stock_hist_em, _fetch_stock_hist_tx, _fetch_stock_daily_sina):
        try:
            frame = fn(code, trade_date)
            if frame is not None and not frame.empty:
                return frame
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.DataFrame()


def _fetch_stock_hist_em(code: str, trade_date: date) -> pd.DataFrame:
    return ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=_compact(trade_date),
        end_date=_compact(trade_date),
        adjust="",
    )


def _fetch_stock_hist_tx(code: str, trade_date: date) -> pd.DataFrame:
    return ak.stock_zh_a_hist_tx(
        symbol=_exchange_prefixed(code),
        start_date=_compact(trade_date),
        end_date=_compact(trade_date),
        adjust="",
    )


def _fetch_stock_daily_sina(code: str, trade_date: date) -> pd.DataFrame:
    return ak.stock_zh_a_daily(
        symbol=_exchange_prefixed(code),
        start_date=_compact(trade_date),
        end_date=_compact(trade_date),
        adjust="",
    )


def _exchange_prefixed(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return code


def _stock_pool_codes(datasets: dict[str, CollectedDataset], limit: int) -> list[str]:
    codes: list[str] = []
    for dataset_name in ("limit_up", "failed_limit", "limit_down", "previous_limit", "dragon_tiger_daily"):
        for row in datasets.get(dataset_name, CollectedDataset(dataset_name, "", None, datetime.now(UTC), [], "FAIL", "missing", False)).rows:
            value = row.get("代码") or row.get("code") or row.get("ts_code") or ""
            code = str(value).split(".")[0].zfill(6) if value != "" else ""
            if code and code not in codes:
                codes.append(code)
            if len(codes) >= limit:
                return codes
    return codes


def _code(row: dict[str, Any]) -> str:
    value = row.get("代码") or row.get("code") or row.get("股票代码") or row.get("ts_code") or ""
    return str(value).split(".")[0].zfill(6) if value != "" else ""


def _stock_ohlcv_from_tushare_daily(dataset: CollectedDataset | None, codes: list[str]) -> list[dict[str, Any]]:
    if not dataset or not dataset.rows or not codes:
        return []
    wanted = set(codes)
    rows = []
    for row in dataset.rows:
        ts_code = str(row.get("ts_code") or "")
        code = ts_code.split(".")[0]
        if code in wanted:
            item = dict(row)
            item["source_stock_code"] = code
            rows.append(item)
    return rows


def _stock_names_by_code(datasets: dict[str, CollectedDataset]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in datasets.get("tushare_stock_basic", CollectedDataset("tushare_stock_basic", "", None, datetime.now(UTC), [], "FAIL", "missing", False)).rows:
        ts_code = str(row.get("ts_code") or "")
        code = ts_code.split(".")[0]
        if code:
            names[code] = str(row.get("name") or "")
    for dataset_name in ("limit_up", "failed_limit", "limit_down", "previous_limit", "dragon_tiger_daily"):
        for row in datasets.get(dataset_name, CollectedDataset(dataset_name, "", None, datetime.now(UTC), [], "FAIL", "missing", False)).rows:
            code = _code(row)
            if code and code not in names:
                names[code] = str(row.get("名称") or row.get("name") or "")
    return names


def _normalize_announcement(row: dict[str, Any], code: str, fallback_name: str) -> dict[str, Any] | None:
    title = _first_text(row, ["公告标题", "标题", "title", "announcementTitle"])
    if not title:
        return None
    published = _first_text(row, ["公告时间", "公告日期", "发布时间", "published_at", "date"])
    url = _first_text(row, ["公告链接", "url", "URL", "adjunctUrl", "announcementUrl"])
    source = "巨潮资讯"
    summary = _clean_summary(_first_text(row, ["摘要", "summary"]) or title)
    category = _announcement_category(title)
    clarification_flags = [keyword for keyword in CLARIFICATION_KEYWORDS if keyword in title or keyword in summary]
    risk_flags = [keyword for keyword in RISK_KEYWORDS if keyword in title or keyword in summary]
    return {
        "stock_code": code,
        "stock_name": _first_text(row, ["证券简称", "股票简称", "名称", "stock_name"]) or fallback_name,
        "title": title,
        "published_at": published,
        "source": source,
        "url": _normalize_cninfo_url(url),
        "category": category,
        "summary": summary,
        "confirmed_fact": title,
        "evidence_level": "A",
        "clarification_flags": clarification_flags,
        "risk_flags": risk_flags,
    }


def _announcement_category(title: str) -> str:
    for keyword, category in ANNOUNCEMENT_CATEGORIES.items():
        if keyword in title:
            return category
    return "other"


def _normalize_cninfo_url(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if text.startswith("http"):
        return text
    if text.startswith("/"):
        return f"http://static.cninfo.com.cn{text}"
    if re.match(r"finalpage/\d{4}-\d{2}-\d{2}/", text):
        return f"http://static.cninfo.com.cn/{text}"
    return text


def _clean_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:220]


def _first_text(row: dict[str, Any] | None, keys: list[str]) -> str | None:
    if not row:
        return None
    for key in keys:
        value = row.get(key)
        if value not in ("", None):
            return str(value)
    return None


def _previous_trade_date(rows: list[dict[str, Any]], trade_date: date) -> date | None:
    current = _compact(trade_date)
    candidates: list[date] = []
    for row in rows:
        if int(row.get("is_open") or 0) != 1:
            continue
        value = str(row.get("cal_date") or "")
        if not value or value >= current:
            continue
        try:
            candidates.append(datetime.strptime(value, "%Y%m%d").date())
        except ValueError:
            continue
    return max(candidates) if candidates else None


def _date_from_payload(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _frame_to_rows(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%d")
    return [_json_safe(row) for row in clean.to_dict("records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
