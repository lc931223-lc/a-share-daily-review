"""Source taxonomy labels, never mainline eligibility or priority."""

TYPES = (
    "INDUSTRY",
    "CONCEPT",
    "EVENT",
    "STYLE_TAG",
    "OWNERSHIP_TAG",
    "FINANCING_TAG",
    "PERFORMANCE_TAG",
    "INDEX_TAG",
    "OTHER",
)


def classify_theme(row, industry_names=()):
    name = str(row.get("theme_name") or row.get("name") or "").strip()
    for labels, kind in (
        (
            (
                "基金重仓",
                "保险重仓",
                "社保重仓",
                "社保持仓",
                "QFII重仓",
                "信托重仓",
                "国家队持股",
                "机构重仓",
            ),
            "OWNERSHIP_TAG",
        ),
        (("融资融券", "转融券", "融券标的", "融资标的"), "FINANCING_TAG"),
        (
            ("业绩预增", "业绩预降", "业绩预减", "业绩预升", "业绩扭亏", "业绩预亏"),
            "PERFORMANCE_TAG",
        ),
        (("含H股", "含B股", "AH股", "A+H股"), "STYLE_TAG"),
    ):
        if any(label.casefold() in name.casefold() for label in labels):
            return kind
    if name in {"沪深300", "上证50", "中证500", "中证1000", "中证2000", "创业板50"}:
        return "INDEX_TAG"
    if row.get("theme_type") in TYPES:
        return row["theme_type"]
    category = str(row.get("source_category") or row.get("category") or "").lower()
    if (
        category in {"industry", "行业"}
        or name in industry_names
        or "industry" in str(row.get("source", ""))
    ):
        return "INDUSTRY"
    if category in {"event", "事件"}:
        return "EVENT"
    if (
        category in {"concept", "概念"}
        or "concept" in str(row.get("source", ""))
        or name in {"CPO", "机器人", "锂电池"}
    ):
        return "CONCEPT"
    return "OTHER"


def selection_types(full, selected):
    available = {kind: sum(r["theme_type"] == kind for r in full) for kind in TYPES}
    retained = {kind: sum(r["theme_type"] == kind for r in selected) for kind in TYPES}
    return {
        "type_filter_applied": False,
        "available_by_type": available,
        "retained_by_type": retained,
        "truncated_by_type": {kind: available[kind] - retained[kind] for kind in TYPES},
    }
