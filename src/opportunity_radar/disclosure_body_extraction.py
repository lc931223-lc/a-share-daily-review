"""Conservative sentence-level facts. No title-derived commercial confirmation."""
import re
from io import BytesIO

from pypdf import PdfReader

NEGATION = re.compile(r"尚未|尚处|未形成|未量产|未实现|未签|未获|尚存在不确定|不以任何方式|承诺|预计|拟|有望|可能|不排除|暂无|未与|不涉及|计划|意向|框架|如果|一旦|若|将|not yet|may |expect|plan to", re.I)
AMOUNT = re.compile(r"(?:合同(?:总)?金额|合同总价|订单金额)[为是：:\s]*[人民币\s]*([\d,]+(?:\.\d+)?)\s*(亿元|万元|元)")


def pdf_text(data):
    reader = PdfReader(BytesIO(data))
    return "\n".join(p.extract_text() or "" for p in reader.pages[:200])


def extract_body(text):
    events = []
    # Keep a complete sentence: adversative/negative clauses cannot be discarded.
    sentences = [re.sub(r"\s+", "", s) for s in re.split(r"[。！？]", text)]
    for sentence in sentences:
        if len(sentence) < 8:
            continue
        negative = bool(NEGATION.search(sentence))
        facts = {"body_parsed": True, "parser_version": "DISCLOSURE_BODY_V21_3", "negation_detected": negative}
        category = stage = None
        if any(w in sentence for w in ("订单", "合同", "客户验证", "客户认证")):
            category = "CUSTOMER_AND_ORDER"
            if "框架" in sentence or "意向" in sentence:
                stage = "FRAMEWORK_AGREEMENT"
            elif "验证" in sentence or "认证" in sentence:
                stage = "CUSTOMER_VALIDATION"
            elif (not negative and AMOUNT.search(sentence) and "公司" in sentence
                  and any(w in sentence for w in ("已签订", "已签署", "收到订单"))
                  and not any(w in sentence for w in ("质押", "担保", "融资", "借款", "股权", "法律意见", "销售模式", "采购模式"))):
                stage = "ORDER_CONFIRMED"
            match = AMOUNT.search(sentence)
            if match:
                facts["contract_amount"] = float(match[1].replace(",", "")) * {"亿元": 1e8, "万元": 1e4, "元": 1}[match[2]]
                facts["currency"] = "CNY"
            ratio = re.search(r"占[^。]{0,35}营业收入[^\d]{0,10}(\d+(?:\.\d+)?)%", sentence)
            facts["ratio_vs_last_year_revenue"] = float(ratio[1]) if ratio else None
            facts["certainty"] = "PROSPECTIVE_OR_NEGATED" if negative else "BODY_STATEMENT"
            duration = re.search(r"(?:履行期限|合同期限|执行期限)[为：:]*([^，；]{2,45})", sentence)
            customer = re.search(r"(?:客户名称|买方|采购方)[为：:]+([^，；]{2,40})", sentence)
            facts["duration"] = duration[1] if duration else None
            facts["customer"] = customer[1] if customer else None
        elif any(w in sentence for w in ("量产", "小批量", "商业化", "研发")):
            category = "PRODUCT_COMMERCIALIZATION"
            stage = "MASS_PRODUCTION" if any(w in sentence for w in ("已实现量产", "已量产", "已进入量产")) and not negative else "SMALL_BATCH" if "已实现小批量" in sentence and not negative else None
            facts["current_stage"] = stage
        elif any(w in sentence for w in ("投产", "产能", "试生产")):
            category = "CAPACITY_AND_UTILIZATION"
            stage = "PRODUCTION_STARTED" if "已投产" in sentence and not negative else None
        elif any(w in sentence for w in ("营业收入", "净利润", "毛利率", "现金流", "销售额")):
            category = "REVENUE_PROFIT_MARGIN"
            for key, label in (("revenue", "营业收入"), ("profit", "净利润"), ("cash_flow", "经营活动产生的现金流量净额")):
                m = re.search(label + r"(?:为|达到|实现)?([\d,]+(?:\.\d+)?)(亿元|万元|元)", sentence)
                if m and not negative:
                    facts[key] = float(m[1].replace(",", "")) * {"亿元": 1e8, "万元": 1e4, "元": 1}[m[2]]
                    facts["financial_basis"] = "SENTENCE_SCOPE_NOT_ASSUMED_CONSOLIDATED"
        elif any(w in sentence for w in ("回购", "增持", "减持")):
            category = "SHAREHOLDER_MANAGEMENT_ACTION"
            if not negative:
                if re.search(r"(?:累计|已)减持.{0,25}[\d,]+(?:万|亿)?股", sentence):
                    facts["action"] = "DECREASE_HOLDING"
                elif re.search(r"(?:累计|已)增持.{0,25}[\d,]+(?:万|亿)?股", sentence):
                    facts["action"] = "INCREASE_HOLDING"
                elif "回购注销" not in sentence and re.search(r"累计.{0,70}回购.{0,25}[\d,]+(?:万|亿)?股", sentence):
                    facts["action"] = "BUYBACK"
        elif any(w in sentence for w in ("收购", "重组", "资产注入")):
            category = "M&A_AND_CAPITAL_OPERATION"
            facts["uncertainty_flags"] = ["PROSPECTIVE"] if negative else []
        if category:
            if stage and category != "PRODUCT_COMMERCIALIZATION":
                facts["event_type"] = stage
            events.append({"signal_type": category, "facts": facts, "body_evidence": sentence[:1800],
                           "metric": "body_fact"})
    return events[:80]


def verified_body_relations(text, company, code, base):
    """Explicit own-product statements only; no concept-membership inference."""
    result = []
    products = ("探针卡", "MLCC", "覆铜板", "光模块", "存储芯片", "印制电路板")
    for sentence in re.split(r"[。！？]", text):
        s = re.sub(r"\s+", "", sentence)
        if NEGATION.search(s) or not (re.search(r"(?:本公司|公司|本集团).{0,24}(?:主要从事|主营|专业从事|生产的)", s)
            or re.search(r"公司(?:MLCC|光模块|探针卡|覆铜板)产品.{0,100}(?:销售量|销售额|实现销售|交付)", s)):
            continue
        for product in products:
            if product in s and base["source_tier"] < 4:
                result.append({**base, "from": company, "to": product, "company_name": company,
                               "stock_code": code, "relationship_type": "PRODUCER",
                               "transmission_depth": 1, "evidence": s[:1800], "confidence": 1.0,
                               "revenue_exposure": None, "cost_exposure": None})
    return result
