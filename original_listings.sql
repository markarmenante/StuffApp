CREATE TABLE IF NOT EXISTS original_listing_pages (
    url TEXT PRIMARY KEY,
    vendor TEXT NOT NULL,
    item_key TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'unknown' CHECK(state IN ('unknown','available','gone')),
    checked_at REAL NOT NULL DEFAULT 0,
    next_check_at REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS original_listing_due ON original_listing_pages(next_check_at, lease_until);
CREATE TABLE IF NOT EXISTS coin_original_listings (
    coin_id TEXT PRIMARY KEY REFERENCES coins(id) ON DELETE CASCADE,
    url TEXT NOT NULL REFERENCES original_listing_pages(url)
);
CREATE INDEX IF NOT EXISTS coin_original_listing_url ON coin_original_listings(url);
CREATE TABLE IF NOT EXISTS banknote_original_listings (
    banknote_id TEXT PRIMARY KEY REFERENCES banknotes(id) ON DELETE CASCADE,
    url TEXT NOT NULL REFERENCES original_listing_pages(url)
);
CREATE INDEX IF NOT EXISTS banknote_original_listing_url ON banknote_original_listings(url);
CREATE TABLE IF NOT EXISTS original_listing_checks (
    id TEXT PRIMARY KEY,
    coin_id TEXT UNIQUE REFERENCES coins(id) ON DELETE CASCADE,
    banknote_id TEXT UNIQUE REFERENCES banknotes(id) ON DELETE CASCADE,
    url TEXT NOT NULL REFERENCES original_listing_pages(url),
    state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','checked','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    next_attempt REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0,
    checked_at REAL,
    dismissed INTEGER NOT NULL DEFAULT 0 CHECK(dismissed IN (0,1)),
    record_snapshot TEXT,
    result TEXT,
    CHECK ((coin_id IS NULL) <> (banknote_id IS NULL))
);
CREATE INDEX IF NOT EXISTS original_listing_check_url ON original_listing_checks(url);
CREATE INDEX IF NOT EXISTS original_listing_check_due ON original_listing_checks(state,next_attempt,lease_until);
CREATE TABLE IF NOT EXISTS purchase_source_archives (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('listing','invoice','order')),
    filename TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0,
    saved_at REAL
);
CREATE TABLE IF NOT EXISTS coin_source_archives (
    coin_id TEXT NOT NULL REFERENCES coins(id) ON DELETE CASCADE,
    url TEXT NOT NULL REFERENCES purchase_source_archives(url),
    attached INTEGER NOT NULL DEFAULT 0 CHECK(attached IN (0,1)),
    PRIMARY KEY(coin_id,url)
);
CREATE INDEX IF NOT EXISTS coin_source_archive_url ON coin_source_archives(url);
CREATE TABLE IF NOT EXISTS banknote_source_archives (
    banknote_id TEXT NOT NULL REFERENCES banknotes(id) ON DELETE CASCADE,
    url TEXT NOT NULL REFERENCES purchase_source_archives(url),
    attached INTEGER NOT NULL DEFAULT 0 CHECK(attached IN (0,1)),
    PRIMARY KEY(banknote_id,url)
);
CREATE INDEX IF NOT EXISTS banknote_source_archive_url ON banknote_source_archives(url);

CREATE TABLE IF NOT EXISTS original_image_assets (
    url TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL CHECK(width > 0),
    height INTEGER NOT NULL CHECK(height > 0),
    saved_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS original_listing_image_sources (
    listing_url TEXT NOT NULL REFERENCES purchase_source_archives(url) ON DELETE CASCADE,
    image_url TEXT NOT NULL REFERENCES original_image_assets(url),
    position INTEGER NOT NULL CHECK(position >= 0),
    PRIMARY KEY(listing_url,image_url)
);
CREATE INDEX IF NOT EXISTS original_listing_image_asset ON original_listing_image_sources(image_url);
CREATE TABLE IF NOT EXISTS original_listing_image_scans (
    url TEXT PRIMARY KEY REFERENCES purchase_source_archives(url) ON DELETE CASCADE,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    next_attempt REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS original_listing_image_due ON original_listing_image_scans(completed_at,next_attempt,lease_until);
