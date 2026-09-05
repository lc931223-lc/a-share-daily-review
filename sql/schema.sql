PRAGMA foreign_keys = ON;

CREATE TABLE review_import (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL,
    sha256 TEXT NOT NULL, archive_path TEXT NOT NULL, trade_date DATE,
    data_kind TEXT, status TEXT NOT NULL, error_json TEXT,
    created_at DATETIME NOT NULL, completed_at DATETIME
);
CREATE INDEX idx_review_import_sha256 ON review_import(sha256);

CREATE TABLE source_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL, dataset TEXT NOT NULL, trade_date DATE NOT NULL,
    fetched_at DATETIME NOT NULL, sha256 TEXT NOT NULL, archive_path TEXT NOT NULL,
    record_count INTEGER NOT NULL, status TEXT NOT NULL, error_category TEXT,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_source_batch_archive UNIQUE(sha256, archive_path)
);
CREATE INDEX idx_source_batch_source_date ON source_batch(source_name, trade_date);

CREATE TABLE source_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES source_batch(id),
    entity_type TEXT NOT NULL, entity_key TEXT NOT NULL, field_name TEXT NOT NULL,
    value_json TEXT NOT NULL, unit TEXT, selected BOOLEAN NOT NULL,
    selected_reason TEXT, conflict_status TEXT NOT NULL, created_at DATETIME NOT NULL
);
CREATE INDEX idx_source_observation_entity
    ON source_observation(entity_type, entity_key, field_name);

CREATE TABLE quality_gate_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL, rule_version TEXT NOT NULL, status TEXT NOT NULL,
    confidence INTEGER NOT NULL, summary_json TEXT NOT NULL, created_at DATETIME NOT NULL
);
CREATE INDEX idx_quality_gate_run_date ON quality_gate_run(trade_date, status);

CREATE TABLE quality_gate_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_run_id INTEGER NOT NULL REFERENCES quality_gate_run(id),
    check_name TEXT NOT NULL, actual_value TEXT NOT NULL, threshold_value TEXT NOT NULL,
    passed BOOLEAN NOT NULL, reason TEXT NOT NULL,
    CONSTRAINT uq_quality_gate_check_name UNIQUE(gate_run_id, check_name)
);

CREATE TABLE source_fallback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL, primary_source TEXT NOT NULL, fallback_source TEXT NOT NULL,
    dataset TEXT NOT NULL, reason TEXT NOT NULL, fields_json TEXT NOT NULL,
    fetched_at DATETIME NOT NULL, coverage REAL, cross_validation_status TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE analysis_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL, status TEXT NOT NULL, rule_version TEXT NOT NULL,
    data_version TEXT NOT NULL, confidence INTEGER NOT NULL,
    gate_run_id INTEGER REFERENCES quality_gate_run(id),
    result_json TEXT NOT NULL, created_at DATETIME NOT NULL,
    CONSTRAINT uq_analysis_snapshot_version UNIQUE(trade_date, data_version)
);
CREATE INDEX idx_analysis_snapshot_date_status ON analysis_snapshot(trade_date, status);

CREATE TABLE trading_day (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date DATE NOT NULL,
    data_kind TEXT NOT NULL, strict_mode BOOLEAN NOT NULL,
    completeness_score INTEGER NOT NULL, missing_items TEXT NOT NULL,
    market_regime TEXT NOT NULL, turnover REAL, turnover_delta REAL,
    advancers INTEGER, decliners INTEGER, limit_up_count INTEGER,
    limit_down_count INTEGER, max_board_height INTEGER,
    position_min INTEGER NOT NULL, position_max INTEGER NOT NULL,
    import_id INTEGER NOT NULL UNIQUE REFERENCES review_import(id),
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_trading_day_date_kind UNIQUE(trade_date, data_kind)
);
CREATE INDEX idx_trading_day_kind_date ON trading_day(data_kind, trade_date);

CREATE TABLE market_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    data_quality_status TEXT NOT NULL,
    data_quality_score INTEGER NOT NULL,
    turnover REAL,
    previous_turnover REAL,
    turnover_delta REAL,
    turnover_delta_pct REAL,
    rise_count INTEGER,
    fall_count INTEGER,
    flat_count INTEGER,
    limit_up_count INTEGER,
    limit_down_count INTEGER,
    failed_limit_count INTEGER,
    highest_board INTEGER,
    source_json TEXT NOT NULL,
    missing_data TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_market_daily_date UNIQUE(trade_date)
);

CREATE TABLE theme (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE, created_at DATETIME NOT NULL
);
CREATE TABLE theme_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL UNIQUE,
    theme_id INTEGER NOT NULL REFERENCES theme(id)
);
CREATE TABLE stock (
    stock_code TEXT PRIMARY KEY, stock_name TEXT NOT NULL,
    exchange TEXT NOT NULL, updated_at DATETIME NOT NULL
);

CREATE TABLE theme_daily_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    theme_id INTEGER NOT NULL REFERENCES theme(id), rank_no INTEGER NOT NULL,
    stage TEXT NOT NULL, change_status TEXT NOT NULL, causal_chain TEXT NOT NULL,
    base_logic_score INTEGER, realization_score INTEGER,
    expectation_gap_score INTEGER, persistence_score INTEGER,
    market_confirmation_score INTEGER, risk_penalty INTEGER,
    total_score INTEGER, rating TEXT, logic_quality INTEGER,
    market_strength INTEGER, risk_reward INTEGER,
    missing_reasons TEXT NOT NULL, delta_score INTEGER,
    delta_reason TEXT NOT NULL, created_at DATETIME NOT NULL,
    CONSTRAINT uq_theme_score_day_theme UNIQUE(trading_day_id, theme_id)
);
CREATE INDEX idx_theme_score_theme_day ON theme_daily_score(theme_id, trading_day_id);

CREATE TABLE theme_daily_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    theme_id INTEGER NOT NULL REFERENCES theme(id),
    rank_no INTEGER NOT NULL,
    base_logic_score INTEGER,
    realization_score INTEGER,
    expectation_gap_score INTEGER,
    persistence_score INTEGER,
    market_confirmation_score INTEGER,
    risk_penalty INTEGER,
    total_score INTEGER,
    rating TEXT,
    lifecycle TEXT NOT NULL,
    delta_score INTEGER,
    delta_reason TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_theme_review_day_theme UNIQUE(trading_day_id, theme_id)
);

CREATE TABLE theme_driver (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    theme_id INTEGER NOT NULL REFERENCES theme(id), driver_code INTEGER NOT NULL,
    driver_name TEXT NOT NULL, evidence_level TEXT NOT NULL,
    CONSTRAINT uq_theme_driver_day UNIQUE(trading_day_id, theme_id, driver_code)
);

CREATE TABLE stock_daily_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    stock_code TEXT NOT NULL REFERENCES stock(stock_code),
    theme_id INTEGER NOT NULL REFERENCES theme(id), role TEXT NOT NULL,
    role_detail TEXT, stage TEXT NOT NULL, catalyst TEXT NOT NULL,
    benefit_path TEXT NOT NULL, causal_chain TEXT NOT NULL,
    realization_score INTEGER, expectation_gap INTEGER, logic_quality INTEGER,
    market_strength INTEGER, risk_reward INTEGER, total_score INTEGER,
    rating TEXT, missing_reasons TEXT NOT NULL, delta_score INTEGER,
    delta_reason TEXT NOT NULL, created_at DATETIME NOT NULL,
    CONSTRAINT uq_stock_score_day_theme UNIQUE(trading_day_id, stock_code, theme_id)
);
CREATE INDEX idx_stock_score_stock_day ON stock_daily_score(stock_code, trading_day_id);

CREATE TABLE stock_daily_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    stock_code TEXT NOT NULL REFERENCES stock(stock_code),
    theme_id INTEGER NOT NULL REFERENCES theme(id),
    role TEXT NOT NULL,
    lifecycle TEXT NOT NULL,
    total_score INTEGER,
    rating TEXT,
    delta_score INTEGER,
    delta_reason TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_stock_review_day_theme UNIQUE(trading_day_id, stock_code, theme_id)
);

CREATE TABLE score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    previous_score INTEGER,
    current_score INTEGER,
    delta_score INTEGER,
    delta_reason TEXT NOT NULL,
    horizon TEXT NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE INDEX idx_score_history_entity ON score_history(entity_type, entity_key, trade_date);

CREATE TABLE stock_driver (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    stock_code TEXT NOT NULL REFERENCES stock(stock_code),
    theme_id INTEGER NOT NULL REFERENCES theme(id), driver_code INTEGER NOT NULL,
    driver_name TEXT NOT NULL, evidence_level TEXT NOT NULL,
    CONSTRAINT uq_stock_driver_day UNIQUE(trading_day_id, stock_code, theme_id, driver_code)
);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    evidence_level TEXT NOT NULL, evidence_type TEXT NOT NULL,
    title TEXT NOT NULL, source_name TEXT NOT NULL, source_url TEXT,
    published_at DATETIME, excerpt TEXT NOT NULL, verified BOOLEAN NOT NULL
);
CREATE INDEX idx_evidence_entity ON evidence(entity_type, entity_key, trading_day_id);

CREATE TABLE risk_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    risk_type TEXT NOT NULL, severity TEXT NOT NULL, penalty INTEGER NOT NULL,
    description TEXT NOT NULL, invalidation_condition TEXT NOT NULL
);

CREATE TABLE tomorrow_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    entity_type TEXT NOT NULL, entity_key TEXT NOT NULL,
    check_type TEXT NOT NULL, description TEXT NOT NULL,
    status TEXT NOT NULL, resolved_day_id INTEGER REFERENCES trading_day(id),
    result TEXT, created_at DATETIME NOT NULL
);
CREATE INDEX idx_check_status ON tomorrow_check(status, proposed_day_id);

CREATE TABLE validation_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    validation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    source_check_id INTEGER REFERENCES tomorrow_check(id),
    created_at DATETIME NOT NULL
);
CREATE INDEX idx_validation_result_status ON validation_result(trade_date, status);

CREATE TABLE market_packet_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    packet_path TEXT NOT NULL,
    compact_path TEXT NOT NULL,
    quality_path TEXT NOT NULL,
    packet_sha256 TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    data_quality_score INTEGER NOT NULL,
    missing_data TEXT NOT NULL,
    generated_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_market_packet_log UNIQUE(trade_date, packet_sha256)
);

CREATE TABLE fact_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_type TEXT NOT NULL, natural_key TEXT NOT NULL, content_hash TEXT NOT NULL,
    source_batch_id INTEGER REFERENCES source_batch(id), payload_json TEXT NOT NULL,
    is_current BOOLEAN NOT NULL, supersedes_id INTEGER REFERENCES fact_version(id),
    first_seen_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL,
    CONSTRAINT uq_fact_version_content UNIQUE(fact_type, natural_key, content_hash)
);
CREATE INDEX idx_fact_version_current
    ON fact_version(fact_type, natural_key, is_current);

CREATE TABLE fact_partition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset TEXT NOT NULL, trade_date DATE NOT NULL, content_hash TEXT NOT NULL,
    path TEXT NOT NULL, record_count INTEGER NOT NULL, schema_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_fact_partition_content UNIQUE(dataset, trade_date, content_hash)
);
CREATE INDEX idx_fact_partition_dataset_date
    ON fact_partition(dataset, trade_date);

CREATE TABLE official_announcement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    source TEXT NOT NULL,
    url TEXT,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    confirmed_fact TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    clarification_flags TEXT NOT NULL,
    risk_flags TEXT NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE INDEX idx_official_announcement_date_stock ON official_announcement(trade_date, stock_code);

CREATE TABLE official_policy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    title TEXT NOT NULL,
    agency TEXT NOT NULL,
    published_at TEXT,
    url TEXT,
    summary TEXT NOT NULL,
    policy_level TEXT NOT NULL,
    related_industries TEXT NOT NULL,
    related_themes TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE INDEX idx_official_policy_date_agency ON official_policy(trade_date, agency);

CREATE TABLE theme_relationship (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL REFERENCES trading_day(id),
    parent_theme_id INTEGER REFERENCES theme(id),
    child_theme_id INTEGER REFERENCES theme(id),
    relation_type TEXT NOT NULL, description TEXT
);

CREATE TABLE review_prediction_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_date DATE NOT NULL,
    source_review TEXT NOT NULL,
    theme_prediction TEXT NOT NULL,
    style_prediction TEXT NOT NULL,
    leader_candidates TEXT NOT NULL,
    next_day_plan TEXT NOT NULL,
    inflection_candidates TEXT NOT NULL,
    risk_points TEXT NOT NULL,
    confidence_level TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_review_prediction_source_date UNIQUE(prediction_date, source_review)
);
CREATE INDEX idx_review_prediction_date ON review_prediction_record(prediction_date);

CREATE TABLE review_validation_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    validation_date DATE NOT NULL,
    prediction_id INTEGER NOT NULL REFERENCES review_prediction_record(id),
    actual_market_state TEXT NOT NULL,
    actual_theme_result TEXT NOT NULL,
    theme_return_5d TEXT NOT NULL,
    theme_return_10d TEXT NOT NULL,
    theme_return_20d TEXT NOT NULL,
    leader_result TEXT NOT NULL,
    stock_result TEXT NOT NULL,
    max_gain REAL,
    max_drawdown REAL,
    error_type TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_review_validation_prediction_date UNIQUE(prediction_id, validation_date)
);
CREATE INDEX idx_review_validation_date ON review_validation_result(validation_date);
