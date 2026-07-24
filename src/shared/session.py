import asyncio
import json
import logging

import aiosqlite

from src.shared.database import DB_PATH

log = logging.getLogger("legal_bot.session")

MAX_SESSION_MESSAGES = 30

_USER_LOCKS: dict[int, asyncio.Lock] = {}
_USER_LOCKS_LOCK = asyncio.Lock()


async def _user_lock(user_id: int) -> asyncio.Lock:
    async with _USER_LOCKS_LOCK:
        if user_id not in _USER_LOCKS:
            _USER_LOCKS[user_id] = asyncio.Lock()
        return _USER_LOCKS[user_id]


async def init_sessions():
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT 'Основная',
                messages TEXT NOT NULL DEFAULT '[]',
                document_text TEXT DEFAULT NULL,
                document_name TEXT DEFAULT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES sessions_v2(id) ON DELETE CASCADE
            );
        """)
        await conn.commit()
    await _migrate_old_sessions()


async def _migrate_old_sessions():
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        try:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            if not await cursor.fetchone():
                return
            cur2 = await conn.execute(
                "SELECT chat_id, messages, document_text, document_name FROM sessions"
            )
            rows = await cur2.fetchall()
            migrated = 0
            for chat_id, messages_json, doc_text, doc_name in rows:
                if chat_id <= 0:
                    continue
                user_id = chat_id
                existing = await conn.execute(
                    "SELECT 1 FROM sessions_v2 WHERE user_id = ?", (user_id,)
                )
                if await existing.fetchone():
                    continue
                try:
                    msgs = json.loads(messages_json) if messages_json else []
                except (json.JSONDecodeError, TypeError):
                    msgs = []
                cursor = await conn.execute(
                    "INSERT INTO sessions_v2 (user_id, name, messages, document_text, document_name) "
                    "VALUES (?, 'Основная', ?, ?, ?)",
                    (user_id, json.dumps(msgs, ensure_ascii=False), doc_text, doc_name),
                )
                sid = cursor.lastrowid
                await conn.execute(
                    "INSERT OR IGNORE INTO active_sessions (user_id, session_id) VALUES (?, ?)",
                    (user_id, sid),
                )
                migrated += 1
            await conn.commit()
            if migrated:
                log.info(f"Migrated {migrated} old sessions to sessions_v2")
        except Exception as e:
            log.info(f"Session migration check: {e}")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _ensure_active_session(user_id: int) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT session_id FROM active_sessions WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            cur2 = await conn.execute(
                "SELECT 1 FROM sessions_v2 WHERE id = ? AND user_id = ?", (row[0], user_id)
            )
            if await cur2.fetchone():
                return row[0]
        cursor2 = await conn.execute(
            "SELECT id FROM sessions_v2 WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user_id,),
        )
        row2 = await cursor2.fetchone()
        if row2:
            sid = row2[0]
            await conn.execute(
                "INSERT OR REPLACE INTO active_sessions (user_id, session_id) VALUES (?, ?)",
                (user_id, sid),
            )
            await conn.commit()
            return sid
        cursor3 = await conn.execute(
            "INSERT INTO sessions_v2 (user_id, name) VALUES (?, 'Основная')",
            (user_id,),
        )
        sid = cursor3.lastrowid
        await conn.execute(
            "INSERT OR REPLACE INTO active_sessions (user_id, session_id) VALUES (?, ?)",
            (user_id, sid),
        )
        await conn.commit()
        return sid


async def list_sessions(user_id: int) -> list[tuple[int, str]]:
    async with await _user_lock(user_id):
        active_id = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            cursor = await conn.execute(
                "SELECT id, name FROM sessions_v2 WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        result = [(sid, name) for sid, name in rows]
        if result:
            active_idx = next((i for i, (sid, _) in enumerate(result) if sid == active_id), 0)
            result[0], result[active_idx] = result[active_idx], result[0]
        return result


async def create_session(user_id: int, name: str) -> tuple[int, str]:
    async with await _user_lock(user_id):
        name = name[:50]
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            cursor = await conn.execute(
                "INSERT INTO sessions_v2 (user_id, name) VALUES (?, ?)",
                (user_id, name),
            )
            sid = cursor.lastrowid
            await conn.execute(
                "INSERT OR REPLACE INTO active_sessions (user_id, session_id) VALUES (?, ?)",
                (user_id, sid),
            )
            await conn.commit()
        return sid, name


async def switch_session(user_id: int, session_id: int) -> bool:
    async with await _user_lock(user_id):
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM sessions_v2 WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            )
            if not await cursor.fetchone():
                return False
            await conn.execute(
                "INSERT OR REPLACE INTO active_sessions (user_id, session_id) VALUES (?, ?)",
                (user_id, session_id),
            )
            await conn.commit()
        return True


async def delete_session(user_id: int) -> str:
    async with await _user_lock(user_id):
        active_id = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sessions_v2 WHERE id = ? AND user_id = ?",
                (active_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return ""
            name = row[0]
            await conn.execute("DELETE FROM sessions_v2 WHERE id = ? AND user_id = ?", (active_id, user_id))
            await conn.commit()
        await _ensure_active_session(user_id)
        return name


async def load_session(user_id: int) -> tuple[list[dict], str | None, str | None]:
    async with await _user_lock(user_id):
        sid = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            cursor = await conn.execute(
                "SELECT messages, document_text, document_name FROM sessions_v2 WHERE id = ? AND user_id = ?",
                (sid, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return [], None, None
        try:
            messages = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            messages = []
        return messages, row[1], row[2]


async def save_session(user_id: int, messages: list[dict], document_text: str | None = None, document_name: str | None = None):
    async with await _user_lock(user_id):
        sid = await _ensure_active_session(user_id)
        trimmed = messages[-MAX_SESSION_MESSAGES:] if len(messages) > MAX_SESSION_MESSAGES else messages
        raw = json.dumps(trimmed, ensure_ascii=False)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "UPDATE sessions_v2 SET messages = ?, document_text = COALESCE(?, document_text), "
                "document_name = COALESCE(?, document_name), updated_at = ? WHERE id = ? AND user_id = ?",
                (raw, document_text, document_name, _now(), sid, user_id),
            )
            await conn.commit()


async def clear_session_history(user_id: int):
    async with await _user_lock(user_id):
        sid = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "UPDATE sessions_v2 SET messages = '[]', document_text = NULL, document_name = NULL, updated_at = ? WHERE id = ? AND user_id = ?",
                (_now(), sid, user_id),
            )
            await conn.commit()


async def save_document_to_session(user_id: int, text: str, name: str):
    async with await _user_lock(user_id):
        sid = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "UPDATE sessions_v2 SET document_text = ?, document_name = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (text, name, _now(), sid, user_id),
            )
            await conn.commit()


async def rename_session(user_id: int, new_name: str):
    async with await _user_lock(user_id):
        sid = await _ensure_active_session(user_id)
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "UPDATE sessions_v2 SET name = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (new_name[:50], _now(), sid, user_id),
            )
            await conn.commit()
