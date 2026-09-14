"""Bounded issuer discovery feeds extend the existing production collector."""
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.opportunity_radar.company_evidence import body_facts, evidence_mode, expectation_revision, parse_amd_expectations, PARSER
from src.opportunity_radar.contracts import SHANGHAI, stamp
from src.opportunity_radar.storage import archive_json


def discover_issuers(root, day, session):
    config = json.loads((root / "config/opportunity_radar_evidence_sources.json").read_text("utf-8"))
    items, diagnostics = [], []
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    for code, name, theme in config["issuers"]:
        try:
            # Reuse discovery only, never invent a new first_seen for old facts.
            cached = []
            for path in (root / "data/raw/opportunity_radar/issuer_discovery").glob("*.json"):
                record = json.loads(path.read_text("utf-8"))
                if record.get("query_version") == 2 and record.get("stock_code") == code and 0 <= (day-stamp(record["retrieved_at"]).date()).days <= 7:
                    cached.append(record)
            if cached:
                payload = max(cached, key=lambda r: r["retrieved_at"])["payload"]
            else:
                response = session.post(url, data={"pageNum": 1, "pageSize": 100,
                    "column": "sse" if code.startswith("6") else "szse", "tabName": "fulltext",
                    "searchkey": name, "category": "category_bndbg_szse;", "sortName": "time", "sortType": "desc",
                    "seDate": f"{day.year}-01-01~{day}", "isHLtitle": "false"}, timeout=(5, 15))
                response.raise_for_status()
                payload = response.json()
                archive_json(root, "issuer_discovery", {"stock_code": code, "query_version": 2, "retrieved_at": datetime.now(SHANGHAI).isoformat(),
                    "url": url, "payload": payload})
            found = []
            forecasts = []
            for row in payload.get("announcements") or []:
                title = BeautifulSoup(row["announcementTitle"], "html.parser").get_text()
                is_report = re.search(r"20\d{2}\s*年半年度报告(?:全文)?(?:[（(]修订[版稿]?[）)])?$", title)
                is_forecast = re.search(r"20\d{2}\s*年半年度业绩预告", title)
                if row["secCode"] != code or not (is_report or is_forecast):
                    continue
                (found if is_report else forecasts).append({"stock_code": code, "stock_name": name, "theme": theme, "source": "巨潮资讯",
                    "title": title, "published_at": datetime.fromtimestamp(row["announcementTime"]/1000, SHANGHAI).date().isoformat(),
                    "url": urljoin("https://static.cninfo.com.cn/", row["adjunctUrl"]), "category": "earnings"})
            items.extend(found[:1])
            items.extend(forecasts[:1])
            diagnostics.append({"source": "CNINFO_ISSUER_DISCOVERY", "stock_code": code,
                "status": "PARTIAL" if found else "UNAVAILABLE", "rows": len(found[:1])+len(forecasts[:1]),
                "reason": "BOUNDED_H1_DISCOVERY_NOT_ALL_DISCLOSURES", "retry_status": "CACHED" if cached else "ATTEMPTED"})
        except Exception as exc:
            diagnostics.append({"source": "CNINFO_ISSUER_DISCOVERY", "stock_code": code, "status": "UNAVAILABLE",
                "rows": 0, "reason": type(exc).__name__, "retry_status": "ATTEMPTED"})
    return items, diagnostics


def paired_expectation_rows(expectations):
    from src.opportunity_radar.enrichment import observation
    rows = []
    for latest in expectations:
        if latest["expectation_source_type"] != "LATEST_REPORTED_FACT":
            continue
        eligible = [p for p in expectations if all(p.get(k) == latest.get(k) for k in ("period", "stock_code", "expectation_metric", "unit", "basis"))
                    and p["expectation_source_type"] == "COMPANY_PRIOR_GUIDANCE" and stamp(p["published_at"]) < stamp(latest["published_at"])]
        if not eligible:
            continue
        prior = max(eligible, key=lambda p: stamp(p["published_at"]))
        facts = expectation_revision(prior, latest)
        seen = max(prior["first_seen_at"], latest["first_seen_at"])
        mode = evidence_mode(latest["published_at"], seen)
        facts.update(body_parsed=True, parser_version=PARSER, observation_mode=mode, historical_backfill=mode == "HISTORICAL_BACKFILL")
        base = {k: latest[k] for k in ("source", "source_tier", "url", "source_path", "provenance")}
        base["first_seen_at"] = seen
        rows.append(observation(base, "EXPECTATION_REVISION", latest["stock_name"], latest["expectation_metric"]+":"+latest["period"],
            None, latest["published_at"], facts, stock_code=latest["stock_code"], stock_name=latest["stock_name"], theme=latest["theme"],
            body_evidence=latest["body_evidence"], unit=latest["unit"]))
    return rows


def collect_official_releases(root, day, session):
    from src.opportunity_radar.enrichment import fetch, observation
    config = json.loads((root / "config/opportunity_radar_evidence_sources.json").read_text("utf-8"))
    items = list(config["official_releases"])
    rows, diagnostics, edges, expectations = [], [], [], []
    for feed in config["discovery_feeds"]:
        try:
            html, _ = fetch(root, feed["source"], feed["url"], session)
            soup = BeautifulSoup(html, "html.parser")
            urls = list(dict.fromkeys(urljoin(feed["url"], a["href"]) for a in soup.select("a[href]")
                                      if "/press-releases/detail/" in a["href"]))[:8]
            items.extend({**feed, "url": url, "published_at": None} for url in urls)
            diagnostics.append({"source": feed["source"]+"_DISCOVERY", "rows": len(urls),
                "status": "PARTIAL" if urls else "UNAVAILABLE", "reason": "BOUNDED_OFFICIAL_FEED"})
        except Exception as exc:
            diagnostics.append({"source": feed["source"]+"_DISCOVERY", "rows": 0, "status": "UNAVAILABLE", "reason": type(exc).__name__})
    for item in {r["url"]: r for r in reversed(items)}.values():
        try:
            html, base = fetch(root, item["source"], item["url"], session)
            base["source_tier"] = 1
            soup = BeautifulSoup(html, "html.parser")
            for unwanted in soup.select("script, style, nav, header, footer"):
                unwanted.decompose()
            body = soup.get_text(" ", strip=True)
            published = item.get("published_at")
            if not published:
                date_node = soup.select_one("time[datetime], meta[property='article:published_time']")
                published = date_node.get("datetime") or date_node.get("content") if date_node else None
            if not published:
                match = re.search(r"Released\s+([A-Za-z]+ \d{1,2}, 20\d{2})", body)
                published = datetime.strptime(match[1], "%B %d, %Y").date().isoformat() if match else None
            if not published or stamp(published) > datetime.now(SHANGHAI):
                raise ValueError("PUBLICATION_TIME_UNAVAILABLE_OR_FUTURE")
            item = {**item, "published_at": published, "title": soup.title.get_text() if soup.title else item["source"]}
            events, relations = body_facts(body, item, base)
            for event in events:
                rows.append(observation(base, event["signal_type"], item["stock_name"], event["metric"], event["value"],
                    published, event["facts"], stock_code=item["stock_code"], stock_name=item["stock_name"], theme=event["theme"],
                    title=item["title"], body_evidence=event["body_evidence"]))
            edges.extend(relations)
            if item["source"] == "AMD_IR":
                expectations.extend(parse_amd_expectations(body, {**base, **{k: item[k] for k in ("stock_code", "stock_name", "theme", "published_at")}}))
            diagnostics.append({"source": item["source"], "url": item["url"], "status": "PARTIAL" if events else "UNAVAILABLE",
                "rows": len(events), "reason": "BODY_PARSED_WITH_ACTUAL_FIRST_SEEN", "retry_status": "ATTEMPTED"})
        except Exception as exc:
            diagnostics.append({"source": item["source"], "url": item["url"], "status": "UNAVAILABLE", "rows": 0,
                "reason": type(exc).__name__ + (":" + str(exc) if isinstance(exc, ValueError) else ""), "retry_status": "ATTEMPTED"})
    rows.extend(paired_expectation_rows(expectations))
    return rows, diagnostics, edges
