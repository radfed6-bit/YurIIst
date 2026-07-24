import json

import pytest

from src.shared.database import DB_PATH


@pytest.fixture
def seeded_db(test_db):
    import aiosqlite
    import asyncio

    async def _seed():
        async with aiosqlite.connect(str(test_db)) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO documents (slug, title, doc_type) VALUES (?, ?, ?)",
                ("test-codex", "Тестовый кодекс", "codex"),
            )
            await conn.execute(
                "INSERT OR IGNORE INTO articles (document_id, article_number, title, content) VALUES (1, '1', 'Статья 1', 'Содержание статьи 1. Тестовый текст для поиска.')",
            )
            await conn.execute(
                "INSERT OR IGNORE INTO articles (document_id, article_number, title, content) VALUES (1, '2', 'Статья 2', 'Содержание статьи 2. Другой тестовый текст.')",
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


@pytest.mark.asyncio
async def test_search_legal_db_empty(test_db):
    from src.agent.tools import search_legal_db
    result = await search_legal_db("несуществующий запрос")
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_search_legal_db_with_data(seeded_db):
    from src.agent.tools import search_legal_db
    result = await search_legal_db("тестовый")
    data = json.loads(result)
    assert len(data) >= 1
    assert "тестовый" in data[0]["content"].lower()


@pytest.mark.asyncio
async def test_search_legal_db_filter_by_slug(seeded_db):
    from src.agent.tools import search_legal_db
    result = await search_legal_db("тестовый", doc_slug="test-codex")
    data = json.loads(result)
    assert len(data) >= 1
    assert data[0]["slug"] == "test-codex"


@pytest.mark.asyncio
async def test_search_legal_db_wrong_slug(seeded_db):
    from src.agent.tools import search_legal_db
    result = await search_legal_db("тестовый", doc_slug="nonexistent")
    data = json.loads(result)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_get_article_found(seeded_db):
    from src.agent.tools import get_article
    result = await get_article("test-codex", "1")
    data = json.loads(result)
    assert data["article_number"] == "1"
    assert data["slug"] == "test-codex"


@pytest.mark.asyncio
async def test_get_article_not_found(seeded_db):
    from src.agent.tools import get_article
    result = await get_article("test-codex", "999")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_get_article_cache(seeded_db):
    from src.agent.tools import get_article, _ARTICLE_CACHE
    _ARTICLE_CACHE.clear()
    await get_article("test-codex", "1")
    assert f"test-codex:1" in _ARTICLE_CACHE
    result = await get_article("test-codex", "1")
    data = json.loads(result)
    assert data["article_number"] == "1"


@pytest.mark.asyncio
async def test_web_fetch_rejects_internal_url(test_db):
    from src.agent.tools import web_fetch
    result = await web_fetch("http://127.0.0.1/admin")
    data = json.loads(result)
    assert "error" in data
    assert "внутренним" in data["error"].lower()


@pytest.mark.asyncio
async def test_web_fetch_rejects_invalid_scheme(test_db):
    from src.agent.tools import web_fetch
    result = await web_fetch("ftp://example.com")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_web_fetch_rejects_localhost(test_db):
    from src.agent.tools import web_fetch
    result = await web_fetch("http://localhost:8080/secret")
    data = json.loads(result)
    assert "error" in data
