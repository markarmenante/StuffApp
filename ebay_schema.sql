-- Shipping is independent of banknotes.status (collection ownership).
-- Email evidence can be supplied by Today.
-- No addresses, payment details, raw API responses, or plaintext tokens.
CREATE TABLE IF NOT EXISTS ebay_connection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    account_key TEXT NOT NULL,
    account_name TEXT NOT NULL,
    owner_email TEXT NOT NULL,
    refresh_token TEXT,
    access_token TEXT,
    access_expires REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    generation INTEGER NOT NULL DEFAULT 1,
    connected_at TEXT NOT NULL,
    last_attempt TEXT,
    last_success TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS ebay_oauth_states (
    state_hash TEXT PRIMARY KEY,
    browser_hash TEXT NOT NULL,
    owner_email TEXT NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ebay_order_items (
    line_key TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    seller TEXT NOT NULL DEFAULT '',
    seller_key TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    ordered_at TEXT,
    shipped_at TEXT,
    delivered_at TEXT,
    estimated_delivery TEXT,
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('Ordered','Shipped','Delivered')),
    attention TEXT NOT NULL DEFAULT '',
    last_seen TEXT NOT NULL,
    ignored INTEGER NOT NULL DEFAULT 0 CHECK (ignored IN (0,1))
);
CREATE INDEX IF NOT EXISTS ebay_items_listing ON ebay_order_items(item_id);
CREATE INDEX IF NOT EXISTS ebay_items_seller ON ebay_order_items(seller_key);
CREATE TABLE IF NOT EXISTS ebay_item_tracking (
    line_key TEXT NOT NULL REFERENCES ebay_order_items(line_key) ON DELETE CASCADE,
    carrier TEXT NOT NULL,
    tracking_number TEXT NOT NULL,
    PRIMARY KEY (line_key, carrier, tracking_number)
);
CREATE TABLE IF NOT EXISTS banknote_ebay_links (
    banknote_id TEXT PRIMARY KEY REFERENCES banknotes(id) ON DELETE CASCADE,
    line_key TEXT NOT NULL UNIQUE REFERENCES ebay_order_items(line_key) ON DELETE CASCADE,
    matched_by TEXT NOT NULL CHECK (matched_by IN ('listing','manual')),
    matched_at TEXT NOT NULL,
    manual_status TEXT CHECK (manual_status IN ('Ordered','Shipped','Delivered'))
);
CREATE TABLE IF NOT EXISTS ebay_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    banknote_id TEXT NOT NULL REFERENCES banknotes(id) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    source TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ebay_events_note ON ebay_status_events(banknote_id, id);
CREATE TABLE IF NOT EXISTS ebay_sync_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    items_seen INTEGER NOT NULL DEFAULT 0,
    matched INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
-- Non-reversible suppression fingerprints prevent re-import after deletion.
CREATE TABLE IF NOT EXISTS ebay_deleted_accounts (
    identity_hash TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS ebay_mail_connection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    last_received TEXT
);
CREATE TABLE IF NOT EXISTS ebay_mail_receipts (
    message_id TEXT PRIMARY KEY,
    line_key TEXT NOT NULL REFERENCES ebay_order_items(line_key) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('Ordered','Shipped','Delivered')),
    evidence TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ebay_mail_item ON ebay_mail_receipts(line_key);
