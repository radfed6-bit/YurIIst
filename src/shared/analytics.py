import json
import logging

import aiosqlite

from src.shared.database import DB_PATH

log = logging.getLogger("legal_bot.analytics")


async def track_event(user_id: int, event_name: str, properties: dict | None = None) -> None:
    if properties is None:
        properties = {}
    try:
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "INSERT INTO events (user_id, event_name, properties) VALUES (?, ?, ?)",
                (user_id, event_name, json.dumps(properties, ensure_ascii=False)),
            )
            await conn.commit()
    except Exception as e:
        log.warning(f"track_event error: {e}")
