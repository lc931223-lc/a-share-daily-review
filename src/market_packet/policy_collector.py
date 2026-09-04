from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from src.adapters.http import SafeHttpClient


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
OFFICIAL_POLICY_SOURCES = [
    {"agency": "中国政府网", "url": "https://www.gov.cn/zhengce/zuixin/", "policy_level": "national"},
    {"agency": "国家发改委", "url": "https://www.ndrc.gov.cn/xxgk/zcfb/", "policy_level": "ministerial"},
    {"agency": "工信部", "url": "https://www.miit.gov.cn/zwgk/zcwj/", "policy_level": "ministerial"},
    {"agency": "财政部", "url": "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/", "policy_level": "ministerial"},
    {"agency": "商务部", "url": "https://www.mofcom.gov.cn/zwgk/zcfb/", "policy_level": "ministerial"},
    {"agency": "人民银行", "url": "https://www.pbc.gov.cn/tiaofasi/144941/144957/index.html", "policy_level": "ministerial"},
    {"agency": "证监会", "url": "https://www.csrc.gov.cn/csrc/c100028/zfxxgk_zdgk.shtml", "policy_level": "ministerial"},
    {"agency": "上交所", "url": "https://www.sse.com.cn/lawandrules/sselawsrules/", "policy_level": "ministerial"},
    {"agency": "深交所", "url": "https://www.szse.cn/lawrules/rule/allrules/index.html", "policy_level": "ministerial"},
    {"agency": "北交所", "url": "https://www.bse.cn/rule/", "policy_level": "ministerial"},
    {"agency": "国家能源局", "url": "https://www.nea.gov.cn/2021-12/27/c_1310399847.htm", "policy_level": "ministerial"},
    {"agency": "科技部", "url": "https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/", "policy_level": "ministerial"},
    {"agency": "国家卫健委", "url": "https://www.nhc.gov.cn/wjw/gfxwj/list.shtml", "policy_level": "ministerial"},
    {"agency": "农业农村部", "url": "https://www.moa.gov.cn/gk/zcfg/", "policy_level": "ministerial"},
    {"agency": "住建部", "url": "https://www.mohurd.gov.cn/gongkai/zhengce/zhengcefilelib/", "policy_level": "ministerial"},
]
THEME_KEYWORDS = {
    "机器人": ["机器人", "智能制造"],
    "AI": ["人工智能", "算力", "大模型"],
    "半导体": ["半导体", "集成电路", "芯片"],
    "农业": ["农业", "种业", "粮食"],
    "房地产": ["房地产", "住房", "城中村"],
    "消费": ["消费", "零售", "服务消费"],
}
ACTION_KEYWORDS = {
    "补贴": "subsidy",
    "支持": "support",
    "鼓励": "support",
    "监管": "regulation",
    "限制": "restriction",
    "试点": "pilot",
    "标准": "standard",
    "采购": "procurement",
    "税": "tax",
    "金融": "finance",
    "投资": "investment",
}


@dataclass(frozen=True)
class PolicyCollection:
    records: list[dict[str, Any]]
    scanned_sources: list[str]
    failed_sources: list[str]
    cache_dir: str

    @property
    def quality(self) -> str:
        if self.records and self.failed_sources:
            return "PARTIAL"
        if len(self.scanned_sources) < 3:
            return "FAIL"
        if self.failed_sources:
            return "PARTIAL"
        return "PASS"


class PolicyCollector:
    def __init__(
        self,
        *,
        raw_root: Path,
        refresh: bool = False,
        client: SafeHttpClient | None = None,
        source_fetcher: Callable[[dict[str, str]], str] | None = None,
    ):
        self.raw_root = raw_root
        self.refresh = refresh
        self.client = client or SafeHttpClient(timeout=8, max_retries=1, source="official_policy", dataset="policy_scan")
        self.source_fetcher = source_fetcher or self._fetch_source_html

    def collect(self, trade_date: date, themes: list[dict[str, Any]] | None = None, *, as_of_time: datetime | None = None) -> PolicyCollection:
        as_of = as_of_time or datetime.combine(trade_date, time(15, 30), SHANGHAI_TZ)
        cache_dir = self.raw_root / trade_date.isoformat() / "policies"
        aggregate = cache_dir / "policies.json"
        if aggregate.exists() and not self.refresh:
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            return PolicyCollection(payload.get("records", []), payload.get("scanned_sources", []), payload.get("failed_sources", []), str(cache_dir))
        seed_path = Path("data") / "policy_sources" / f"{trade_date.isoformat()}.json"
        records: list[dict[str, Any]] = []
        scanned: list[str] = []
        failed: list[str] = []
        if seed_path.exists() and not self.refresh:
            records.extend(json.loads(seed_path.read_text(encoding="utf-8")))
            scanned.append("local.policy_sources")
        keywords = self._keywords_for_themes(themes or [])
        for source in OFFICIAL_POLICY_SOURCES:
            try:
                html = self.source_fetcher(source)
                candidates = self._discover_from_html(html, source)
                scanned.append(source["agency"])
                for candidate in candidates:
                    item = self.normalize_policy(candidate, source, trade_date, keywords)
                    published = _parse_datetime(item.get("published_at"), trade_date)
                    if published and published.astimezone(SHANGHAI_TZ) > as_of.astimezone(SHANGHAI_TZ):
                        continue
                    item["published_at"] = published.isoformat() if published else None
                    item["retrieved_at"] = datetime.now(UTC).isoformat()
                    item["data_date"] = trade_date.isoformat()
                    records.append(item)
                    self._write_raw_record(cache_dir, item)
            except Exception as exc:
                failed.append(f"{source['agency']}:{exc.__class__.__name__}")
        records = self.deduplicate_policies(records)
        collection = PolicyCollection(records, scanned, failed, str(cache_dir))
        self._write_aggregate(aggregate, collection)
        return collection

    def normalize_policy(self, candidate: dict[str, Any], source: dict[str, str], trade_date: date, keywords: list[str]) -> dict[str, Any]:
        title = str(candidate.get("title") or "")
        summary = _summary(candidate.get("summary") or title)
        related = [keyword for keyword in keywords if keyword and keyword in title + summary]
        is_official = True
        return {
            "title": title,
            "raw_title": title,
            "normalized_title": _normalize_title(title),
            "agency": source["agency"],
            "published_at": candidate.get("published_at"),
            "url": candidate.get("url"),
            "source": source["agency"],
            "source_type": "official",
            "is_official": is_official,
            "evidence_level": "A",
            "policy_level": source["policy_level"],
            "related_industries": related,
            "related_themes": related,
            "summary": summary,
            "confirmed_fact": title,
            "action_type": self._classify_action(title + summary),
        }

    def deduplicate_policies(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str | None], dict[str, Any]] = {}
        for item in records:
            key = (item["normalized_title"], item.get("published_at"))
            if item.get("published_at") is None:
                for existing_key in list(grouped):
                    if existing_key[0] == item["normalized_title"]:
                        key = existing_key
                        break
            elif key not in grouped:
                for existing_key in list(grouped):
                    if existing_key[0] == item["normalized_title"] and existing_key[1] is None:
                        key = existing_key
                        break
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = item
                continue
            if item.get("is_official") and not existing.get("is_official"):
                grouped[key] = item
        return sorted(grouped.values(), key=lambda row: (row.get("published_at") or "", row["normalized_title"]))

    def _discover_from_html(self, html: str, source: dict[str, str]) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        rows = []
        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            if not title or len(title) < 4:
                continue
            url = urljoin(source["url"], link["href"])
            nearby = link.find_parent()
            text = nearby.get_text(" ", strip=True) if nearby else title
            rows.append({"title": title, "url": url, "summary": text, "published_at": _extract_date(text)})
        return rows[:80]

    def _keywords_for_themes(self, themes: list[dict[str, Any]]) -> list[str]:
        found: list[str] = []
        for theme in themes[:20]:
            name = str(theme.get("theme_name") or theme.get("name") or "")
            for key, values in THEME_KEYWORDS.items():
                if key in name:
                    found.extend(values)
            if name:
                found.append(name)
        return list(dict.fromkeys(found))

    def _classify_action(self, text: str) -> str:
        for keyword, action in ACTION_KEYWORDS.items():
            if keyword in text:
                return action
        return "other"

    def _fetch_source_html(self, source: dict[str, str]) -> str:
        response = self.client.get(source["url"], source=source["agency"], dataset="policy_scan")
        response.encoding = response.encoding or "utf-8"
        return response.text

    def _write_raw_record(self, cache_dir: Path, item: dict[str, Any]) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(item, ensure_ascii=False, sort_keys=True)
        payload = {
            "retrieved_at": item.get("retrieved_at"),
            "source_url": item.get("url"),
            "source_hash": hashlib.sha256(str(item.get("url") or item.get("title")).encode("utf-8")).hexdigest(),
            "published_at": item.get("published_at"),
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "raw": item,
        }
        (cache_dir / f"{payload['content_hash'][:16]}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_aggregate(self, path: Path, collection: PolicyCollection) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "records": collection.records,
            "scanned_sources": collection.scanned_sources,
            "failed_sources": collection.failed_sources,
            "quality": collection.quality,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_policy_sections(records: list[dict[str, Any]], collection: PolicyCollection | None = None) -> dict[str, Any]:
    return {
        "records": records,
        "national_policies": [row for row in records if row.get("policy_level") == "national"],
        "ministerial_policies": [row for row in records if row.get("policy_level") == "ministerial"],
        "local_policies": [row for row in records if row.get("policy_level") == "local"],
        "related_theme_policies": [row for row in records if row.get("related_themes")],
        "metadata": {
            "scanned_sources": collection.scanned_sources if collection else [],
            "failed_sources": collection.failed_sources if collection else [],
            "quality": collection.quality if collection else ("PASS" if records else "FAIL"),
            "cache_dir": collection.cache_dir if collection else None,
        },
    }


def media_policy_record(title: str, source: str, url: str | None = None) -> dict[str, Any]:
    return {
        "title": title,
        "raw_title": title,
        "normalized_title": _normalize_title(title),
        "agency": source,
        "published_at": None,
        "url": url,
        "source": source,
        "source_type": "media",
        "is_official": False,
        "evidence_level": "B",
        "policy_level": "ministerial",
        "related_industries": [],
        "related_themes": [],
        "summary": _summary(title),
        "confirmed_fact": title,
        "action_type": "other",
    }


def _extract_date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if not match:
        return None
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).replace("：", ":").strip()


def _summary(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()[:300]


def _parse_datetime(value: Any, fallback_date: date) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=SHANGHAI_TZ)
    if isinstance(value, date):
        return datetime.combine(value, time(0), SHANGHAI_TZ)
    if value in ("", None):
        return None
    text = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None
