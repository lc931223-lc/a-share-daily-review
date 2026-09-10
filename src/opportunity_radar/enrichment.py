"""V2.1 source adapters feeding the existing observation store."""
import calendar
import hashlib
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.opportunity_radar.contracts import SHANGHAI, number, stamp, digest
from src.opportunity_radar.storage import archive_json
from src.opportunity_radar.disclosure_body_extraction import extract_body, pdf_text, verified_body_relations

REGISTRY = {
    "nbs": {"url": "https://www.stats.gov.cn/sj/zxfbhjd/", "tier": 1, "frequency": "release_calendar", "kind": "OFFICIAL_RELEASE"},
    "dram": {"url": "https://www.dramexchange.com/", "tier": 3, "frequency": "daily_or_weekly", "kind": "SPOT_QUOTE"},
    "twse": {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L", "tier": 2, "frequency": "monthly", "kind": "OFFICIAL_MONTHLY_REVENUE"},
    "tpex": {"url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O", "tier": 2, "frequency": "monthly", "kind": "OFFICIAL_MONTHLY_REVENUE"},
    "sec": {"url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json", "tier": 2, "frequency": "filing", "kind": "OFFICIAL_XBRL"},
    "cninfo": {"url": "https://www.cninfo.com.cn/new/hisAnnouncement/query", "tier": 1, "frequency": "per_snapshot", "kind": "OFFICIAL_DISCLOSURE_DISCOVERY"},
}
# These are issuer identifiers for retrieval, not verified supply-chain edges.
TAIWAN = {"2408": "存储", "2344": "存储", "3260": "存储", "8299": "存储", "2327": "MLCC",
          "2492": "MLCC", "2383": "PCB/CCL", "3037": "PCB/CCL", "2313": "PCB/CCL",
          "2368": "PCB/CCL", "6223": "探针/测试", "6510": "探针/测试", "3363": "光通信",
          "4979": "光通信", "2330": "晶圆制造", "3711": "先进封装"}
NBS_SEEDS = ["https://www.stats.gov.cn/sj/zxfbhjd/202607/t20260715_1964130.html",
             "https://www.stats.gov.cn/sj/zxfbhjd/202608/t20260817_1965051.html"]
UNCONNECTED = {
    "consensus_estimates": "No licensed stable consensus feed; research title counts are not estimates",
    "memory_contract_HBM": "Public spot quotes do not cover licensed contracts, HBM price or supply",
    "inventory": "No operational point-in-time inventory feed; production is not inventory",
    "optical_800G_1600G": "Annual disclosures are available, but shipment/price/Capex time series are not connected",
    "pcb_material_prices": "Issuer total revenue is not CCL, copper foil or glass cloth price",
    "mlcc_utilization_lead_time": "Company disclosures are not continuous channel inventory/utilization data",
    "probe_HBM_orders": "Issuer monthly revenue is not probe-card orders or HBM test demand",
    "overseas_IR": "Samsung, SK hynix, Japanese suppliers and cloud Capex IR adapters not connected",
    "macro_vintages": "Only retained NBS publication bodies; original first-release vintage and FX/rate feeds incomplete",
    "historic_lead_time": "Cold-start series have no original first-seen history",
}


def fetch(root, source, url, session):
    response = session.get(url.replace("http://", "https://"), timeout=(5, 20))
    response.raise_for_status()
    if len(response.content) > 20_000_000:
        raise ValueError("SOURCE_BODY_TOO_LARGE")
    seen = datetime.now(SHANGHAI).isoformat()
    is_pdf = response.content.startswith(b"%PDF")
    text = pdf_text(response.content) if is_pdf else response.content.decode(response.encoding if response.encoding and response.encoding.lower() != "iso-8859-1" else "utf-8", errors="replace")
    raw_sha = hashlib.sha256(response.content).hexdigest()
    binary = root / "data/raw/opportunity_radar/bodies" / (raw_sha + (".pdf" if is_pdf else ".bin"))
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists():
        binary.write_bytes(response.content)
    receipt = archive_json(root, "body_receipts", {"url": url, "source": source, "retrieved_at": seen,
        "raw_path": binary.relative_to(root).as_posix(), "raw_sha256": raw_sha,
        "extracted_text": text if is_pdf else None})
    return text, {"source": source, "url": url, "source_path": receipt.relative_to(root).as_posix(),
                  "first_seen_at": seen, "provenance": {"sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                  "raw_sha256": raw_sha, "raw_path": binary.relative_to(root).as_posix(), "kind": "SOURCE_BODY"}}


def observation(base, category, entity, metric, value, published, facts=None, **extra):
    facts = {"observation_mode": "LIVE_OBSERVED", "revision_version": base["provenance"]["raw_sha256"],
             "update_frequency": "SOURCE_RELEASE", **(facts or {})}
    return {**base, "signal_type": category, "entity": entity, "metric": metric, "value": value,
            "published_at": published, "source_date": published[:10], "event_date": published[:10],
            "effective_date": published[:10], "facts": facts, **extra}


def parse_nbs(text, base):
    soup = BeautifulSoup(text, "html.parser")
    title_tag = soup.find("meta", attrs={"name": "ArticleTitle"})
    published_tag = soup.find("meta", attrs={"name": "PubDate"})
    if not published_tag or not title_tag:
        return []
    published = datetime.strptime(published_tag["content"], "%Y/%m/%d %H:%M").replace(tzinfo=SHANGHAI).isoformat()
    title = title_tag["content"]
    body = soup.select_one(".TRS_Editor") or soup
    rows = []
    if "流通领域" in title and "价格" in title:
        group = None
        for tr in body.select("tr"):
            cells = [re.sub(r"\s+", "", t.get_text()) for t in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) == 1 and "、" in cells[0]:
                group = cells[0].split("、", 1)[-1]
            if len(cells) != 5 or number(cells[2]) is None:
                continue
            rows.append(observation(base, "COMMODITY_PRICE", cells[0], "circulation_spot_price", number(cells[2]), published,
                {"category": "SPOT_SURVEY_PRICE", "instrument": cells[0], "period": title,
                 "reported_change_abs": number(cells[3]), "reported_change_pct": number(cells[4]),
                 "series_caveat": "Ten-day circulation survey price, not futures or contract settlement"},
                unit="CNY/"+cells[1], currency="CNY", theme=group, body_evidence=" | ".join(cells)))
    elif "产能利用率" in title:
        for tr in body.select("tr"):
            cells = [re.sub(r"\s+", "", t.get_text()) for t in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) >= 3 and number(cells[1]) is not None and not cells[0].isdigit():
                rows.append(observation(base, "CAPACITY_AND_UTILIZATION", cells[0], "capacity_utilization_rate", number(cells[1]), published,
                    {"period": title, "current": number(cells[1]), "reported_yoy_pp": number(cells[2])}, unit="percent", theme=cells[0], body_evidence=" | ".join(cells)))
    elif "能源生产" in title:
        body_text = re.sub(r"\s+", "", body.get_text())
        for m in re.finditer(r"((?:\d{1,2}[—－–\-至])?\d{1,2}月份?)，(?:规上工业)?(原煤|原油|天然气)(?:产量|生产)(\d+(?:\.\d+)?)(亿吨|万吨|亿立方米)", body_text):
            basis = "YTD" if re.search(r"[—－–\-至]", m[1]) else "MONTHLY"
            rows.append(observation(base, "SUPPLY_DEMAND", m[2], "production_"+basis.lower(), float(m[3]), published,
                {"period": title[:4]+"年"+m[1], "period_basis": basis, "metric": "production",
                 "series_caveat": "Monthly and cumulative series kept separate; comparable enterprise scope retained"},
                unit=m[4], theme=m[2], body_evidence=m[0]))
    elif any(w in title for w in ("居民消费价格", "工业生产者", "采购经理指数")):
        for p in body.find_all("p"):
            sentence = re.sub(r"\s+", "", p.get_text())
            if len(sentence) > 500:
                continue
            for label, pattern in [
                ("CPI_yoy", r"居民消费价格同比(上涨|下降)(\d+(?:\.\d+)?)%"),
                ("PPI_yoy", r"工业生产者出厂价格同比(上涨|下降)(\d+(?:\.\d+)?)%"),
                ("manufacturing_PMI", r"制造业采购经理指数[（(]PMI[）)]为()(\d+(?:\.\d+)?)%"),
            ]:
                m = re.search(pattern, sentence)
                if m:
                    rows.append(observation(base, "MACRO_LIQUIDITY_FX_RATES", label, label, float(m[2]) * (-1 if m[1] == "下降" else 1), published,
                        {"period": title, "revision_at": None, "series_caveat": "First retrieved release version; original first publication vintage not certified"},
                        unit="percent", body_evidence=sentence))
    return rows


def parse_dram(text, base):
    soup = BeautifulSoup(text, "html.parser")
    rows, label, published = [], None, None
    for table in soup.select("table"):
        if table.select("table"):
            continue
        content = table.get_text(" ", strip=True)
        if "Last Update:" in content:
            label = content.split("Last Update:")[0].strip()
            m = re.search(r"([A-Z][a-z]{2})\.(\d{1,2})\s+(\d{4})\s+(\d\d:\d\d)", content)
            published = datetime.strptime(" ".join(m.groups()), "%b %d %Y %H:%M").replace(tzinfo=SHANGHAI).isoformat() if m else None
            continue
        if not published or label not in {"DRAM Spot Price", "Flash Spot Price", "Module Spot Price", "Wafer Spot Price"}:
            continue
        for tr in table.select("tr"):
            cells = [t.get_text(" ", strip=True) for t in tr.find_all("td", recursive=False)]
            if len(cells) < 7 or number(cells[5]) is None:
                continue
            rows.append(observation(base, "COMMODITY_PRICE", cells[0], "memory_spot_session_average", number(cells[5]), published,
                {"category": "SPOT_QUOTE", "instrument": cells[0], "reported_change_pct": number(cells[6].replace("%", "")),
                 "series_caveat": "Public spot quote; not contract price or HBM price; no licensed history"},
                theme="存储", unit="USD/item", currency="USD", body_evidence=" | ".join(cells[:7])))
    return rows


def roc_date(value):
    value = re.sub(r"\D", "", str(value))
    return f"{int(value[:3])+1911:04d}-{value[3:5]}-{value[5:7]}"


def parse_sec(text, base):
    payload = json.loads(text)
    rows = []
    facts = payload.get("facts", {}).get("us-gaap", {})
    tags = {"revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"),
            "profit": ("NetIncomeLoss",), "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
            "inventory": ("InventoryNet",)}
    for metric, choices in tags.items():
        tag = next((key for key in choices if key in facts), None)
        if not tag:
            continue
        values = facts[tag].get("units", {}).get("USD", [])
        values = [r for r in values if r.get("filed") and r.get("end") and r.get("form") in {"10-Q", "10-K", "10-K/A", "10-Q/A"}]
        for item in sorted(values, key=lambda r: (r["filed"], r["end"]))[-20:]:
            duration = (datetime.fromisoformat(item["end"])-datetime.fromisoformat(item["start"])).days+1 if item.get("start") else None
            basis = "INSTANT" if duration is None else f"DURATION_{duration}_DAYS"
            rows.append(observation(base, "OVERSEAS_LEAD", payload["entityName"], metric+"_"+basis, number(item["val"]), item["filed"],
                {"event_type": "FILED_FINANCIAL_FACT", "market": "US", "period": item["end"], "period_start": item.get("start"),
                 "period_basis": basis, "accession": item.get("accn"), "xbrl_tag": tag, metric: number(item["val"]),
                 "observation_mode": "RETROSPECTIVE_SERIES", "history_status": "HISTORICAL_SERIES_WITHOUT_ORIGINAL_FIRST_SEEN",
                 "series_caveat": "Filing date precision only; no inference of first-release vintage or comparable duration"},
                stock_code=str(payload.get("cik")), stock_name=payload["entityName"], unit="USD", currency="USD"))
    return rows


def parse_monthly(text, base):
    rows = []
    for item in json.loads(text):
        code = str(item.get("公司代號") or item.get("公司代碼") or "")
        if code not in TAIWAN:
            continue
        published = roc_date(item["出表日期"])
        period = str(item["資料年月"])
        value = number(item.get("營業收入-當月營收"))
        if value is None:
            continue
        facts = {"market": "TW", "instrument": code, "period": period, "revenue": value,
                 "monthly_operation_data": item, "theme_mapping_basis": "ISSUER_WATCHLIST_NOT_VERIFIED_RELATION",
                 "series_caveat": "Company total monthly revenue in TWD thousand, not product revenue"}
        rows.append(observation(base, "OVERSEAS_LEAD", item["公司名稱"], "monthly_revenue", value, published, facts,
            stock_code=code+".TW", stock_name=item["公司名稱"], theme=TAIWAN[code], unit="TWD_thousand", currency="TWD"))
    return rows


def collect_enrichment(root, day, *, session=None, max_disclosures=50):
    session = session or requests.Session()
    session.headers.update({"User-Agent": "a-share-daily-review public-data-research https://github.com/lc931223-lc/a-share-daily-review"})
    rows, diagnostics, relations = [], [], []

    def collect(name, url, tier, parser):
        try:
            text, base = fetch(root, name, url, session)
            base["source_tier"] = tier
            parsed = parser(text, base)
            now = datetime.now(SHANGHAI)
            parsed = [r for r in parsed if stamp(r["published_at"]) <= now]
            rows.extend(parsed)
            diagnostics.append({"source": name, "url": url, "source_tier": tier,
                "status": "PARTIAL" if parsed else "UNAVAILABLE", "rows": len(parsed),
                "reason": "CONTINUITY_AND_HISTORICAL_VINTAGES_NOT_PROVEN" if parsed else "NO_PARSEABLE_AS_OF_FACTS",
                "impact": "Missing facts remain unavailable", "retry_status": "ATTEMPTED"})
            return text
        except Exception as exc:
            diagnostics.append({"source": name, "url": url, "source_tier": tier, "status": "UNAVAILABLE", "rows": 0,
                "reason": type(exc).__name__, "impact": "No observations imported", "retry_status": "ATTEMPTED"})
            return ""

    index = collect("NBS", REGISTRY["nbs"]["url"], 1, lambda t, b: [])
    soup = BeautifulSoup(index, "html.parser")
    links = [urljoin(REGISTRY["nbs"]["url"], a["href"]) for a in soup.select("a[href]")
             if any(w in a.get_text() for w in ("流通领域", "产能利用率", "能源生产情况", "居民消费价格", "工业生产者出厂", "采购经理指数运行"))]
    for url in list(dict.fromkeys(links + NBS_SEEDS))[:12]:
        collect("NBS", url, 1, parse_nbs)
    collect("DRAMeXchange", REGISTRY["dram"]["url"], 3, parse_dram)
    for key in ("twse", "tpex"):
        collect(key.upper(), REGISTRY[key]["url"], 2, parse_monthly)
    # Keep a real permission/network diagnostic; no media or synthetic XBRL fallback.
    collect("SEC", REGISTRY["sec"]["url"], 2, parse_sec)
    seed_path = root / "config/opportunity_radar_disclosures.json"
    seeds = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.exists() else []
    disclosures = {r["url"]: ("announcements", r) for r in seeds if r["published_at"][:10] <= str(day)}
    try:
        response = session.post(REGISTRY["cninfo"]["url"], data={"pageNum": 1, "pageSize": 30,
            "column": "szse", "tabName": "fulltext", "sortName": "time", "sortType": "desc",
            "seDate": f"{day-timedelta(days=2)}~{day}", "isHLtitle": "true"}, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
        archive_json(root, "disclosure_discovery", {"retrieved_at": datetime.now(SHANGHAI).isoformat(),
            "url": REGISTRY["cninfo"]["url"], "payload": payload})
        recent = payload.get("announcements") or []
        for r in recent:
            url = urljoin("https://static.cninfo.com.cn/", r["adjunctUrl"])
            published = datetime.fromtimestamp(r["announcementTime"] / 1000, SHANGHAI).date().isoformat()
            disclosures[url] = ("announcements", {"stock_code": r["secCode"], "stock_name": r["secName"],
                "published_at": published, "title": BeautifulSoup(r["announcementTitle"], "html.parser").get_text(),
                "source": "巨潮资讯", "category": "live_discovery", "url": url})
        diagnostics.append({"source": "CNINFO_DISCOVERY", "status": "PARTIAL" if recent else "UNAVAILABLE",
            "rows": len(recent), "reason": "BOUNDED_FIRST_PAGE_NOT_FULL_MARKET_COVERAGE", "impact": "Additional overnight discovery", "retry_status": "ATTEMPTED"})
    except Exception as exc:
        diagnostics.append({"source": "CNINFO_DISCOVERY", "status": "UNAVAILABLE", "rows": 0,
            "reason": type(exc).__name__, "impact": "Overnight discovery incomplete; archive reuse only", "retry_status": "ATTEMPTED"})
    for path in sorted((root / "data/market_packets").glob("????-??-??.json"), reverse=True)[:8]:
        packet = json.loads(path.read_text(encoding="utf-8"))
        if packet.get("meta", {}).get("trade_date", "") > day.isoformat():
            continue
        for section in ("announcements", "policies"):
            for item in packet.get(section, {}).get("records", []):
                if item.get("url") and item.get("published_at"):
                    disclosures.setdefault(item["url"], (section, item))
    # Prefer content-bearing event disclosures over legal opinions and meeting notices.
    seed_urls = {r["url"] for r in seeds}
    ordered = sorted(disclosures.items(), key=lambda pair: (pair[0] not in seed_urls,
        pair[1][1].get("category") in {"other", "risk_warning"}, -stamp(pair[1][1]["published_at"]).timestamp()))
    for url, (section, item) in ordered[:max_disclosures]:
        def parse(text, base, item=item, section=section):
            published = item["published_at"][:10]  # Date-only feed is not midnight publication proof.
            body = text if url.lower().endswith(".pdf") else BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
            if section == "policies":
                return [observation(base, "POLICY_AND_FISCAL", item.get("agency") or item["title"], "official_policy_body", None,
                    published, {"title": item["title"], "body_parsed": True}, title=item["title"], body_evidence=body[:1800])]
            events = extract_body(body)
            for event in events:
                if stamp(published).date() < datetime.now(SHANGHAI).date()-timedelta(days=7):
                    event["facts"].update(observation_mode="RETROSPECTIVE_SERIES",
                        history_status="RETROSPECTIVE_DOCUMENT_NOT_NEW_EVENT")
            parsed = [observation(base, e["signal_type"], item["stock_code"], e["metric"], None, published, e["facts"],
                stock_code=item["stock_code"], stock_name=item.get("stock_name"), theme=item.get("theme"), title=item["title"], body_evidence=e["body_evidence"]) for e in events]
            edge_base = {**base, "published_at": published, "source_date": published, "event_date": published}
            relations.extend(verified_body_relations(body, item.get("stock_name") or item["stock_code"], item["stock_code"], edge_base))
            return parsed
        collect(item.get("source") or item.get("agency") or "OfficialDisclosure", url, 1, parse)
    diagnostics.extend({"source": key, "status": "UNAVAILABLE", "rows": 0, "reason": reason,
                        "impact": "No substitute data or inferred confirmation", "retry_status": "NOT_CONNECTED"}
                       for key, reason in UNCONNECTED.items())
    return rows, diagnostics, relations
