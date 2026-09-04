from __future__ import annotations

import hashlib
import gzip
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
    {"agency": "中国政府网", "url": "https://www.gov.cn/zhengce/zuixin/", "policy_level": "national", "allow_paths": ["/zhengce/"]},
    {"agency": "国家发改委", "url": "https://www.ndrc.gov.cn/xxgk/zcfb/", "policy_level": "ministerial", "allow_paths": ["/xxgk/zcfb/"]},
    {"agency": "工信部", "url": "https://zwgk.miit.gov.cn/", "policy_level": "ministerial", "allow_paths": ["/zcwj/", "/policy/", "/zwgk/"]},
    {"agency": "财政部", "url": "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/", "policy_level": "ministerial", "allow_paths": ["/zhengcefabu/"]},
    {"agency": "商务部", "url": "https://www.mofcom.gov.cn/zwgk/zcfb/", "policy_level": "ministerial", "allow_paths": ["/zwgk/zcfb/"]},
    {"agency": "人民银行", "url": "https://www.pbc.gov.cn/tiaofasi/144941/144957/index.html", "policy_level": "ministerial", "allow_paths": ["/tiaofasi/"]},
    {"agency": "证监会", "url": "https://www.csrc.gov.cn/csrc/c100028/zfxxgk_zdgk.shtml", "policy_level": "ministerial", "allow_paths": ["/c100028/", "/zcfg/"]},
    {"agency": "上交所", "url": "https://www.sse.com.cn/lawandrules/sselawsrules/", "policy_level": "ministerial", "allow_paths": ["/lawandrules/"]},
    {"agency": "深交所", "url": "https://www.szse.cn/lawrules/rule/allrules/index.html", "policy_level": "ministerial", "allow_paths": ["/lawrules/"]},
    {"agency": "北交所", "url": "https://www.bseinfo.net/business/overview.html", "policy_level": "ministerial", "allow_paths": ["/rule/", "/law/", "/business/"]},
    {"agency": "国家能源局", "url": "https://www.nea.gov.cn/nyflfg/", "policy_level": "ministerial", "allow_paths": ["/nyflfg/", "/zcwj/"]},
    {"agency": "科技部", "url": "https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/", "policy_level": "ministerial", "allow_paths": ["/fgzc/"]},
    {"agency": "国家卫健委", "url": "https://www.nhc.gov.cn/wjw/gfxwj/list.shtml", "policy_level": "ministerial", "allow_paths": ["/gfxwj/"]},
    {"agency": "农业农村部", "url": "https://www.moa.gov.cn/gk/zcfg/", "policy_level": "ministerial", "allow_paths": ["/gk/zcfg/"]},
    {"agency": "住建部", "url": "https://www.mohurd.gov.cn/gongkai/zhengce/zhengcefilelib/", "policy_level": "ministerial", "allow_paths": ["/gongkai/zhengce/"]},
]
POLICY_SCHEMA_VERSION = "policy.2"
NAVIGATION_TITLES = {"APP下载", "English", "English Version", "一网通办", "首页", "登录", "导航", "专题", "下载客户端", "友情链接", "更多", "【更多】", "hide"}
DENY_URL_PARTS = ("/english", "_en/", "/app/", "/login", "javascript:", "mailto:")
POLICY_TITLE_KEYWORDS = ("通知", "公告", "意见", "办法", "规定", "决定", "批复", "函", "规则", "指引", "政策", "条例", "法", "方案", "细则", "标准")
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
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


class OfficialPolicyAdapter:
    def __init__(self, agency: str, url: str, policy_level: str):
        self.source = {"agency": agency, "url": url, "policy_level": policy_level}

    @property
    def agency(self) -> str:
        return self.source["agency"]

    def headers(self) -> dict[str, str]:
        return {"User-Agent": _USER_AGENT, "Referer": self.source["url"]}

    def fetch_html(self, client: SafeHttpClient, source_fetcher: Callable[[dict[str, str]], str] | None = None) -> str:
        if source_fetcher is not None:
            return source_fetcher(self.source)
        response = client.get(
            self.source["url"],
            headers=self.headers(),
            source=self.agency,
            dataset="policy_scan",
        )
        if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def discover(self, html: str) -> list[dict[str, Any]]:
        return _discover_links_from_html(html, self.source)


class MiitPolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("工信部", "https://zwgk.miit.gov.cn/", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://zwgk.miit.gov.cn/"}


class CsrcPolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("证监会", "https://www.csrc.gov.cn/csrc/c100028/zfxxgk_zdgk.shtml", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://www.csrc.gov.cn/"}


class BsePolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("北交所", "https://www.bseinfo.net/business/overview.html", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://www.bseinfo.net/"}


class NeaPolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("国家能源局", "https://www.nea.gov.cn/nyflfg/", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://www.nea.gov.cn/"}


class NhcPolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("国家卫健委", "https://www.nhc.gov.cn/wjw/gfxwj/list.shtml", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://www.nhc.gov.cn/"}


class MohurdPolicyAdapter(OfficialPolicyAdapter):
    def __init__(self):
        super().__init__("住建部", "https://www.mohurd.gov.cn/gongkai/zhengce/zhengcefilelib/", "ministerial")

    def headers(self) -> dict[str, str]:
        return {**super().headers(), "Referer": "https://www.mohurd.gov.cn/"}


def _default_policy_adapters() -> list[OfficialPolicyAdapter]:
    specialized = {
        "工信部": MiitPolicyAdapter(),
        "证监会": CsrcPolicyAdapter(),
        "北交所": BsePolicyAdapter(),
        "国家能源局": NeaPolicyAdapter(),
        "国家卫健委": NhcPolicyAdapter(),
        "住建部": MohurdPolicyAdapter(),
    }
    adapters: list[OfficialPolicyAdapter] = []
    for source in OFFICIAL_POLICY_SOURCES:
        adapter = specialized.get(source["agency"]) or OfficialPolicyAdapter(source["agency"], source["url"], source["policy_level"])
        adapter.source = dict(source)
        adapters.append(adapter)
    return adapters


@dataclass(frozen=True)
class PolicyCollection:
    records: list[dict[str, Any]]
    scanned_sources: list[str]
    failed_sources: list[str]
    cache_dir: str
    background_reference: list[dict[str, Any]] | None = None
    rejected_records: list[dict[str, Any]] | None = None
    invalid_reasons: list[str] | None = None

    @property
    def quality(self) -> str:
        if self.invalid_reasons:
            return "INVALID"
        if self.records and self.failed_sources:
            return "PARTIAL"
        if len(self.scanned_sources) < 3:
            return "FAIL"
        if self.failed_sources:
            return "PARTIAL"
        return "PASS" if self.records else "EMPTY_VALID"


class PolicyCollector:
    def __init__(
        self,
        *,
        raw_root: Path,
        refresh: bool = False,
        client: SafeHttpClient | None = None,
        source_fetcher: Callable[[dict[str, str]], str] | None = None,
        adapters: list[OfficialPolicyAdapter] | None = None,
    ):
        self.raw_root = raw_root
        self.refresh = refresh
        self.client = client or SafeHttpClient(timeout=8, max_retries=1, source="official_policy", dataset="policy_scan")
        self.source_fetcher = source_fetcher
        self.adapters = adapters or _default_policy_adapters()

    def collect(self, trade_date: date, themes: list[dict[str, Any]] | None = None, *, as_of_time: datetime | None = None) -> PolicyCollection:
        as_of = as_of_time or datetime.combine(trade_date, time(15, 30), SHANGHAI_TZ)
        cache_dir = self.raw_root / trade_date.isoformat() / "policies"
        aggregate = cache_dir / "policies.json"
        if aggregate.exists() and not self.refresh:
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            if payload.get("schema_version") == POLICY_SCHEMA_VERSION:
                return PolicyCollection(
                    payload.get("records", []), payload.get("scanned_sources", []), payload.get("failed_sources", []), str(cache_dir),
                    payload.get("background_reference", []), payload.get("rejected_records", []), payload.get("invalid_reasons", []),
                )
        batch_path = cache_dir / "source_records.jsonl.gz"
        if self.refresh and batch_path.exists():
            batch_path.unlink()
        self._batch_hashes = _read_batch_hashes(batch_path)
        seed_path = Path("data") / "policy_sources" / f"{trade_date.isoformat()}.json"
        records: list[dict[str, Any]] = []
        background: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        scanned: list[str] = []
        failed: list[str] = []
        if seed_path.exists() and not self.refresh:
            records.extend(json.loads(seed_path.read_text(encoding="utf-8")))
            scanned.append("local.policy_sources")
        keywords = self._keywords_for_themes(themes or [])
        for adapter in self.adapters:
            source = adapter.source
            try:
                html = adapter.fetch_html(self.client, self.source_fetcher)
                candidates = adapter.discover(html)
                scanned.append(source["agency"])
                for candidate in candidates:
                    item = self.normalize_policy(candidate, source, trade_date, keywords)
                    rejection = _policy_rejection_reason(item, source)
                    if rejection:
                        rejected.append({"agency": source["agency"], "title": item.get("title"), "url": item.get("url"), "reason": rejection})
                        continue
                    published = _parse_datetime(item.get("published_at"), trade_date)
                    if published is None:
                        rejected.append({"agency": source["agency"], "title": item.get("title"), "url": item.get("url"), "reason": "missing_published_at"})
                        continue
                    if published.astimezone(SHANGHAI_TZ) > as_of.astimezone(SHANGHAI_TZ):
                        rejected.append({"agency": source["agency"], "title": item.get("title"), "url": item.get("url"), "reason": "future_published_at"})
                        continue
                    item["published_at"] = published.isoformat() if published else None
                    item["retrieved_at"] = datetime.now(UTC).isoformat()
                    item["data_date"] = published.date().isoformat()
                    if published.date() < trade_date:
                        background.append(item)
                        continue
                    if published.date() > trade_date:
                        rejected.append({"agency": source["agency"], "title": item.get("title"), "url": item.get("url"), "reason": "cross_date"})
                        continue
                    records.append(item)
                    self._write_raw_record(cache_dir, item)
            except Exception as exc:
                failed.append(f"{source['agency']}:{exc.__class__.__name__}")
        records = self.deduplicate_policies(records)
        invalid = _formal_policy_invalid_reasons(records, trade_date, as_of)
        collection = PolicyCollection(records, scanned, failed, str(cache_dir), background, rejected, invalid)
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
        return _discover_links_from_html(html, source)

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
        response = self.client.get(source["url"], headers={"User-Agent": _USER_AGENT, "Referer": source["url"]}, source=source["agency"], dataset="policy_scan")
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
        content_hash = payload["content_hash"]
        if content_hash in getattr(self, "_batch_hashes", set()):
            return
        self._batch_hashes.add(content_hash)
        with gzip.open(cache_dir / "source_records.jsonl.gz", "at", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _write_aggregate(self, path: Path, collection: PolicyCollection) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": POLICY_SCHEMA_VERSION,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "records": collection.records,
            "background_reference": collection.background_reference or [],
            "rejected_records": collection.rejected_records or [],
            "invalid_reasons": collection.invalid_reasons or [],
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
        "daily_policy_events": records,
        "background_reference": (collection.background_reference or []) if collection else [],
        "metadata": {
            "scanned_sources": collection.scanned_sources if collection else [],
            "failed_sources": collection.failed_sources if collection else [],
            "quality": collection.quality if collection else ("PASS" if records else "FAIL"),
            "rejected_count": len(collection.rejected_records or []) if collection else 0,
            "invalid_reasons": collection.invalid_reasons or [] if collection else [],
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


def _discover_links_from_html(html: str, source: dict[str, str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue
        url = urljoin(source["url"], link["href"])
        if not _url_allowed(url, source):
            continue
        nearby = link.find_parent()
        text = nearby.get_text(" ", strip=True) if nearby else title
        rows.append({"title": title, "url": url, "summary": text, "published_at": _extract_date(text)})
    return rows[:80]


def _url_allowed(url: str, source: dict[str, Any]) -> bool:
    lowered = url.lower()
    if any(part in lowered for part in DENY_URL_PARTS):
        return False
    allowed = source.get("allow_paths") or []
    policy_path_markers = ("/policy", "/zhengce", "/zcfg", "/zcwj", "/law", "/rule")
    return not allowed or any(part.lower() in lowered for part in allowed) or any(part in lowered for part in policy_path_markers)


def _policy_rejection_reason(item: dict[str, Any], source: dict[str, Any]) -> str | None:
    title = str(item.get("title") or "").strip()
    if title in NAVIGATION_TITLES or title.strip("【】[] ") in NAVIGATION_TITLES:
        return "navigation_title"
    if len(title) < 4 or len(title) > 180:
        return "abnormal_title_length"
    if "�" in title or sum(title.count(ch) for ch in ("Ã", "Â", "å", "æ", "ç", "è", "é", "ä")) >= 3:
        return "mojibake_title"
    if not any(keyword in title for keyword in POLICY_TITLE_KEYWORDS):
        return "not_policy_document"
    if not _url_allowed(str(item.get("url") or ""), source):
        return "url_not_allowed"
    return None


def _formal_policy_invalid_reasons(records: list[dict[str, Any]], trade_date: date, as_of: datetime) -> list[str]:
    reasons: list[str] = []
    for item in records:
        published = _parse_datetime(item.get("published_at"), trade_date)
        if published is None:
            reasons.append("missing_published_at")
        elif published.date() != trade_date:
            reasons.append("cross_date_pollution")
        elif published.astimezone(SHANGHAI_TZ) > as_of.astimezone(SHANGHAI_TZ):
            reasons.append("future_pollution")
        if _policy_rejection_reason(item, {"allow_paths": [], "agency": item.get("agency")}) in {"navigation_title", "mojibake_title", "not_policy_document"}:
            reasons.append("content_pollution")
    return sorted(set(reasons))


def _extract_date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if not match:
        return None
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _read_batch_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    hashes: set[str] = set()
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                value = json.loads(line).get("content_hash")
                if value:
                    hashes.add(str(value))
    except (OSError, json.JSONDecodeError):
        return set()
    return hashes


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
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=SHANGHAI_TZ)
    except ValueError:
        pass
    text = raw[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None
