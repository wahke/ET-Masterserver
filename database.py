# database.py
import sqlite3
from contextlib import contextmanager

DB_NAME = "masterserver.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                port INTEGER,
                name TEXT,
                version TEXT,
                mod TEXT,
                players INTEGER,
                max_players INTEGER,
                map TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
