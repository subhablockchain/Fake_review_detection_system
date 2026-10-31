-- Migration 001 — Confidence-based human review + cache versioning
-- Run this against an EXISTING database (created before this upgrade)
-- to add the new columns without losing any existing data.
--
-- Requires MySQL 8.0.29+ / MariaDB 10.5+ for "ADD COLUMN IF NOT EXISTS".
-- On older MySQL, remove "IF NOT EXISTS" and run manually (it will error
-- harmlessly if a column already exists).

USE fake_review_detector;

ALTER TABLE reviews
    ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(10) AFTER confidence,
    ADD COLUMN IF NOT EXISTS needs_human_review BOOLEAN DEFAULT FALSE AFTER confidence_level,
    ADD COLUMN IF NOT EXISTS indicators TEXT AFTER reasoning,
    ADD COLUMN IF NOT EXISTS was_cached BOOLEAN DEFAULT FALSE AFTER indicators;

CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);
CREATE INDEX IF NOT EXISTS idx_reviews_human_review ON reviews(needs_human_review);

ALTER TABLE review_cache
    ADD COLUMN IF NOT EXISTS indicators TEXT AFTER reasoning,
    ADD COLUMN IF NOT EXISTS model_version VARCHAR(50) AFTER indicators,
    ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(50) AFTER model_version;

-- Optional: backfill confidence_level for historical rows using the same
-- thresholds as src/config.py (defaults: HIGH >= 80, MEDIUM >= 60).
UPDATE reviews
SET confidence_level = CASE
    WHEN confidence >= 80 THEN 'HIGH'
    WHEN confidence >= 60 THEN 'MEDIUM'
    ELSE 'LOW'
END,
needs_human_review = (confidence < 60)
WHERE confidence_level IS NULL;
