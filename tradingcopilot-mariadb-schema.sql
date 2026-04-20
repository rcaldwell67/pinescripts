-- MariaDB schema for tradingcopilot (converted from SQLite)

CREATE TABLE backtest_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT 'v6',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metrics TEXT,
    notes TEXT,
    current_equity DOUBLE
);

CREATE TABLE paper_trading_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT 'v6',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metrics TEXT,
    notes TEXT,
    current_equity DOUBLE
);

CREATE TABLE live_trading_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT 'v6',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metrics TEXT,
    notes TEXT,
    current_equity DOUBLE
);

CREATE TABLE symbols (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL UNIQUE,
    description VARCHAR(255),
    asset_type VARCHAR(32) DEFAULT 'crypto',
    live_enabled TINYINT(1) NOT NULL DEFAULT 1
);

CREATE TABLE audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    user VARCHAR(64),
    action VARCHAR(64) NOT NULL,
    target_table VARCHAR(64),
    target_id INT,
    details TEXT
);

CREATE TABLE trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT 'v1',
    mode VARCHAR(16) NOT NULL DEFAULT 'backtest',
    entry_time DATETIME,
    exit_time DATETIME,
    direction VARCHAR(8),
    entry_price DOUBLE,
    exit_price DOUBLE,
    result VARCHAR(16),
    pnl_pct DOUBLE,
    dollar_pnl DOUBLE,
    equity DOUBLE,
    source VARCHAR(32)
);

CREATE TABLE chart_data (
    symbol VARCHAR(32) NOT NULL,
    t BIGINT NOT NULL,
    o DOUBLE NOT NULL,
    h DOUBLE NOT NULL,
    l DOUBLE NOT NULL,
    c DOUBLE NOT NULL,
    v DOUBLE NOT NULL,
    PRIMARY KEY (symbol, t)
);

CREATE TABLE chart_meta (
    symbol VARCHAR(32) PRIMARY KEY,
    generated_at DATETIME NOT NULL
);

CREATE TABLE Account_Info (
    account_id VARCHAR(64) PRIMARY KEY,
    account_number VARCHAR(32),
    account_mode VARCHAR(16),
    currency VARCHAR(8),
    status VARCHAR(16),
    beginning_balance DOUBLE,
    current_balance DOUBLE,
    buying_power DOUBLE,
    cash DOUBLE,
    last_event VARCHAR(64),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE paper_fill_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    activity_id VARCHAR(64) UNIQUE NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8),
    qty DOUBLE,
    price DOUBLE,
    transaction_time DATETIME,
    order_id VARCHAR(64),
    raw_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE paper_order_trade_links (
    order_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL,
    trade_id INT NOT NULL,
    role VARCHAR(16) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE paper_order_events (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32),
    status VARCHAR(16),
    event_type VARCHAR(32),
    event_time DATETIME,
    qty DOUBLE,
    notional DOUBLE,
    filled_qty DOUBLE,
    submitted_at DATETIME,
    raw_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE live_fill_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    activity_id VARCHAR(64) UNIQUE NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8),
    qty DOUBLE,
    price DOUBLE,
    transaction_time DATETIME,
    order_id VARCHAR(64),
    raw_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE live_order_trade_links (
    order_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    version VARCHAR(16) NOT NULL,
    trade_id INT NOT NULL,
    role VARCHAR(16) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE live_order_events (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32),
    status VARCHAR(16),
    event_type VARCHAR(32),
    event_time DATETIME,
    qty DOUBLE,
    notional DOUBLE,
    filled_qty DOUBLE,
    submitted_at DATETIME,
    raw_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
