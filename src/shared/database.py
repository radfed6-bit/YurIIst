import json
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import aiosqlite

from src.config import settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_db_path = settings.database_path
if not Path(_db_path).is_absolute():
    _db_path = str(_PROJECT_ROOT / _db_path)
DB_PATH = Path(_db_path)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def async_get_connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


@asynccontextmanager
async def async_get_db():
    conn = await async_get_connection()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                short_title TEXT DEFAULT '',
                doc_type TEXT NOT NULL,
                official_number TEXT DEFAULT '',
                adoption_date TEXT DEFAULT NULL,
                effective_date TEXT DEFAULT NULL,
                source_url TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                article_number TEXT NOT NULL,
                title TEXT DEFAULT '',
                content TEXT NOT NULL,
                chapter TEXT DEFAULT '',
                section TEXT DEFAULT '',
                paragraph TEXT DEFAULT '',
                parent_article_id INTEGER DEFAULT NULL REFERENCES articles(id),
                "order" INTEGER DEFAULT 0,
                UNIQUE(document_id, article_number)
            );

            CREATE INDEX IF NOT EXISTS idx_articles_document_id ON articles(document_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                content, title, chapter, section,
                content='articles',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, content, title, chapter, section)
                VALUES (new.id, new.content, new.title, new.chapter, new.section);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, content, title, chapter, section)
                VALUES ('delete', old.id, old.content, old.title, old.chapter, old.section);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, content, title, chapter, section)
                VALUES ('delete', old.id, old.content, old.title, old.chapter, old.section);
                INSERT INTO articles_fts(rowid, content, title, chapter, section)
                VALUES (new.id, new.content, new.title, new.chapter, new.section);
            END;

            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                tier TEXT NOT NULL DEFAULT 'free',
                active_until TEXT,
                trial_used INTEGER DEFAULT 0,
                telegram_payment_charge_id TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            );

            CREATE TABLE IF NOT EXISTS daily_doc_usage (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_events_name_created ON events(event_name, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, created_at);
        """)
