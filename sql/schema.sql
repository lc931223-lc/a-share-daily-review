PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trading_day (
    trade_date TEXT PRIMARY KEY,
    market_regime TEXT,
    turnover REAL,
    turnover_delta REAL,
    advancers INTEGER,
    decliners INTEGER,
    limit_up_count INTEGER,
    limit_down_count INTEGER,
    max_board_height INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS theme (
    theme_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS theme_daily_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    theme_id INTEGER NOT NULL,
    rank_no INTEGER,
    stage TEXT,
    change_status TEXT,
    causal_chain TEXT,
    base_logic_score INTEGER,
    realization_score INTEGER,
    expectation_gap_score INTEGER,
    persistence_score INTEGER,
    market_confirmation_score INTEGER,
    risk_penalty INTEGER,
    total_score INTEGER,
    rating TEXT,
    logic_quality INTEGER,
    market_strength INTEGER,
    risk_reward INTEGER,
    delta_score INTEGER,
    delta_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, theme_id),
    FOREIGN KEY(theme_id) REFERENCES theme(theme_id)
);

CREATE TABLE IF NOT EXISTS theme_driver (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    theme_id INTEGER NOT NULL,
    driver_code INTEGER NOT NULL,
    driver_name TEXT NOT NULL,
    evidence_level TEXT,
    FOREIGN KEY(theme_id) REFERENCES theme(theme_id)
);

CREATE TABLE IF NOT EXISTS stock (
    stock_code TEXT PRIMARY KEY,
    stock_name TEXT NOT NULL,
    exchange TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_daily_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    theme_id INTEGER,
    role TEXT,
    stage TEXT,
    catalyst TEXT,
    benefit_path TEXT,
    causal_chain TEXT,
    realization_score INTEGER,
    expectation_gap INTEGER,
    logic_quality INTEGER,
    market_strength INTEGER,
    risk_reward INTEGER,
    total_score INTEGER,
    rating TEXT,
    delta_score INTEGER,
    delta_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, stock_code, theme_id),
    FOREIGN KEY(stock_code) REFERENCES stock(stock_code),
    FOREIGN KEY(theme_id) REFERENCES theme(theme_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    evidence_type TEXT,
    title TEXT,
    source_name TEXT,
    source_url TEXT,
    published_at TEXT,
    excerpt TEXT,
    verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    risk_type TEXT NOT NULL,
    severity TEXT,
    penalty INTEGER,
    description TEXT,
    invalidation_condition TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tomorrow_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    check_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    resolved_on TEXT,
    result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS theme_relationship (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    parent_theme_id INTEGER,
    child_theme_id INTEGER,
    relation_type TEXT,
    description TEXT,
    FOREIGN KEY(parent_theme_id) REFERENCES theme(theme_id),
    FOREIGN KEY(child_theme_id) REFERENCES theme(theme_id)
);

CREATE INDEX IF NOT EXISTS idx_theme_daily_score_date ON theme_daily_score(trade_date);
CREATE INDEX IF NOT EXISTS idx_stock_daily_score_date ON stock_daily_score(trade_date);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(entity_type, entity_key, trade_date);
