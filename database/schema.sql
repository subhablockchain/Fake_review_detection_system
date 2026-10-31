-- Fake Review Detection System — Database Schema

CREATE DATABASE IF NOT EXISTS fake_review_detector;
USE fake_review_detector;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    review_text TEXT NOT NULL,
    rating INT,
    predicted_label VARCHAR(20),
    confidence INT,
    confidence_level VARCHAR(10),          -- HIGH / MEDIUM / LOW
    needs_human_review BOOLEAN DEFAULT FALSE,
    reasoning TEXT,
    indicators TEXT,                        -- JSON-encoded list of short signal phrases
    was_cached BOOLEAN DEFAULT FALSE,       -- true if served from review_cache (no LLM call)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_reviews_user_id ON reviews(user_id);
CREATE INDEX idx_reviews_created_at ON reviews(created_at);
CREATE INDEX idx_reviews_human_review ON reviews(needs_human_review);

-- Caches AI agent results by a hash of (review_text + rating + model_version +
-- prompt_version) so an identical review submitted again skips the LLM call
-- entirely — and a model/prompt change automatically invalidates old entries
-- because the hash changes, without needing to clear the table.
CREATE TABLE IF NOT EXISTS review_cache (
    review_hash VARCHAR(64) PRIMARY KEY,
    predicted_label VARCHAR(20) NOT NULL,
    confidence INT NOT NULL,
    reasoning TEXT NOT NULL,
    indicators TEXT,
    model_version VARCHAR(50),
    prompt_version VARCHAR(50),
    hit_count INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_hit_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
