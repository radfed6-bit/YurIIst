import aiosqlite
import pytest

from src.shared.database import DB_PATH


@pytest.mark.asyncio
async def test_init_db_creates_all_tables(test_db):
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    required = {"documents", "articles", "articles_fts", "subscriptions", "daily_usage", "daily_doc_usage", "sessions_v2", "active_sessions", "events"}
    assert required.issubset(tables), f"Missing tables: {required - tables}"


@pytest.mark.asyncio
async def test_subscriptions_unique_charge_id(test_db):
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT sql FROM sqlite_master WHERE name='subscriptions'")
        sql = (await cursor.fetchone())[0]
    assert "UNIQUE" in sql


@pytest.mark.asyncio
async def test_events_table_indexed(test_db):
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events'"
        )
        indexes = {row[0] for row in await cursor.fetchall()}
    assert "idx_events_name_created" in indexes
    assert "idx_events_user" in indexes


@pytest.mark.asyncio
async def test_documents_articles_relation(test_db):
    async with aiosqlite.connect(str(test_db)) as conn:
        await conn.execute("INSERT INTO documents (slug, title, doc_type) VALUES ('doc1', 'Doc 1', 'codex')")
        await conn.execute("INSERT INTO articles (document_id, article_number, content) VALUES (1, '1', 'content')")
        await conn.commit()
        cursor = await conn.execute("SELECT a.article_number, d.slug FROM articles a JOIN documents d ON d.id = a.document_id")
        row = await cursor.fetchone()
    assert row[0] == "1"
    assert row[1] == "doc1"
