"""
Database layer — MySQL connection and query helpers.
Reviews are scoped per user, tagged with confidence level / human-review
status / cache status, and analytics are computed from real stored data
(no fabricated numbers).
"""

import json
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "fake_review_detector"),
}


def get_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        raise RuntimeError(f"Database connection failed: {e}")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username: str, hashed_password: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, hashed_password) VALUES (%s, %s)",
            (username, hashed_password),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, username, created_at FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Reviews (scoped per user)
# ---------------------------------------------------------------------------

def save_review(
    review_text: str, rating: int | None, label: str, confidence: int,
    reasoning: str, user_id: int | None = None,
    confidence_level: str | None = None, needs_human_review: bool = False,
    indicators: list | None = None, was_cached: bool = False,
) -> int:
    """Inserts a review and its AI agent prediction. Returns the new row id."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO reviews
                (user_id, review_text, rating, predicted_label, confidence,
                 confidence_level, needs_human_review, reasoning, indicators, was_cached)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, review_text, rating, label, confidence,
                confidence_level, needs_human_review, reasoning,
                json.dumps(indicators or []), was_cached,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def _deserialize_indicators(row: dict) -> dict:
    """Converts the stored JSON-text indicators column back into a list."""
    if row is None:
        return row
    raw = row.get("indicators")
    try:
        row["indicators"] = json.loads(raw) if raw else []
    except (TypeError, json.JSONDecodeError):
        row["indicators"] = []
    return row


def get_history(limit: int = 20, user_id: int | None = None) -> list[dict]:
    """Fetches the most recent predictions, newest first. Scoped to user_id if given."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cols = """id, review_text, rating, predicted_label, confidence, confidence_level,
                  needs_human_review, reasoning, indicators, was_cached, created_at"""
        if user_id is not None:
            cursor.execute(
                f"SELECT {cols} FROM reviews WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        else:
            cursor.execute(
                f"SELECT {cols} FROM reviews ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return [_deserialize_indicators(r) for r in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def get_review_by_id(review_id: int, user_id: int | None = None) -> dict | None:
    """Fetches a single review by id. If user_id given, only returns it if owned by that user.
    This is the enforcement point for user data isolation on single-review reads."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if user_id is not None:
            cursor.execute("SELECT * FROM reviews WHERE id = %s AND user_id = %s", (review_id, user_id))
        else:
            cursor.execute("SELECT * FROM reviews WHERE id = %s", (review_id,))
        return _deserialize_indicators(cursor.fetchone())
    finally:
        cursor.close()
        conn.close()


def delete_review(review_id: int, user_id: int | None = None) -> bool:
    """Deletes a review by id, optionally scoped to the owning user.
    Scoping to user_id is what prevents user A from deleting user B's rows."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if user_id is not None:
            cursor.execute("DELETE FROM reviews WHERE id = %s AND user_id = %s", (review_id, user_id))
        else:
            cursor.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Analytics — all computed from real stored data
# ---------------------------------------------------------------------------

def get_stats(user_id: int | None = None) -> dict:
    """Returns aggregate counts, optionally scoped to a single user.
    Includes cache efficiency and human-review metrics, not just raw totals."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        base = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN predicted_label = 'Fake' THEN 1 ELSE 0 END) AS fake_count,
                SUM(CASE WHEN predicted_label = 'Genuine' THEN 1 ELSE 0 END) AS genuine_count,
                AVG(confidence) AS avg_confidence,
                SUM(CASE WHEN needs_human_review = TRUE THEN 1 ELSE 0 END) AS needs_human_review_count,
                SUM(CASE WHEN was_cached = TRUE THEN 1 ELSE 0 END) AS cache_hits
            FROM reviews
        """
        if user_id is not None:
            cursor.execute(base + " WHERE user_id = %s", (user_id,))
        else:
            cursor.execute(base)
        row = cursor.fetchone()

        total = row["total"] or 0
        fake_count = row["fake_count"] or 0
        genuine_count = row["genuine_count"] or 0
        cache_hits = row["cache_hits"] or 0

        return {
            "total": total,
            "fake_count": fake_count,
            "genuine_count": genuine_count,
            "fake_percentage": round((fake_count / total * 100), 1) if total else 0,
            "genuine_percentage": round((genuine_count / total * 100), 1) if total else 0,
            "avg_confidence": round(row["avg_confidence"], 1) if row["avg_confidence"] else 0,
            "needs_human_review_count": row["needs_human_review_count"] or 0,
            "cache_hits": cache_hits,
            "llm_calls": total - cache_hits,
        }
    finally:
        cursor.close()
        conn.close()


def get_confidence_distribution(user_id: int | None = None) -> dict:
    """Counts of HIGH / MEDIUM / LOW confidence predictions — real counts
    from the confidence_level column, not derived/estimated values."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        base = """
            SELECT confidence_level, COUNT(*) AS count
            FROM reviews
            WHERE confidence_level IS NOT NULL
        """
        params = []
        if user_id is not None:
            base += " AND user_id = %s"
            params.append(user_id)
        base += " GROUP BY confidence_level"
        cursor.execute(base, tuple(params))
        rows = {r["confidence_level"]: r["count"] for r in cursor.fetchall()}
        return {
            "HIGH": rows.get("HIGH", 0),
            "MEDIUM": rows.get("MEDIUM", 0),
            "LOW": rows.get("LOW", 0),
        }
    finally:
        cursor.close()
        conn.close()


def get_trend(days: int = 14, user_id: int | None = None) -> list[dict]:
    """Returns per-day Fake/Genuine/human-review counts for the last `days`
    days, oldest first. Used to plot the analytics trend chart."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        base = """
            SELECT
                DATE(created_at) AS day,
                SUM(CASE WHEN predicted_label = 'Fake' THEN 1 ELSE 0 END) AS fake_count,
                SUM(CASE WHEN predicted_label = 'Genuine' THEN 1 ELSE 0 END) AS genuine_count,
                SUM(CASE WHEN needs_human_review = TRUE THEN 1 ELSE 0 END) AS human_review_count
            FROM reviews
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """
        params = [days]
        if user_id is not None:
            base += " AND user_id = %s"
            params.append(user_id)
        base += " GROUP BY DATE(created_at) ORDER BY day ASC"
        cursor.execute(base, tuple(params))
        rows = cursor.fetchall()
        for r in rows:
            r["day"] = r["day"].isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Review result cache (version-aware — see src/config.py MODEL_VERSION /
# PROMPT_VERSION, which are baked into the hash by the caller before it
# reaches these functions)
# ---------------------------------------------------------------------------

def get_cached_result(review_hash: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT predicted_label, confidence, reasoning, indicators FROM review_cache WHERE review_hash = %s",
            (review_hash,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE review_cache SET hit_count = hit_count + 1 WHERE review_hash = %s",
                (review_hash,),
            )
            conn.commit()
            try:
                row["indicators"] = json.loads(row["indicators"]) if row.get("indicators") else []
            except (TypeError, json.JSONDecodeError):
                row["indicators"] = []
        return row
    finally:
        cursor.close()
        conn.close()


def save_cache_result(
    review_hash: str, label: str, confidence: int, reasoning: str,
    indicators: list | None = None, model_version: str | None = None,
    prompt_version: str | None = None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO review_cache
                (review_hash, predicted_label, confidence, reasoning, indicators, model_version, prompt_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                predicted_label = VALUES(predicted_label),
                confidence = VALUES(confidence),
                reasoning = VALUES(reasoning),
                indicators = VALUES(indicators),
                hit_count = hit_count + 1
            """,
            (review_hash, label, confidence, reasoning, json.dumps(indicators or []), model_version, prompt_version),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
