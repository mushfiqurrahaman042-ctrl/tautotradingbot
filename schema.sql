-- Database schema for Arts Trading Bot
-- PostgreSQL/Supabase compatible schema

-- Table for storing processed webhook events (for idempotency)
CREATE TABLE IF NOT EXISTS processed_events (
    event_id VARCHAR(255) PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table for storing position information
CREATE TABLE IF NOT EXISTS positions (
    id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    strategy_id VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    initial_qty DECIMAL(20, 8) NOT NULL,
    remaining_qty DECIMAL(20, 8) NOT NULL,
    status VARCHAR(20) DEFAULT 'OPEN', -- 'OPEN' or 'CLOSED'
    tp_level INTEGER DEFAULT 0, -- Tracks TP1-TP5
    closed_qty_tp1 DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed at TP1
    closed_qty_tp2 DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed at TP2
    closed_qty_tp3 DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed at TP3
    closed_qty_tp4 DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed at TP4
    closed_qty_tp5 DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed at TP5
    sl_closed_qty DECIMAL(20, 8) DEFAULT 0.0,   -- Quantity closed by stop loss
    timeguard_closed_qty DECIMAL(20, 8) DEFAULT 0.0,  -- Quantity closed by TimeGuard
    maxbars_closed_qty DECIMAL(20, 8) DEFAULT 0.0,    -- Quantity closed by MaxBars
    swingtp_closed_qty DECIMAL(20, 8) DEFAULT 0.0,    -- Quantity closed by SwingTP
    dyn_tp_closed_qty DECIMAL(20, 8) DEFAULT 0.0,     -- Quantity closed by DynTP
    other_closed_qty DECIMAL(20, 8) DEFAULT 0.0,      -- Quantity closed by other means
    entry_price DECIMAL(20, 8),
    order_ids TEXT, -- JSON string list of order IDs
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    leverage INTEGER DEFAULT 1,
    margin_mode VARCHAR(20) DEFAULT 'cross', -- 'cross' or 'isolated'
    sl_type VARCHAR(20) DEFAULT 'base', -- Type of stop loss: base, swing, sfp, body, atr_trail, etc.
    sl_price DECIMAL(20, 8), -- Stop loss price
    tp_levels TEXT, -- JSON string of TP levels with prices and percentages
    entry_strategy VARCHAR(20) DEFAULT 'sfp' -- Entry strategy: sfp, volume_spike, etc.
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_positions_account_status ON positions(account_id, status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol_strategy ON positions(symbol, strategy_id);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_processed_events_timestamp ON processed_events(timestamp);

-- Trigger to update the updated_at timestamp in PostgreSQL
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_positions_updated_at ON positions;
CREATE TRIGGER update_positions_updated_at 
    BEFORE UPDATE ON positions 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();