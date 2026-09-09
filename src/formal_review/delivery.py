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
    raw = formal.read_bytes() if formal.exists() else b""
    # Git may materialize the immutable JSON with CRLF on Windows. Accept only
    # exact bytes or the LF representation, never an unrelated content hash.
    formal_hashes = {hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
    ready = (
        formal.exists()
        and projection.get("source_sha256") in formal_hashes
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
        from src.formal_review.objective_inputs import build_inputs

        build_inputs(root, day)
        queue["chatgpt_review_input_path"] = f"data/chatgpt_review_inputs/{day}.json"
        queue["chatgpt_review_input_compact_path"] = f"data/chatgpt_review_inputs/{day}_compact.json"
        write(root / "data/formal_review_queue" / f"{day}.json", queue)
    return queue
