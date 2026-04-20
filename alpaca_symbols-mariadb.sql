-- MariaDB table for Alpaca symbols
CREATE TABLE alpaca_symbols (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id VARCHAR(64) NOT NULL UNIQUE,
    symbol VARCHAR(32) NOT NULL,
    name VARCHAR(255),
    status VARCHAR(32),
    tradable TINYINT(1),
    marginable TINYINT(1),
    shortable TINYINT(1),
    easy_to_borrow TINYINT(1),
    fractionable TINYINT(1),
    asset_class VARCHAR(32),
    exchange VARCHAR(32),
    last_trade_time DATETIME,
    maintenance_margin_requirement DOUBLE,
    min_order_size DOUBLE,
    min_trade_increment DOUBLE,
    min_trade_price_increment DOUBLE,
    attributes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
