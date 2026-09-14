"""Dated body evidence, not headlines, establishes product stages and economics."""
import re
from datetime import timedelta

from src.opportunity_radar.contracts import number, stamp

PARSER = "COMPANY_EVIDENCE_V2"
PRODUCTS = {
    "AI芯片": "AI芯片 GPU ASIC 存算一体".split(),
    "存储": "HBM DRAM NAND 存储控制器 存储芯片".split(),
    "光通信": "CPO NPO 800G 1.6T 3.2T 光模块 光芯片 激光器 DSP 硅光 高速铜连接 光器件 光纤连接".split(),
    "PCB/CCL": "PCB CCL HDI 印制电路板 覆铜板 玻纤布 铜箔 树脂".split(),
    "MLCC": "MLCC 陶瓷粉体 电极材料 电感 电容".split(),
    "探针/测试": "探针卡 半导体测试设备 测试机 分选机 socket interface_board 探针台".split(),
    "先进封装": "先进封装 CoWoS Chiplet ABF 封装基板 underfill TGV TSV hybrid_bonding".split(),
    "数据中心电力": "液冷 高功率电源 数据中心供配电".split(),
}
RELATION_TYPES = {"upstream_supplier", "core_producer", "equipment_supplier", "material_supplier",
                  "customer", "downstream_application", "substitute", "competitor"}
REVISION_METRICS = {x + "_revision" for x in (
    "earnings", "revenue", "gross_margin", "order", "shipment", "capacity", "price", "utilization", "capex", "customer")}
NEGATIVE = re.compile(r"尚未|未形成|未量产|未实现|未认证|未通过|不涉及|不存在|not yet|\bno\b", re.I)
PROSPECTIVE = re.compile(r"预计|计划|规划|拟|有望|未来|将|\b(?:expect\w*|will|would|could|plan\w*|target\w*)\b", re.I)


def sentences(body):
    # Do not split decimal points or drop adversative clauses within a sentence.
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", body)
    for sentence in re.split(r"[。！？]|(?<=[a-zA-Z])\.(?=\s+[A-Z])", text):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if 8 <= len(sentence) <= 1800:
            yield sentence


def product_matches(text):
    for theme, products in PRODUCTS.items():
        for product in products:
            literal = product.replace("_", " ")
            pattern = re.escape(literal)
            if literal.isascii():
                pattern = r"(?<![a-zA-Z])" + pattern + r"(?![a-zA-Z])"
            match = re.search(pattern, text, re.I)
            if match:
                yield theme, product, match


def technology_stage(statement):
    if NEGATIVE.search(statement) or PROSPECTIVE.search(statement):
        return "RESEARCH" if re.search(r"仍在研发|正在研发|研发中|research|under development", statement, re.I) else None
    stages = (
        ("RAPID_PENETRATION", r"渗透率.{0,12}(?:提升至|达到)\s*\d+(?:\.\d+)?%"),
        ("MASS_PRODUCTION", r"已(?:实现|进入)?(?:规模化)?量产|实现(?:规模化)?量产|(?<!小)批量出货|\b(?:now in|in full|volume|mass) production\b"),
        ("SMALL_SCALE_PRODUCTION", r"已.{0,8}小批量|small[- ](?:scale|batch) production"),
        ("CUSTOMER_VALIDATION", r"客户(?:验证|认证)|customer (?:validation|qualification)"),
        ("ENGINEERING_SAMPLE", r"已.{0,8}(?:送样|样片)|engineering samples?|sampling"),
        ("RESEARCH", r"研发|研究|research|development"),
    )
    return next((stage for stage, pattern in stages if re.search(pattern, statement, re.I)), None)


def evidence_mode(published, seen):
    return "HISTORICAL_BACKFILL" if stamp(published).date() < stamp(seen).date()-timedelta(days=7) else "LIVE_OBSERVED"


def body_facts(body, item, base):
    """All products need their own local predicate; no other-product stage transfer."""
    events, relations = [], []
    mode = evidence_mode(item["published_at"], base["first_seen_at"])
    common = {"body_parsed": True, "parser_version": PARSER, "observation_mode": mode,
              "historical_backfill": mode == "HISTORICAL_BACKFILL"}
    for statement in sentences(body):
        own = bool(re.search(r"(?:本公司|公司|本集团).{0,50}(?:主要|从事|产品|业务|研发|生产|实现|推进|销售|提供)", statement))
        own = own or (item.get("source") in {"AMD_IR", "NVIDIA_NEWSROOM"}
                      and re.search(r"\b(?:AMD|NVIDIA|our|we)\b", statement, re.I) is not None)
        for theme, product, match in product_matches(statement):
            # A comma/semicolon-delimited predicate must refer to this product.
            clause = re.split(r"[，；;]", statement[match.start():])[0][:160]
            stage = technology_stage(clause) if own else None
            if len(statement) > 600 and item.get("source") not in {"AMD_IR", "NVIDIA_NEWSROOM"}:
                stage = None
            if stage == "RESEARCH" and (len(statement) > 600 or re.search(r"风险|释义|主要业务|主营业务", statement)
                or not re.search(r"在研|研发进展|研发项目|产品预研|技术研发|正在研发|成功研发|研发成功|完成研发|research milestone|prototype", statement, re.I)):
                stage = None
            if product in {"800G", "1.6T", "3.2T"} and item.get("theme") == "PCB/CCL":
                theme = "PCB/CCL"
            if stage in {"MASS_PRODUCTION", "RAPID_PENETRATION"} and (NEGATIVE.search(statement) or PROSPECTIVE.search(statement)):
                stage = None
            if stage:
                events.append({"signal_type": "TECHNOLOGY_BREAKTHROUGH", "metric": "technology_stage:" + product,
                    "theme": theme, "value": None, "body_evidence": statement,
                    "facts": {**common, "technology": product, "technology_name": product,
                        "technology_category": theme, "company": item["stock_name"], "current_stage": stage,
                        "technology_stage": stage, "commercialization_stage": stage,
                        "milestone_type": "DISCLOSED_STAGE_NOT_ASSUMED_BREAKTHROUGH", "affected_industries": [theme],
                        "affected_products": [product], "possible_beneficiaries": [],
                        "beneficiary_status": "REQUIRES_SEPARATE_ECONOMIC_RELATION", "quantitative_improvement": None}})
            # Restrict VERIFICATION to issuer activity, never broad market outlook.
            relation = bool(re.search(r"(?:公司|集团).{0,32}(?:主要从事|主营|专业从事|生产的|主要产品|业务包括|产品包括)", statement)
                            or re.search(r"公司.{0,20}" + re.escape(product) + r".{0,45}(?:销售|收入|交付|生产)", statement))
            if relation and not NEGATIVE.search(statement) and not PROSPECTIVE.search(statement):
                kind = "equipment_supplier" if theme == "探针/测试" else "material_supplier" if product in {"覆铜板", "铜箔", "树脂", "玻纤布", "陶瓷粉体", "underfill"} else "core_producer"
                relations.append({**base, "published_at": item["published_at"], "source_date": item["published_at"][:10],
                    "event_date": item["published_at"][:10], "from": product, "to": item["stock_name"],
                    "stock_code": item["stock_code"], "stock_name": item["stock_name"], "company_name": item["stock_name"],
                    "upstream_theme": theme, "downstream_theme": theme, "relationship_type": kind,
                    "product": product, "revenue_exposure": None, "profit_exposure": None, "customer_exposure": None,
                    "capacity_exposure": None, "evidence": statement, "evidence_date": item["published_at"][:10],
                    "confidence": 1.0, "relation_status": "VERIFIED", "verification_basis": "ISSUER_OWN_PRODUCT_BODY",
                    "observation_mode": mode, "parser_version": PARSER})
        if own and not PROSPECTIVE.search(statement) and re.search(r"竞争加剧|价格竞争|价格战|市场份额.{0,12}(?:下降|提升)|market share (?:gains|declin)", statement, re.I):
            events.append({"signal_type": "INDUSTRY_COMPETITION", "metric": "competition_body", "theme": item.get("theme"),
                "value": None, "body_evidence": statement, "facts": {**common, "industry": item.get("theme"),
                    "event": "ISSUER_COMPETITION_DISCLOSURE", "risk_flag": bool(re.search(r"加剧|价格战|下降|declin", statement, re.I))}})
    # Explicit headline table only. YoY is a fundamental comparison, NOT surprise.
    # Search the financial table, not the earlier table of contents mentioning it.
    head = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", body[:40000])
    for metric, label in (("revenue", r"营业收入"), ("earnings", r"归属于上市公司股东的净利润")):
        m = re.search(label + r"\s*[（(]元[）)]\s*([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+(-?\d+(?:\.\d+)?)%", head)
        if m:
            current, prior = (float(m[i].replace(",", "")) for i in (1, 2))
            events.append({"signal_type": "REVENUE_PROFIT_MARGIN", "metric": "reported_" + metric,
                "theme": item.get("theme"), "value": current, "body_evidence": m[0],
                "facts": {**common, "financial_metric": metric, "current_value": current, "prior_value": prior,
                    "fundamental_change_pct": 100*(current-prior)/abs(prior) if prior else None,
                    "comparison_basis": "REPORTED_YOY_NOT_EXPECTATION_REVISION", "financial_scope": "CONSOLIDATED_REPORTED_TABLE",
                    "period_basis": "H1" if "半年度报告" in item.get("title", "") else "SOURCE_REPORT_PERIOD"}})
    unique = {(e["signal_type"], e["metric"], e["body_evidence"]): e for e in events}
    return list(unique.values())[:100], relations


def expectation_revision(prior, latest):
    """Same issuer/period/unit/basis; both numeric sides require body provenance."""
    if latest.get("expectation_metric") not in REVISION_METRICS:
        raise ValueError("UNKNOWN_EXPECTATION_METRIC")
    for key in ("stock_code", "expectation_metric", "period", "unit", "basis"):
        if not prior.get(key) or prior.get(key) != latest.get(key):
            raise ValueError("EXPECTATION_COMPARISON_MISMATCH:" + key)
    if prior.get("expectation_source_type") not in {"COMPANY_PRIOR_GUIDANCE", "PUBLIC_CONSENSUS", "PUBLIC_FORECAST"}:
        raise ValueError("PRIOR_EXPECTATION_REQUIRED_NOT_YOY")
    for row in (prior, latest):
        if not row.get("body_evidence") or not row.get("provenance", {}).get("sha256") or not row.get("url"):
            raise ValueError("EXPECTATION_BODY_PROVENANCE_REQUIRED")
        if not stamp(row.get("published_at")) or not stamp(row.get("first_seen_at")):
            raise ValueError("EXPECTATION_TIMESTAMPS_REQUIRED")
    if stamp(prior["published_at"]) >= stamp(latest["published_at"]):
        raise ValueError("PRIOR_EXPECTATION_MUST_PRECEDE_LATEST")
    a, b = number(prior.get("value")), number(latest.get("value"))
    if a is None or b is None:
        raise ValueError("EXPECTATION_NUMERIC_PAIR_REQUIRED")
    return {"expectation_metric": latest["expectation_metric"], "prior_expectation": a, "latest_expectation": b,
        "guidance_low": prior.get("guidance_low"), "guidance_high": prior.get("guidance_high"),
        "guidance_comparison_basis": "DISCLOSED_RANGE_MIDPOINT" if prior.get("guidance_low") is not None else "DISCLOSED_POINT_ESTIMATE",
        "outside_guidance_range": (b < prior["guidance_low"] or b > prior["guidance_high"]) if prior.get("guidance_low") is not None else None,
        "revision_abs": b-a, "revision_pct": 100*(b-a)/abs(a) if a else None,
        "revision_direction": "UP" if b > a else "DOWN" if b < a else "UNCHANGED",
        "expectation_source_type": prior["expectation_source_type"], "latest_source_type": latest["expectation_source_type"],
        "period": latest["period"], "unit": latest["unit"], "basis": latest["basis"],
        "prior_evidence": {k: prior[k] for k in ("published_at", "first_seen_at", "url", "source_path", "provenance", "body_evidence")},
        "latest_evidence": {k: latest[k] for k in ("published_at", "first_seen_at", "url", "source_path", "provenance", "body_evidence")},
        "comparison_semantics": "SOURCE_GUIDANCE_NOT_ASSUMED_MARKET_CONSENSUS"}


def parse_amd_expectations(body, base):
    rows = []
    # Keep reported GAAP revenue and non-GAAP margin on separate accounting bases.
    for m in re.finditer(r"For the (first|second|third|fourth) quarter of (20\d{2}), AMD expects revenue to be approximately \$(\d+(?:\.\d+)?) billion[^.]*\.", body, re.I):
        rows.append({**base, "period": m[2]+"Q"+str(["first", "second", "third", "fourth"].index(m[1].lower())+1),
            "expectation_metric": "revenue_revision", "value": float(m[3])*1000, "unit": "USD_million",
            "basis": "CONSOLIDATED_REVENUE", "expectation_source_type": "COMPANY_PRIOR_GUIDANCE", "body_evidence": m[0]})
    report = re.search(r"financial results for the (first|second|third|fourth) quarter of (20\d{2})", body, re.I)
    if report:
        table = re.search(r"Revenue\s*\(\$M\)\s*\$([\d,]+)", body)
        if table:
            rows.append({**base, "period": report[2]+"Q"+str(["first", "second", "third", "fourth"].index(report[1].lower())+1),
                "expectation_metric": "revenue_revision", "value": float(table[1].replace(",", "")), "unit": "USD_million",
                "basis": "CONSOLIDATED_REVENUE", "expectation_source_type": "LATEST_REPORTED_FACT", "body_evidence": table[0]})
    return rows


def issuer_expectations(body, item, base, events):
    """Mainland reported H1 attributable profit versus an issuer H1 forecast."""
    title = re.sub(r"\s+", "", item.get("title", ""))
    period = re.search(r"(20\d{2})年半年度", title)
    if not period:
        return []
    common = {**base, "stock_code": item["stock_code"], "stock_name": item["stock_name"], "theme": item.get("theme"),
        "period": period[1]+"H1", "unit": "CNY", "basis": "NET_PROFIT_ATTRIBUTABLE_PARENT", "expectation_metric": "earnings_revision",
        "published_at": item["published_at"]}
    if "业绩预告" not in title:
        return [{**common, "value": event["value"], "expectation_source_type": "LATEST_REPORTED_FACT", "body_evidence": event["body_evidence"]}
                for event in events if event["metric"] == "reported_earnings"]
    text = re.sub(r"\s+", "", body)
    label = r"(?:归属于(?:上市公司股东|母公司(?:所有者)?)(?:的)?净利润|归母净利润)"
    amount = r"(-?[\d,]+(?:\.\d+)?)"
    pattern = label + r"[^。]{0,35}?(?:盈利[：:]|为|达到|约为)?" + amount + r"(亿元|万元|元)?(?:至|到|[-~～—])" + amount + r"(亿元|万元|元)"
    m = re.search(pattern, text)
    if not m or re.search(r"亏损|扣除非经常性|同比|增加|增长|减少|上年|同期|差额|变动", m[0]):
        return []
    unit_a, unit_b = m[2] or m[4], m[4]
    low = float(m[1].replace(",", ""))*{"元": 1, "万元": 1e4, "亿元": 1e8}[unit_a]
    high = float(m[3].replace(",", ""))*{"元": 1, "万元": 1e4, "亿元": 1e8}[unit_b]
    if low > high:
        return []
    return [{**common, "value": (low+high)/2, "guidance_low": low, "guidance_high": high,
             "expectation_source_type": "COMPANY_PRIOR_GUIDANCE", "body_evidence": m[0]}]


def valid_relation(edge):
    if edge.get("parser_version") == "COMPANY_EVIDENCE_V1":
        return False
    if edge.get("relation_status", "VERIFIED") != "VERIFIED":
        return False
    if edge.get("relationship_type") in RELATION_TYPES and edge.get("verification_basis") != "ISSUER_OWN_PRODUCT_BODY":
        return False
    return bool(edge.get("evidence") and edge.get("source_tier") in (1, 2) and edge.get("provenance", {}).get("sha256"))
