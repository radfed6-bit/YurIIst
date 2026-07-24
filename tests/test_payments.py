import aiosqlite
import pytest

from src.shared.database import DB_PATH
from src.shared.payments import (
    ADMIN_ID,
    activate_subscription,
    check_daily_limit,
    check_document_limit,
    cleanup_expired_subscriptions,
    get_user_tier,
    increment_document_usage,
    increment_usage,
    server_cancel_subscription,
    try_activate_trial,
)


@pytest.mark.asyncio
async def test_get_user_tier_free_default(test_db):
    tier, until = await get_user_tier(999999)
    assert tier == "free"
    assert until is None


@pytest.mark.asyncio
async def test_activate_subscription_success(test_db):
    ok = await activate_subscription(100, "plus", "ch_001")
    assert ok is True
    tier, until = await get_user_tier(100)
    assert tier == "plus"
    assert until is not None


@pytest.mark.asyncio
async def test_activate_subscription_rejects_duplicate_charge_id(test_db):
    ok1 = await activate_subscription(100, "plus", "ch_dup")
    assert ok1 is True
    ok2 = await activate_subscription(200, "pro", "ch_dup")
    assert ok2 is False


@pytest.mark.asyncio
async def test_activate_subscription_same_user_new_charge(test_db):
    ok1 = await activate_subscription(100, "plus", "ch_a")
    assert ok1 is True
    ok2 = await activate_subscription(100, "pro", "ch_b")
    assert ok2 is True
    tier, _ = await get_user_tier(100)
    assert tier == "pro"


@pytest.mark.asyncio
async def test_get_user_tier_admin(test_db):
    tier, _ = await get_user_tier(ADMIN_ID)
    assert tier == "pro"


@pytest.mark.asyncio
async def test_try_activate_trial_success(test_db):
    ok = await try_activate_trial(300)
    assert ok is True
    tier, until = await get_user_tier(300)
    assert tier == "plus"
    assert until is not None


@pytest.mark.asyncio
async def test_try_activate_trial_once(test_db):
    ok1 = await try_activate_trial(400)
    assert ok1 is True
    ok2 = await try_activate_trial(400)
    assert ok2 is False


@pytest.mark.asyncio
async def test_try_activate_trial_admin(test_db):
    ok = await try_activate_trial(ADMIN_ID)
    assert ok is False


@pytest.mark.asyncio
async def test_server_cancel_subscription(test_db):
    await activate_subscription(500, "pro", "ch_cancel")
    ok = await server_cancel_subscription(500)
    assert ok is True
    tier, _ = await get_user_tier(500)
    assert tier == "free"


@pytest.mark.asyncio
async def test_server_cancel_free_user(test_db):
    ok = await server_cancel_subscription(600)
    assert ok is False


@pytest.mark.asyncio
async def test_check_daily_limit_free(test_db):
    allowed, remaining, tier = await check_daily_limit(700)
    assert allowed is True
    assert remaining == 5
    assert tier == "free"


@pytest.mark.asyncio
async def test_check_daily_limit_exhausted(test_db):
    uid = 800
    for _ in range(5):
        await increment_usage(uid)
    allowed, remaining, _ = await check_daily_limit(uid)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_check_daily_limit_admin(test_db):
    allowed, remaining, tier = await check_daily_limit(ADMIN_ID)
    assert allowed is True
    assert remaining == 999
    assert tier == "pro"


@pytest.mark.asyncio
async def test_check_document_limit_free(test_db):
    allowed, remaining, tier = await check_document_limit(900)
    assert allowed is True
    assert remaining == 1


@pytest.mark.asyncio
async def test_check_document_limit_exhausted(test_db):
    uid = 1000
    await increment_document_usage(uid)
    allowed, remaining, _ = await check_document_limit(uid)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_concurrent_subscriptions_no_race(test_db):
    import asyncio
    results = await asyncio.gather(
        activate_subscription(1100, "plus", "ch_race"),
        activate_subscription(1101, "plus", "ch_race"),
    )
    true_count = sum(1 for r in results if r is True)
    assert true_count == 1, f"Only 1 should succeed, got {true_count}"


@pytest.mark.asyncio
async def test_cleanup_expired_subscriptions_none(test_db):
    count = await cleanup_expired_subscriptions()
    assert count == 0


@pytest.mark.asyncio
async def test_cleanup_expired_subscriptions_removes_expired(test_db):
    await activate_subscription(200, "plus", "ch_exp1")
    import aiosqlite
    from src.shared.database import DB_PATH as db
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            "UPDATE subscriptions SET active_until = ? WHERE user_id = 200",
            (past,),
        )
        await conn.commit()
    count = await cleanup_expired_subscriptions()
    assert count == 1
    tier, _ = await get_user_tier(200)
    assert tier == "free"


@pytest.mark.asyncio
async def test_cleanup_skips_active_subscriptions(test_db):
    await activate_subscription(300, "pro", "ch_actv")
    count = await cleanup_expired_subscriptions()
    assert count == 0
    tier, _ = await get_user_tier(300)
    assert tier == "pro"
