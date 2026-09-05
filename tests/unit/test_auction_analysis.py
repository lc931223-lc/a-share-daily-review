from src.auction.analysis import anomaly_labels, build_objective_analysis


def test_anomaly_labels_cover_four_initial_objective_patterns():
    assert "EXTREME_VOLUME_ANOMALY" in anomaly_labels({
        "auction_volume_anomaly_score": 18, "auction_amount_ratio_20d": 4, "auction_gap_pct": 0.5,
    })
    assert "STRONG_VOLUME_CONFIRMATION" in anomaly_labels({
        "auction_volume_anomaly_score": 14, "auction_amount_ratio_20d": 2, "auction_gap_pct": 1.5,
    })
    assert anomaly_labels({
        "auction_volume_anomaly_score": 5, "auction_amount_ratio_20d": 0.8, "auction_gap_pct": 3,
    }) == ["PRICE_STRONG_VOLUME_WEAK"]
    assert "PRICE_WEAK_VOLUME_STRONG" in anomaly_labels({
        "auction_volume_anomaly_score": 15, "auction_amount_ratio_20d": 2, "auction_gap_pct": -1,
    })


def test_objective_analysis_does_not_infer_transitions_without_official_review():
    watchlist = {"stocks": [{"ts_code": "000001.SZ", "themes": ["银行"]}]}
    summaries = [{
        "ts_code": "000001.SZ", "stock_name": "平安银行", "auction_price": 10,
        "auction_gap_pct": 1, "auction_amount": 1000, "auction_amount_ratio_20d": 2,
        "auction_volume_anomaly_score": 14, "anomaly_labels": ["STRONG_VOLUME_CONFIRMATION"],
    }]

    result = build_objective_analysis(watchlist, summaries, {})

    assert result["previous_mainline_validation"]["status"] == "UNAVAILABLE"
    assert result["transition_status"] == "UNAVAILABLE"
    assert result["weak_to_strong_candidates"] == []
    assert result["strong_to_weak_candidates"] == []
    assert result["sector_auction_ranking"][0]["name"] == "银行"


def test_transition_candidates_accept_chinese_official_review_roles():
    watchlist = {"stocks": [
        {"ts_code": "000001.SZ", "themes": ["测试"]},
        {"ts_code": "000002.SZ", "themes": ["测试"]},
    ]}
    summaries = [
        {
            "ts_code": "000001.SZ", "stock_name": "A", "auction_price": 10,
            "auction_gap_pct": 2, "auction_amount": 1000, "auction_amount_ratio_20d": 2,
            "auction_volume_anomaly_score": 14, "anomaly_labels": ["STRONG_VOLUME_CONFIRMATION"],
        },
        {
            "ts_code": "000002.SZ", "stock_name": "B", "auction_price": 10,
            "auction_gap_pct": -1, "auction_amount": 1000, "auction_amount_ratio_20d": 2,
            "auction_volume_anomaly_score": 14, "anomaly_labels": ["PRICE_WEAK_VOLUME_STRONG"],
        },
    ]
    review = {"stocks": [
        {"code": "000001", "role": "补涨"},
        {"code": "000002", "role": "中军"},
    ]}

    result = build_objective_analysis(watchlist, summaries, review)

    assert [item["ts_code"] for item in result["weak_to_strong_candidates"]] == ["000001.SZ"]
    assert [item["ts_code"] for item in result["strong_to_weak_candidates"]] == ["000002.SZ"]
