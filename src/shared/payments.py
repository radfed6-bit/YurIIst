import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from src.config import settings
from src.shared.database import DB_PATH, init_db

log = logging.getLogger("legal_bot.payments")

ADMIN_ID = settings.admin_telegram_id

PLANS = {
    "plus": {"stars": 150, "daily_limit": 50, "doc_limit": 10, "label": "Plus"},
    "pro": {"stars": 700, "daily_limit": float("inf"), "doc_limit": float("inf"), "label": "Pro"},
}
LIMITS = {"free": 5, "plus": 50, "pro": float("inf")}
DOC_LIMITS = {"free": 1, "plus": 10, "pro": float("inf")}
TRIAL_DURATION = timedelta(days=1)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_user_tier(user_id: int) -> tuple[str, str | None]:
    if user_id == ADMIN_ID:
        return "pro", None
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT tier, active_until, trial_used FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return "free", None
    tier, active_until, trial_used = row
    if active_until:
        try:
            until = datetime.strptime(active_until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > until:
                await _set_tier(user_id, "free", None)
                return "free", None
        except ValueError:
            pass
    return tier, active_until


async def server_cancel_subscription(user_id: int) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT tier FROM subscriptions WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row or row[0] == "free":
            return False
        await conn.execute(
            "UPDATE subscriptions SET tier = 'free', active_until = NULL, updated_at = ? WHERE user_id = ?",
            (_now(), user_id),
        )
        await conn.commit()
    log.info(f"Subscription cancelled server-side for user {user_id} (was {row[0]})")
    return True


async def _set_tier(user_id: int, tier: str, active_until: str | None, charge_id: str | None = None):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, tier, active_until, telegram_payment_charge_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET tier=excluded.tier, active_until=excluded.active_until, "
            "telegram_payment_charge_id=COALESCE(excluded.telegram_payment_charge_id, telegram_payment_charge_id), "
            "updated_at=excluded.updated_at",
            (user_id, tier, active_until, charge_id, _now()),
        )
        await conn.commit()


async def _mark_trial_used(user_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, trial_used, updated_at) VALUES (?, 1, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET trial_used=1, updated_at=excluded.updated_at",
            (user_id, _now()),
        )
        await conn.commit()


async def try_activate_trial(user_id: int) -> bool:
    if ADMIN_ID and user_id == ADMIN_ID:
        return False
    until = (datetime.now(timezone.utc) + TRIAL_DURATION).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT tier, active_until, trial_used FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            if row[2]:
                return False
            if row[0] != "free" and row[1]:
                try:
                    existing = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) < existing:
                        return False
                except ValueError:
                    pass
        await conn.execute(
            "INSERT INTO subscriptions (user_id, tier, active_until, trial_used, updated_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "tier=excluded.tier, active_until=excluded.active_until, "
            "trial_used=1, updated_at=excluded.updated_at",
            (user_id, "plus", until, _now()),
        )
        await conn.commit()
    return True


async def activate_subscription(user_id: int, tier: str, charge_id: str) -> bool:
    until = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "INSERT INTO subscriptions (user_id, tier, active_until, telegram_payment_charge_id, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "tier=excluded.tier, active_until=excluded.active_until, "
                "telegram_payment_charge_id=excluded.telegram_payment_charge_id, "
                "updated_at=excluded.updated_at",
                (user_id, tier, until, charge_id, _now()),
            )
            await conn.commit()
        log.info(f"Subscription activated: user={user_id} tier={tier} charge_id={charge_id} until={until}")
        return True
    except aiosqlite.IntegrityError:
        log.warning(f"Duplicate charge_id {charge_id} for user {user_id}")
        return False


async def check_daily_limit(user_id: int) -> tuple[bool, int, str]:
    if user_id == ADMIN_ID:
        return True, 999, "pro"
    tier, _ = await get_user_tier(user_id)
    limit = LIMITS.get(tier, 5)
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT count FROM daily_usage WHERE user_id = ? AND date = ?",
            (user_id, _today()),
        )
        row = await cursor.fetchone()
    used = row[0] if row else 0
    remaining = limit - used
    if remaining <= 0:
        return False, 0, tier
    return True, remaining, tier


async def increment_usage(user_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.execute(
            "INSERT INTO daily_usage (user_id, date, count) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
            (user_id, _today()),
        )
        await conn.commit()


async def check_document_limit(user_id: int) -> tuple[bool, int, str]:
    if user_id == ADMIN_ID:
        return True, 999, "pro"
    tier, _ = await get_user_tier(user_id)
    limit = DOC_LIMITS.get(tier, 1)
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT count FROM daily_doc_usage WHERE user_id = ? AND date = ?",
            (user_id, _today()),
        )
        row = await cursor.fetchone()
    used = row[0] if row else 0
    remaining = limit - used
    if remaining <= 0:
        return False, 0, tier
    return True, remaining, tier


async def increment_document_usage(user_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.execute(
            "INSERT INTO daily_doc_usage (user_id, date, count) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
            (user_id, _today()),
        )
        await conn.commit()


async def get_subscription_info(user_id: int) -> dict:
    tier, active_until = await get_user_tier(user_id)
    allowed, remaining, _ = await check_daily_limit(user_id)
    used = 0 if tier == "pro" else (await _get_daily_usage(user_id))
    doc_limit = DOC_LIMITS.get(tier, 1)
    doc_used = await _get_daily_doc_usage(user_id)
    return {
        "tier": tier,
        "active_until": active_until,
        "daily_used": used,
        "daily_remaining": remaining,
        "daily_limit": LIMITS.get(tier, 5),
        "doc_limit": doc_limit,
        "doc_used": doc_used,
        "is_admin": user_id == ADMIN_ID,
    }


async def cleanup_expired_subscriptions() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT user_id, tier, active_until FROM subscriptions "
            "WHERE active_until IS NOT NULL AND active_until < ? AND tier != 'free'",
            (now,),
        )
        expired = await cursor.fetchall()
        if expired:
            for uid, old_tier, until in expired:
                await conn.execute(
                    "UPDATE subscriptions SET tier = 'free', active_until = NULL, updated_at = ? WHERE user_id = ?",
                    (now, uid),
                )
                log.info(f"Expired subscription cleaned up: user={uid} old_tier={old_tier} active_until={until}")
            await conn.commit()
    return len(expired)


async def _get_daily_usage(user_id: int) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT count FROM daily_usage WHERE user_id = ? AND date = ?",
            (user_id, _today()),
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def _get_daily_doc_usage(user_id: int) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT count FROM daily_doc_usage WHERE user_id = ? AND date = ?",
            (user_id, _today()),
        )
        row = await cursor.fetchone()
    return row[0] if row else 0
