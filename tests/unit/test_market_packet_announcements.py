from src.market_packet.collector import _normalize_announcement


def test_announcement_normalization_sets_category_and_risk_flags():
    row = {
        "证券简称": "测试股份",
        "公告标题": "关于异常波动暨尚未形成订单的风险提示公告",
        "公告时间": "2026-09-02",
        "公告链接": "finalpage/2026-09-02/test.PDF",
    }
    item = _normalize_announcement(row, "000001", "平安银行")
    assert item["stock_code"] == "000001"
    assert item["source"] == "巨潮资讯"
    assert item["evidence_level"] == "A"
    assert item["category"] in {"order", "risk_warning", "clarification"}
    assert "尚未形成订单" in item["clarification_flags"]
    assert "风险提示" in item["risk_flags"]
    assert item["url"].startswith("http://static.cninfo.com.cn/")
