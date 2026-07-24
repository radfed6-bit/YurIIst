import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def test_db(tmp_path):
    import src.shared.database as db_mod
    import src.shared.payments as pmt_mod
    import src.shared.session as ses_mod
    import src.shared.analytics as anl_mod
    import src.agent.tools as tools_mod

    old_db = db_mod.DB_PATH
    old_tools_db = tools_mod.SQLITE_PATH
    db_file = tmp_path / "test_legal.db"

    db_mod.DB_PATH = db_file
    pmt_mod.DB_PATH = db_file
    ses_mod.DB_PATH = db_file
    anl_mod.DB_PATH = db_file
    tools_mod.SQLITE_PATH = db_file

    db_mod.init_db()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(ses_mod.init_sessions())
    loop.close()

    yield db_file

    db_mod.DB_PATH = old_db
    pmt_mod.DB_PATH = old_db
    ses_mod.DB_PATH = old_db
    anl_mod.DB_PATH = old_db
    tools_mod.SQLITE_PATH = old_tools_db


@pytest.fixture
def seeded_db(test_db):
    import aiosqlite
    import asyncio

    async def _seed():
        async with aiosqlite.connect(str(test_db)) as conn:
            doc_exists = await conn.execute(
                "SELECT id FROM documents WHERE slug = ?", ("test-codex",)
            )
            if not await doc_exists.fetchone():
                await conn.execute(
                    "INSERT INTO documents (slug, title, doc_type) VALUES (?, ?, ?)",
                    ("test-codex", "Тестовый кодекс", "codex"),
                )
            for num in ("1", "2"):
                exists = await conn.execute(
                    "SELECT 1 FROM articles WHERE document_id=1 AND article_number=?", (num,)
                )
                if not await exists.fetchone():
                    await conn.execute(
                        "INSERT INTO articles (document_id, article_number, title, content) VALUES (1, ?, ?, ?)",
                        (num, f"Статья {num}", f"Содержание статьи {num}. Тестовый текст для поиска."),
                    )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()
