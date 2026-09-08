"""Derived delivery queue and legacy-shaped official projection, never new judgements."""

import hashlib
from src.auction.production import read, write


def official_projection(payload, digest):
    themes, stocks, checks = [], [], []
    role_names = {
        "LEADER": "leader",
        "CAPACITY": "capacity",
        "TREND_LEADER": "trend_core",
        "ELASTICITY": "sentiment_core",
        "CATCH_UP": "catch_up",
        "FOLLOWER": "follower",
    }
    for theme in payload.get("main_themes", []):
        drivers = [
            dict(e) | dict(
                code=f["factor_id"],
                name=f["factor_name"],
                evidence_level="ABCD"[e["tier"] - 1],
            )
            for f in theme["41_factors"]
            if f["status"] in {"CONFIRMED", "PARTIAL"}
            for e in f["evidence"]
        ]
        themes.append(
            dict(
                name=theme["theme_name"],
                scores=theme["scores"],
                stage=theme["lifecycle"]["current_state"],
                rank=theme["theme_rank"],
                drivers=drivers,
                risks=theme.get("uncertainties", []),
            )
        )
        for stock in theme.get("core_stocks", []):
            stocks.append(
                dict(
                    code=stock.get("code") or stock.get("ts_code") or stock.get("stock_code"),
                    name=stock.get("name") or stock.get("stock_name"),
                    theme=theme["theme_name"],
                    role=role_names.get(stock.get("role"), stock.get("role")),
                    drivers=drivers,
                )
            )
        for check in theme.get("next_day_validation", []):
            checks.append(
                dict(
                    entity_type="theme",
                    entity_key=theme["theme_name"],
                    description=check.get("validation_point", ""),
                )
                | check
            )
    checks.extend(payload.get("tomorrow_checks", []))
    return dict(
        date=payload["date"],
        data_kind="official",
        projection_of="formal_review.3",
        source_sha256=digest,
        market_regime=payload["market_regime"],
        main_themes=themes,
        stocks=stocks,
        tomorrow_checks=checks,
        final_judgement_owner="chatgpt",
        evidence=[],
        risk_events=payload.get("uncertainties", []),
    )


def publish_official(root, payload, digest):
    path = root / "data/official_reviews" / f"{payload['date']}.json"
    projected = official_projection(payload, digest)
    existing = read(path)
    if existing is not None and existing != projected:
        raise ValueError("existing official review is immutable; projection conflict")
    write(path, projected)
    update_queue(root, payload["date"])


def update_queue(root, day):
    formal = root / "data/formal_reviews" / f"{day}.json"
    official = root / "data/official_reviews" / f"{day}.json"
    support = root / "data/formal_review_support" / f"{day}.json"
    context = root / "data/review_context" / f"{day}.json"
    projection = read(official, {})
    ready = (
        formal.exists()
        and projection.get("source_sha256") == hashlib.sha256(formal.read_bytes()).hexdigest()
    )
    queue = dict(
        trade_date=str(day),
        objective_support_path=f"data/formal_review_support/{day}.json",
        review_context_path=f"data/review_context/{day}.json",
        status="FORMAL_REVIEW_READY" if ready else "WAITING_FOR_CHATGPT_REVIEW",
        official_review_required=True,
        official_review_path=f"data/official_reviews/{day}.json" if ready else None,
        validation_status="PASS" if ready else "PENDING",
    )
    write(root / "data/formal_review_queue" / f"{day}.json", queue)
    if support.exists() and context.exists():
        data, ctx = read(support), read(context)
        theme_rows = data.get("theme_support", [])
        inputs = dict(
            trade_date=str(day),
            data_role="OBJECTIVE_SUPPORT_ONLY",
            final_judgement_owner="chatgpt",
            market_environment=ctx.get("market_environment"),
            top_mainline_candidates=theme_rows,
            capital_preference=ctx.get("capital_preference"),
            inflection=ctx.get("inflection_candidates"),
            review_intelligence=ctx.get("market_cycle_and_style"),
            source_quality=data.get("data_quality"),
            catalysts=ctx.get("catalysts", []),
            risks=ctx.get("risks", []),
            missing_fields=[
                {
                    "theme": t["theme_name"],
                    "factors": [
                        f["factor_id"] for f in t["41_factors"] if f["status"] == "UNCONFIRMED"
                    ],
                }
                for t in theme_rows
            ],
            role_fields={
                "leaders": "LEADER",
                "zhongjun": "CAPACITY",
                "trend_core": "TREND_LEADER",
                "buzhang": "CATCH_UP",
                "sentiment_core": "ELASTICITY",
            },
            source_manifest=data.get("source_manifest"),
        )
        write(root / "data/chatgpt_review_inputs" / f"{day}_compact.json", inputs)
    return queue
