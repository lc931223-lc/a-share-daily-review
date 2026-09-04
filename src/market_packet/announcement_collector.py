from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover - reported as collector failure
    ak = None


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
OFFICIAL_SOURCES = {"巨潮资讯", "上交所", "深交所", "北交所", "公司官网", "公司投资者关系"}
CATEGORIES = {
    "业绩预告": "earnings",
    "业绩快报": "earnings",
    "年度报告": "earnings",
    "季度报告": "earnings",
    "订单": "order",
    "中标": "order",
    "合同": "contract",
    "客户": "customer",
    "产品": "product",
    "产能": "capacity",
    "投产": "capacity",
    "重组": "restructuring",
    "合并": "merger",
    "吸收合并": "merger",
    "收购": "restructuring",
    "回购": "buyback",
    "增持": "increase_holding",
    "减持": "decrease_holding",
    "权益变动": "shareholding_change",
    "澄清": "clarification",
    "异常波动": "clarification",
    "风险": "risk_warning",
    "监管": "regulatory",
    "问询": "regulatory",
    "诉讼": "litigation",
    "仲裁": "litigation",
    "质押": "pledge",
    "停牌": "suspension",
    "复牌": "resumption",
}
CLARIFICATION_PHRASES = (
    "尚未形成订单",
    "未形成订单",
    "尚未形成收入",
    "业务占比较低",
    "业务占比低",
    "处于研发阶段",
    "仍在研发",
    "尚未通过客户认证",
    "尚未认证",
    "存在重大不确定性",
    "短期不会对业绩产生重大影响",
    "股价严重偏离基本面",
)
RISK_PHRASES = ("风险提示", "减持", "立案调查", "监管关注", "监管问询", "异常波动", "重大不确定性")


@dataclass(frozen=True)
class AnnouncementCandidate:
    stock_code: str
    stock_name: str
    source: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class AnnouncementCollection:
    records: list[dict[str, Any]]
    core_stock_count: int
    covered_stock_count: int
    failed_sources: list[str]
    official_source_available: bool
    cache_dir: str

    @property
    def coverage_rate(self) -> float:
        if self.core_stock_count == 0:
            return 0.0
        return round(self.covered_stock_count / self.core_stock_count, 4)

    @property
    def quality(self) -> str:
        if not self.official_source_available or self.coverage_rate < 0.60:
            return "FAIL"
        if self.coverage_rate < 0.90 or self.failed_sources:
            return "PARTIAL"
        return "PASS"


class AnnouncementCollector:
    def __init__(
        self,
        *,
        raw_root: Path,
        refresh: bool = False,
        fetcher: Callable[[str, date, date], pd.DataFrame] | None = None,
        max_stocks: int = 40,
    ):
        self.raw_root = raw_root
        self.refresh = refresh
        self.fetcher = fetcher or self._fetch_cninfo
        self.max_stocks = max_stocks

    def collect(self, trade_date: date, datasets: dict[str, Any], *, as_of_time: datetime | None = None) -> AnnouncementCollection:
        as_of = as_of_time or datetime.combine(trade_date, time(15, 30), SHANGHAI_TZ)
        cache_dir = self.raw_root / trade_date.isoformat() / "announcements"
        aggregate = cache_dir / "announcements.json"
        if aggregate.exists() and not self.refresh:
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            failed = payload.get("failed_sources", [])
            core_count = payload.get("core_stock_count", 0)
            failed_codes = {item.split(":")[1] for item in failed if item.startswith("cninfo:") and len(item.split(":")) >= 2}
            return AnnouncementCollection(
                records=payload.get("records", []),
                core_stock_count=core_count,
                covered_stock_count=max(0, core_count - len(failed_codes)),
                failed_sources=failed,
                official_source_available=payload.get("official_source_available", False),
                cache_dir=str(cache_dir),
            )
        candidates, failed_sources, core_count = self.discover_announcements(trade_date, datasets)
        records = []
        for candidate in candidates:
            item = self.fetch_official_announcement(candidate, trade_date, as_of)
            if item is not None:
                records.append(item)
        records = self.deduplicate_announcements(records)
        failed_codes = {item.split(":")[1] for item in failed_sources if item.startswith("cninfo:") and len(item.split(":")) >= 2}
        covered = max(0, core_count - len(failed_codes))
        collection = AnnouncementCollection(
            records=records,
            core_stock_count=core_count,
            covered_stock_count=covered,
            failed_sources=failed_sources,
            official_source_available=not failed_sources or bool(records),
            cache_dir=str(cache_dir),
        )
        self._write_aggregate(aggregate, collection)
        return collection

    def discover_announcements(self, trade_date: date, datasets: dict[str, Any]) -> tuple[list[AnnouncementCandidate], list[str], int]:
        cache_dir = self.raw_root / trade_date.isoformat() / "announcements"
        stock_names = _stock_names_by_code(datasets)
        codes = _core_stock_codes(datasets, self.max_stocks)
        if not codes:
            return [], ["core_stock_pool_empty"], 0
        start = trade_date - timedelta(days=1)
        candidates: list[AnnouncementCandidate] = []
        failed: list[str] = []
        if ak is None and self.fetcher == self._fetch_cninfo:
            return [], ["akshare_import_failed"], len(codes)
        for code in codes:
            try:
                frame = self.fetcher(code, start, trade_date)
            except Exception as exc:
                failed.append(f"cninfo:{code}:{exc.__class__.__name__}")
                continue
            rows = _frame_to_rows(frame)
            if not rows:
                continue
            for row in rows:
                candidates.append(AnnouncementCandidate(code, stock_names.get(code, ""), "巨潮资讯", row))
                self._write_raw_record(cache_dir, code, row)
        return candidates, failed, len(codes)

    def fetch_official_announcement(self, candidate: AnnouncementCandidate, trade_date: date, as_of_time: datetime) -> dict[str, Any] | None:
        item = self.normalize_announcement(candidate)
        if item is None:
            return None
        published = _parse_datetime(item.get("published_at"), trade_date)
        if published and published.astimezone(SHANGHAI_TZ) > as_of_time.astimezone(SHANGHAI_TZ):
            return None
        item["published_at"] = published.isoformat() if published else None
        item["data_date"] = trade_date.isoformat()
        item["retrieved_at"] = datetime.now(UTC).isoformat()
        return item

    def normalize_announcement(self, candidate: AnnouncementCandidate) -> dict[str, Any] | None:
        raw = candidate.raw
        raw_title = _first_text(raw, ["公告标题", "标题", "title", "announcementTitle"])
        if not raw_title:
            return None
        normalized_title = _normalize_title(raw_title)
        summary = _summary(_first_text(raw, ["摘要", "summary"]) or raw_title)
        source = candidate.source
        is_official = source in OFFICIAL_SOURCES
        category = self.classify_announcement(raw_title, summary)
        facts = self.extract_key_facts(raw_title, summary, category)
        return {
            "stock_code": candidate.stock_code,
            "stock_name": _first_text(raw, ["证券简称", "股票简称", "名称", "stock_name"]) or candidate.stock_name,
            "title": raw_title,
            "raw_title": raw_title,
            "normalized_title": normalized_title,
            "published_at": _first_text(raw, ["公告时间", "公告日期", "发布时间", "published_at", "date"]),
            "source": source,
            "source_type": "official" if is_official else "media",
            "is_official": is_official,
            "url": _normalize_url(_first_text(raw, ["公告链接", "url", "URL", "adjunctUrl", "announcementUrl"])),
            "category": category,
            "summary": summary,
            "confirmed_fact": raw_title,
            "evidence_level": "A" if is_official else "B",
            "primary_source": source,
            "supplemental_sources": [],
            **facts,
        }

    def classify_announcement(self, title: str, summary: str = "") -> str:
        text = title + " " + summary
        if any(phrase in text for phrase in RISK_PHRASES if phrase != "减持"):
            return "risk_warning"
        for keyword, category in CATEGORIES.items():
            if keyword in text:
                return category
        return "other"

    def extract_key_facts(self, title: str, summary: str, category: str) -> dict[str, Any]:
        text = title + " " + summary
        facts = {
            "contract_amount": _first_amount(text) if category in {"order", "contract"} else None,
            "customer_name": None,
            "contract_period": None,
            "revenue_ratio_if_disclosed": _first_ratio(text),
            "profit_impact_if_disclosed": None,
            "uncertainty_flag": any(phrase in text for phrase in CLARIFICATION_PHRASES + ("存在重大不确定性",)),
            "revenue": None,
            "revenue_yoy": None,
            "net_profit": None,
            "net_profit_yoy": None,
            "guidance_low": None,
            "guidance_high": None,
            "clarification_flags": [phrase for phrase in CLARIFICATION_PHRASES if phrase in text],
            "risk_flags": [phrase for phrase in RISK_PHRASES if phrase in text],
        }
        return facts

    def deduplicate_announcements(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        for item in records:
            key = (item["stock_code"], item["normalized_title"], item.get("published_at"))
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = item
                continue
            if item.get("is_official") and not existing.get("is_official"):
                item["supplemental_sources"] = [existing["source"], *existing.get("supplemental_sources", [])]
                grouped[key] = item
            else:
                sources = existing.setdefault("supplemental_sources", [])
                if item["source"] != existing["source"] and item["source"] not in sources:
                    sources.append(item["source"])
        return sorted(grouped.values(), key=lambda row: (row.get("published_at") or "", row["stock_code"], row["normalized_title"]))

    def _fetch_cninfo(self, code: str, start: date, end: date) -> pd.DataFrame:
        return ak.stock_zh_a_disclosure_report_cninfo(symbol=code, start_date=_compact(start), end_date=_compact(end))

    def _write_raw_record(self, cache_dir: Path, code: str, row: dict[str, Any]) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        title = _first_text(row, ["公告标题", "标题", "title", "announcementTitle"]) or ""
        url = _first_text(row, ["公告链接", "url", "URL", "adjunctUrl", "announcementUrl"])
        text = json.dumps(row, ensure_ascii=False, sort_keys=True)
        payload = {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source_url": _normalize_url(url),
            "source_hash": hashlib.sha256(str(url or title).encode("utf-8")).hexdigest(),
            "published_at": _first_text(row, ["公告时间", "公告日期", "发布时间", "published_at", "date"]),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "raw": row,
        }
        (cache_dir / f"{code}-{payload['content_hash'][:16]}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_aggregate(self, path: Path, collection: AnnouncementCollection) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "records": collection.records,
            "core_stock_count": collection.core_stock_count,
            "covered_stock_count": collection.covered_stock_count,
            "coverage_rate": collection.coverage_rate,
            "failed_sources": collection.failed_sources,
            "official_source_available": collection.official_source_available,
            "quality": collection.quality,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_announcement_sections(records: list[dict[str, Any]], collection: AnnouncementCollection | None = None) -> dict[str, Any]:
    risk = [row for row in records if row.get("risk_flags") or row.get("category") in {"risk_warning", "regulatory", "litigation", "pledge", "decrease_holding"}]
    clarifications = [row for row in records if row.get("clarification_flags") or row.get("category") == "clarification"]
    orders = [row for row in records if row.get("category") in {"order", "contract"}]
    earnings = [row for row in records if row.get("category") == "earnings"]
    return {
        "records": records,
        "important_announcements": records[:50],
        "risk_announcements": risk,
        "clarifications": clarifications,
        "orders_contracts": orders,
        "earnings_updates": earnings,
        "metadata": {
            "core_stock_count": collection.core_stock_count if collection else None,
            "covered_stock_count": collection.covered_stock_count if collection else None,
            "coverage_rate": collection.coverage_rate if collection else None,
            "failed_sources": collection.failed_sources if collection else [],
            "official_source_available": collection.official_source_available if collection else bool(records),
            "quality": collection.quality if collection else ("PASS" if records else "FAIL"),
            "cache_dir": collection.cache_dir if collection else None,
        },
    }


def _core_stock_codes(datasets: dict[str, Any], limit: int) -> list[str]:
    codes: list[str] = []
    for dataset_name in ("limit_up", "limit_down", "previous_limit", "failed_limit", "dragon_tiger_daily"):
        for row in getattr(datasets.get(dataset_name), "rows", []):
            code = _code(row)
            if code and code not in codes:
                codes.append(code)
            if len(codes) >= limit:
                return codes
    daily = sorted(getattr(datasets.get("tushare_daily_all"), "rows", []), key=lambda row: float(row.get("amount") or 0), reverse=True)
    for row in daily:
        code = str(row.get("ts_code") or "").split(".")[0]
        if code and code not in codes:
            codes.append(code)
        if len(codes) >= limit:
            return codes
    return codes


def _stock_names_by_code(datasets: dict[str, Any]) -> dict[str, str]:
    names = {}
    for row in getattr(datasets.get("tushare_stock_basic"), "rows", []):
        code = str(row.get("ts_code") or "").split(".")[0]
        if code:
            names[code] = str(row.get("name") or "")
    for dataset_name in ("limit_up", "failed_limit", "limit_down", "previous_limit", "dragon_tiger_daily"):
        for row in getattr(datasets.get(dataset_name), "rows", []):
            code = _code(row)
            if code and code not in names:
                names[code] = str(row.get("名称") or row.get("name") or "")
    return names


def _code(row: dict[str, Any]) -> str:
    value = row.get("代码") or row.get("code") or row.get("股票代码") or row.get("ts_code") or ""
    return str(value).split(".")[0].zfill(6) if value != "" else ""


def _frame_to_rows(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%d")
    return clean.to_dict("records")


def _first_text(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in ("", None):
            return str(value)
    return None


def _compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).replace("：", ":").strip()


def _summary(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()[:300]


def _normalize_url(value: str | None) -> str | None:
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


def _parse_datetime(value: Any, fallback_date: date) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=SHANGHAI_TZ)
    if isinstance(value, date):
        return datetime.combine(value, time(0), SHANGHAI_TZ)
    if value in ("", None):
        return datetime.combine(fallback_date, time(0), SHANGHAI_TZ)
    text = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None


def _first_amount(text: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(亿元|万元)", text)
    if not match:
        return None
    value = float(match.group(1))
    return value * 100000000 if match.group(2) == "亿元" else value * 10000


def _first_ratio(text: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    return float(match.group(1)) if match else None
