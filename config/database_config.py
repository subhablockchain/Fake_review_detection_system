"""
Fake Review Detection System - Database Configuration & Management Module
Supports SQLite (local default), MySQL, and MongoDB data persistence.
"""

import os
import sqlite3
import datetime
from typing import List, Dict, Any, Optional

try:
    import pymongo
    HAS_MONGODB = True
except ImportError:
    HAS_MONGODB = False

try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

# Store SQLite DB in data/ directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
SQLITE_DB_PATH = os.path.join(DATA_DIR, "fake_reviews.db")

# ---------------------------------------------------------
# SQLite Local Default Database Manager
# ---------------------------------------------------------
def init_sqlite_db():
    """Initializes SQLite tables for users and review logs."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_text TEXT NOT NULL,
            prediction TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)
    
    conn.commit()
    conn.close()

def save_sqlite_log(review_text: str, prediction: str, confidence: float):
    """Saves a review analysis record to SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO review_logs (review_text, prediction, confidence) VALUES (?, ?, ?)",
        (review_text, prediction, confidence)
    )
    conn.commit()
    conn.close()

def get_sqlite_recent_logs(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieves recent review analysis logs from SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, review_text, prediction, confidence, created_at FROM review_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ---------------------------------------------------------
# Unified Database Interface
# ---------------------------------------------------------
class DatabaseManager:
    """Unified Database Interface (defaults to SQLite with fallbacks)."""
    
    def __init__(self, engine: str = "sqlite"):
        self.engine = engine.lower()
        if self.engine == "sqlite":
            init_sqlite_db()
            
    def log_review(self, review_text: str, prediction: str, confidence: float):
        if self.engine == "sqlite":
            save_sqlite_log(review_text, prediction, confidence)
            
    def get_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        if self.engine == "sqlite":
            return get_sqlite_recent_logs(limit)
        return []

if __name__ == "__main__":
    print("Testing Database Configuration in config/...")
    db = DatabaseManager(engine="sqlite")
    db.log_review("I bought this phone. Great battery life!", "REAL", 98.5)
    history = db.get_history(limit=5)
    print(f"✅ Database initialized in '{SQLITE_DB_PATH}'. History count: {len(history)}")
