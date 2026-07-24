import aiosqlite
import pytest

from src.shared.analytics import track_event
from src.shared.database import DB_PATH


@pytest.mark.asyncio
async def test_track_event(test_db):
    await track_event(1, "test", {"key": "val"})
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT user_id, event_name, properties FROM events")
        row = await cursor.fetchone()
    assert row[0] == 1
    assert row[1] == "test"
    assert '"key": "val"' in row[2]


@pytest.mark.asyncio
async def test_track_event_default_props(test_db):
    await track_event(2, "no_props")
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT properties FROM events WHERE user_id=2")
        row = await cursor.fetchone()
    assert row[0] == "{}"


@pytest.mark.asyncio
async def test_track_event_never_crashes(test_db):
    await track_event(3, "ok")
    # даже если передать None
    await track_event(4, "test", None)
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM events")
        count = (await cursor.fetchone())[0]
    assert count == 2


@pytest.mark.asyncio
async def test_events_indexed_for_query(test_db):
    import random
    uid = random.randint(10000, 99999)
    for i in range(5):
        await track_event(uid, "search", {"q": f"query{i}"})
    async with aiosqlite.connect(str(test_db)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT event_name, COUNT(*) as cnt FROM events WHERE user_id=? GROUP BY event_name",
            (uid,),
        )
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["cnt"] == 5
