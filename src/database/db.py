"""
SQLite database layer for the Fake Review Detection System.
Keeps the same public helper functions used by the FastAPI app.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", BASE_DIR / "data" / "fake_review_detector.db"))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        raise RuntimeError(f"Database connection failed: {e}")


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                review_text TEXT NOT NULL,
                rating INTEGER,
                predicted_label TEXT,
                confidence INTEGER,
                confidence_level TEXT,
                needs_human_review INTEGER DEFAULT 0,
                reasoning TEXT,
                indicators TEXT,
                was_cached INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_user_id
                ON reviews(user_id);

            CREATE INDEX IF NOT EXISTS idx_reviews_created_at
                ON reviews(created_at);

            CREATE INDEX IF NOT EXISTS idx_reviews_human_review
                ON reviews(needs_human_review);

            CREATE TABLE IF NOT EXISTS review_cache (
                review_hash TEXT PRIMARY KEY,
                predicted_label TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                indicators TEXT,
                model_version TEXT,
                prompt_version TEXT,
                hit_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_hit_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


init_db()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username: str, hashed_password: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed_password),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def save_review(
    review_text: str,
    rating: int | None,
    label: str,
    confidence: int,
    reasoning: str,
    user_id: int | None = None,
    confidence_level: str | None = None,
    needs_human_review: bool = False,
    indicators: list | None = None,
    was_cached: bool = False,
) -> int:

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO reviews
            (
                user_id, review_text, rating, predicted_label,
                confidence, confidence_level, needs_human_review,
                reasoning, indicators, was_cached
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                review_text,
                rating,
                label,
                confidence,
                confidence_level,
                int(needs_human_review),
                reasoning,
                json.dumps(indicators or []),
                int(was_cached),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _deserialize_indicators(row):
    if row is None:
        return row

    row = dict(row)

    raw = row.get("indicators")

    try:
        row["indicators"] = json.loads(raw) if raw else []
    except (TypeError, json.JSONDecodeError):
        row["indicators"] = []

    row["needs_human_review"] = bool(row.get("needs_human_review"))
    row["was_cached"] = bool(row.get("was_cached"))

    return row


def get_history(limit: int = 20, user_id: int | None = None) -> list[dict]:
    conn = get_connection()

    try:
        cols = """
            id, review_text, rating, predicted_label, confidence,
            confidence_level, needs_human_review, reasoning,
            indicators, was_cached, created_at
        """

        if user_id is not None:
            rows = conn.execute(
                f"""
                SELECT {cols}
                FROM reviews
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT {cols}
                FROM reviews
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [_deserialize_indicators(row) for row in rows]

    finally:
        conn.close()


def get_review_by_id(
    review_id: int,
    user_id: int | None = None,
) -> dict | None:

    conn = get_connection()

    try:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT *
                FROM reviews
                WHERE id = ? AND user_id = ?
                """,
                (review_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = ?",
                (review_id,),
            ).fetchone()

        return _deserialize_indicators(row)

    finally:
        conn.close()


def delete_review(
    review_id: int,
    user_id: int | None = None,
) -> bool:

    conn = get_connection()

    try:
        if user_id is not None:
            cursor = conn.execute(
                """
                DELETE FROM reviews
                WHERE id = ? AND user_id = ?
                """,
                (review_id, user_id),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM reviews WHERE id = ?",
                (review_id,),
            )

        conn.commit()
        return cursor.rowcount > 0

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_stats(user_id: int | None = None) -> dict:
    conn = get_connection()

    try:
        query = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN predicted_label = 'Fake' THEN 1 ELSE 0 END)
                    AS fake_count,
                SUM(CASE WHEN predicted_label = 'Genuine' THEN 1 ELSE 0 END)
                    AS genuine_count,
                AVG(confidence) AS avg_confidence,
                SUM(
                    CASE WHEN needs_human_review = 1 THEN 1 ELSE 0 END
                ) AS needs_human_review_count,
                SUM(
                    CASE WHEN was_cached = 1 THEN 1 ELSE 0 END
                ) AS cache_hits
            FROM reviews
        """

        if user_id is not None:
            row = conn.execute(
                query + " WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(query).fetchone()

        total = row["total"] or 0
        fake_count = row["fake_count"] or 0
        genuine_count = row["genuine_count"] or 0
        cache_hits = row["cache_hits"] or 0

        return {
            "total": total,
            "fake_count": fake_count,
            "genuine_count": genuine_count,
            "fake_percentage": round(fake_count / total * 100, 1)
                if total else 0,
            "genuine_percentage": round(genuine_count / total * 100, 1)
                if total else 0,
            "avg_confidence": round(row["avg_confidence"], 1)
                if row["avg_confidence"] else 0,
            "needs_human_review_count":
                row["needs_human_review_count"] or 0,
            "cache_hits": cache_hits,
            "llm_calls": total - cache_hits,
        }

    finally:
        conn.close()


def get_confidence_distribution(
    user_id: int | None = None,
) -> dict:

    conn = get_connection()

    try:
        query = """
            SELECT confidence_level, COUNT(*) AS count
            FROM reviews
            WHERE confidence_level IS NOT NULL
        """

        params = []

        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " GROUP BY confidence_level"

        rows = conn.execute(query, params).fetchall()

        data = {
            row["confidence_level"]: row["count"]
            for row in rows
        }

        return {
            "HIGH": data.get("HIGH", 0),
            "MEDIUM": data.get("MEDIUM", 0),
            "LOW": data.get("LOW", 0),
        }

    finally:
        conn.close()


def get_trend(
    days: int = 14,
    user_id: int | None = None,
) -> list[dict]:

    conn = get_connection()

    try:
        cutoff = (
            datetime.now() - timedelta(days=days)
        ).strftime("%Y-%m-%d %H:%M:%S")

        query = """
            SELECT
                DATE(created_at) AS day,
                SUM(
                    CASE WHEN predicted_label = 'Fake'
                    THEN 1 ELSE 0 END
                ) AS fake_count,
                SUM(
                    CASE WHEN predicted_label = 'Genuine'
                    THEN 1 ELSE 0 END
                ) AS genuine_count,
                SUM(
                    CASE WHEN needs_human_review = 1
                    THEN 1 ELSE 0 END
                ) AS human_review_count
            FROM reviews
            WHERE created_at >= ?
        """

        params = [cutoff]

        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " GROUP BY DATE(created_at) ORDER BY day ASC"

        rows = conn.execute(query, params).fetchall()

        return [
            {
                "day": row["day"],
                "fake_count": row["fake_count"] or 0,
                "genuine_count": row["genuine_count"] or 0,
                "human_review_count": row["human_review_count"] or 0,
            }
            for row in rows
        ]

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Review Cache
# ---------------------------------------------------------------------------

def get_cached_result(review_hash: str) -> dict | None:

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                predicted_label,
                confidence,
                reasoning,
                indicators
            FROM review_cache
            WHERE review_hash = ?
            """,
            (review_hash,),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE review_cache
                SET
                    hit_count = hit_count + 1,
                    last_hit_at = CURRENT_TIMESTAMP
                WHERE review_hash = ?
                """,
                (review_hash,),
            )
            conn.commit()

            result = dict(row)

            try:
                result["indicators"] = (
                    json.loads(result["indicators"])
                    if result.get("indicators")
                    else []
                )
            except (TypeError, json.JSONDecodeError):
                result["indicators"] = []

            return result

        return None

    finally:
        conn.close()


def save_cache_result(
    review_hash: str,
    label: str,
    confidence: int,
    reasoning: str,
    indicators: list | None = None,
    model_version: str | None = None,
    prompt_version: str | None = None,
) -> None:

    conn = get_connection()

    try:
        existing = conn.execute(
            """
            SELECT review_hash
            FROM review_cache
            WHERE review_hash = ?
            """,
            (review_hash,),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE review_cache
                SET
                    predicted_label = ?,
                    confidence = ?,
                    reasoning = ?,
                    indicators = ?,
                    model_version = ?,
                    prompt_version = ?,
                    hit_count = hit_count + 1,
                    last_hit_at = CURRENT_TIMESTAMP
                WHERE review_hash = ?
                """,
                (
                    label,
                    confidence,
                    reasoning,
                    json.dumps(indicators or []),
                    model_version,
                    prompt_version,
                    review_hash,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO review_cache
                (
                    review_hash,
                    predicted_label,
                    confidence,
                    reasoning,
                    indicators,
                    model_version,
                    prompt_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_hash,
                    label,
                    confidence,
                    reasoning,
                    json.dumps(indicators or []),
                    model_version,
                    prompt_version,
                ),
            )

        conn.commit()

    finally:
        conn.close()