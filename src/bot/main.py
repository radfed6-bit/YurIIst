import asyncio
import logging
import re
import time
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest

from src.agent import agent
from src.shared.analytics import track_event
from src.shared.database import init_db
from src.shared.payments import (
    ADMIN_ID,
    DOC_LIMITS,
    PLANS,
    activate_subscription,
    check_daily_limit,
    check_document_limit,
    cleanup_expired_subscriptions,
    get_subscription_info,
    get_user_tier,
    increment_document_usage,
    increment_usage,
    server_cancel_subscription,
    try_activate_trial,
)

from src.agent.document_parser import download_and_parse
from src.shared.session import (
    clear_session_history,
    create_session,
    delete_session,
    list_sessions,
    load_session,
    rename_session,
    save_document_to_session,
    save_session,
    switch_session,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("legal_bot")

TELEGRAM_TOKEN = ""
OPENDCODE_API_KEY = ""

_AI_TASKS: dict[int, asyncio.Task] = {}  # chat_id -> task
_AI_TASKS_LOCK = asyncio.Lock()

_USER_LLM_LIMIT: dict[int, list[float]] = {}
_USER_LLM_LOCK = asyncio.Lock()
_LLM_WINDOW = 60
_LLM_MAX_CALLS = 10


async def _check_llm_rate_limit(user_id: int) -> bool:
    now = time.monotonic()
    async with _USER_LLM_LOCK:
        timestamps = _USER_LLM_LIMIT.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < _LLM_WINDOW]
        if len(timestamps) >= _LLM_MAX_CALLS:
            return False
        timestamps.append(now)
        _USER_LLM_LIMIT[user_id] = timestamps
    return True


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    trial = await try_activate_trial(uid)
    await track_event(uid, "start", {"trial_activated": trial})
    text = (
        "⚖️ *ЮрИИст* — юридический AI-ассистент по кодексам РФ\n\n"
        "Просто напиши вопрос — AI найдёт ответ в кодексах РФ\n"
        "⏳ Бот может думать до 5 минут — это нормально. Чем дольше, тем точнее ответ.\n\n"
        "📊 *Тарифы:*\n"
        "• Free — 5 запросов/день\n"
        f"• Plus — {PLANS['plus']['stars']} ⭐/мес, 50 запросов/день\n"
        f"• Pro — {PLANS['pro']['stars']} ⭐/мес, безлимит\n\n"
        "Команды:\n"
        "`/subscribe` — выбрать тариф\n"
        "`/myplan` — мой тариф и статистика\n"
        "`/sessions` — управление сессиями\n"
        "`/reset` — очистить историю текущей сессии\n"
        "`/help` — справка"
    )
    if trial:
        text += "\n\n🎁 *Пробный Plus на 24 часа активирован!*"
    await update.message.reply_text(text, parse_mode="Markdown")


async def reset_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await clear_session_history(uid)
    await track_event(uid, "session_reset")
    await update.message.reply_text("🔄 История и документ текущей сессии очищены.")


MAX_MSG = 4096


def _fix_tables(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.count("|") >= 3:
            if re.match(r'^\|[-:\s]+\|[-:\s]+\|', stripped):
                continue
            parts = [p.strip() for p in stripped.split("|")]
            parts = [p for p in parts if p]
            if parts:
                if len(parts) == 1:
                    result.append(f"• {parts[0]}")
                else:
                    result.append(f"• **{parts[0]}** — {' — '.join(parts[1:])}")
        else:
            result.append(line)
    return "\n".join(result)


def _split_message(text: str) -> list[str]:
    if len(text) <= MAX_MSG:
        return [text]
    parts = []
    while len(text) > MAX_MSG:
        split = text.rfind("\n\n", 0, MAX_MSG)
        if split <= 0:
            split = text.rfind("\n", 0, MAX_MSG)
        if split <= 0:
            split = MAX_MSG
        chunk = text[:split]
        if chunk:
            parts.append(chunk)
        skip = split
        while skip < len(text) and text[skip] == '\n':
            skip += 1
        text = text[skip:]
    if text:
        parts.append(text)
    return parts


async def _run_ai_and_edit(bot, chat_id: int, message_id: int, question: str, user_id: int):
    this_task = asyncio.current_task()
    history, doc_text, doc_name = await load_session(user_id)

    async def progress_update(text: str):
        try:
            truncated = text[:3500]
            await bot.edit_message_text(
                f"🤔 *Размышляю...*\n\n{truncated}",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown",
            )
        except Exception as e:
            log.warning(f"Progress update failed: {e}")

    try:
        answer, sources, updated_history, thoughts = await asyncio.wait_for(
            agent.run(
                user_query=question,
                api_key=OPENDCODE_API_KEY,
                user_id=user_id,
                chat_id=chat_id,
                messages_history=history,
                document_text=doc_text,
                progress_callback=progress_update,
            ),
            timeout=300,
        )
        await save_session(user_id, updated_history)
        await increment_usage(user_id)

        answer = _fix_tables(answer)

        if sources:
            answer += "\n\n📌 *Источники:* " + ", ".join(sources[:8])
        answer += "\n\n⚠️ *Ответ носит информационный характер, не является юридической консультацией.*"

        thinking_block = "\n".join(thoughts) if thoughts else ""
        if thinking_block:
            thinking_block = _fix_tables(thinking_block)
            full_text = f"🤔 *Размышления:*\n{thinking_block}\n\n━━━━━━━━━━━━━━━\n\n{answer}"
        else:
            full_text = answer

        parts = _split_message(full_text)
        await bot.edit_message_text(parts[0], chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
        for part in parts[1:]:
            await bot.send_message(chat_id=chat_id, text=part, parse_mode="Markdown")
    except Exception as e:
        log.warning(f"AI task error: {e}")
        try:
            await bot.edit_message_text("⚠️ Ошибка при обработке запроса", chat_id=chat_id, message_id=message_id)
        except Exception as e2:
            log.warning(f"Error message edit failed: {e2}")
    finally:
        async with _AI_TASKS_LOCK:
            if _AI_TASKS.get(chat_id) is this_task:
                _AI_TASKS.pop(chat_id, None)


async def subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"Plus — {PLANS['plus']['stars']} ⭐/мес", callback_data="sub_plus")],
        [InlineKeyboardButton(f"Pro — {PLANS['pro']['stars']} ⭐/мес", callback_data="sub_pro")],
    ]
    await update.message.reply_text(
        "Выбери тариф:\n\n"
        f"• *Plus* — {PLANS['plus']['stars']} ⭐/мес, 50 запросов/день, 10 документов/день\n"
        f"• *Pro* — {PLANS['pro']['stars']} ⭐/мес, безлимит запросов и документов\n\n"
        "Бесплатно: 5 запросов/день, 1 документ/день.\n\n"
        "Оплата через Telegram Stars. После оплаты подписка действует 30 дней.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def subscribe_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tier = query.data.split("_")[1]
    stars = PLANS[tier]["stars"]
    link = await ctx.bot.create_invoice_link(
        title=f"ЮрИИст {PLANS[tier]['label']}",
        description=f"Подписка {PLANS[tier]['label']} на 30 дней",
        payload=tier,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(f"{PLANS[tier]['label']} 30 дней", stars)],
        subscription_period=2592000,
    )
    await query.edit_message_text(
        f"💳 *Оплата подписки {PLANS[tier]['label']}*\n\n"
        f"Нажми кнопку ниже, чтобы оплатить {stars} ⭐:\n"
        f"{link}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Оплатить {stars} ⭐", url=link)]
        ]),
    )


async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.pre_checkout_query
    tier = q.invoice_payload
    expected = PLANS.get(tier, {}).get("stars")
    if not expected or q.total_amount != expected:
        await q.answer(ok=False, error_message="Ошибка: неверная сумма")
        return
    if q.currency != "XTR":
        await q.answer(ok=False, error_message="Ошибка: неверная валюта")
        return
    await q.answer(ok=True)


async def successful_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    charge_id = update.message.successful_payment.telegram_payment_charge_id
    tier = update.message.successful_payment.invoice_payload
    ok = await activate_subscription(user_id, tier, charge_id)
    await track_event(user_id, "subscription_purchased", {"tier": tier, "charge_id": charge_id, "success": ok})
    if not ok:
        return  # дубликат — уже обработан
    await update.message.reply_text(
        f"✅ Оплата прошла! Тариф *{PLANS[tier]['label']}* активирован на 30 дней.\n"
        "Задавай вопросы — я помогу!",
        parse_mode="Markdown",
    )


async def cancel_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ok = await server_cancel_subscription(user_id)
    await track_event(user_id, "subscription_cancelled", {"success": ok})
    if not ok:
        await update.message.reply_text("У тебя и так бесплатный тариф.")
        return
    await update.message.reply_text(
        "✅ Подписка отменена. Ты переведён на бесплатный тариф.\n"
        "Чтобы отменить recurring-платеж в Telegram, открой *Настройки* → *Звёзды*.",
        parse_mode="Markdown",
    )


async def admin_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("Эта команда только для администратора.")
        return
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "📋 *Команды администратора:*\n\n"
            "`/admin status <user_id>` — информация о пользователе\n"
            "`/admin grant <user_id> plus|pro` — выдать подписку на 30 дней\n"
            "`/admin revoke <user_id>` — отменить подписку\n"
            "`/admin cleanup` — принудительная очистка истекших подписок",
            parse_mode="Markdown",
        )
        return
    cmd = args[0].lower()
    if cmd == "cleanup":
        count = await cleanup_expired_subscriptions()
        await update.message.reply_text(f"🧹 Очищено {count} просроченных подписок.")
        return
    if len(args) < 2:
        await update.message.reply_text("Укажи user_id.")
        return
    try:
        target = int(args[1])
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
        return
    if cmd == "status":
        info = await get_subscription_info(target)
        lines = [
            f"📊 *Пользователь*: `{target}`",
            f"Тариф: *{info['tier'].capitalize()}*",
        ]
        if info["active_until"]:
            lines.append(f"Действует до: `{info['active_until']}`")
        if info["tier"] != "pro":
            lines.append(f"Запросов: {info['daily_used']}/{info['daily_limit']}")
            lines.append(f"Документов: {info['doc_used']}/{info['doc_limit']}")
        if info["is_admin"]:
            lines.append("👑 Администратор")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    elif cmd == "grant":
        if len(args) < 3:
            await update.message.reply_text("Укажи tier: `/admin grant <user_id> plus|pro`", parse_mode="Markdown")
            return
        tier = args[2].lower()
        if tier not in ("plus", "pro"):
            await update.message.reply_text("Tier может быть только `plus` или `pro`.", parse_mode="Markdown")
            return
        ok = await activate_subscription(target, tier, f"admin_{uid}_{int(time.time())}")
        if not ok:
            await update.message.reply_text("❌ Не удалось активировать (возможно, дубликат charge_id).")
            return
        admin_name = update.effective_user.first_name or str(uid)
        log.info(f"Admin {admin_name} ({uid}) granted {tier} to user {target}")
        await update.message.reply_text(f"✅ Выдан тариф *{PLANS[tier]['label']}* пользователю `{target}` на 30 дней.", parse_mode="Markdown")
    elif cmd == "revoke":
        ok = await server_cancel_subscription(target)
        if not ok:
            await update.message.reply_text(f"❌ У пользователя `{target}` и так бесплатный тариф.", parse_mode="Markdown")
            return
        admin_name = update.effective_user.first_name or str(uid)
        log.info(f"Admin {admin_name} ({uid}) revoked subscription for user {target}")
        await update.message.reply_text(f"✅ Подписка пользователя `{target}` отменена.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Неизвестная команда: `{cmd}`", parse_mode="Markdown")


async def myplan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    info = await get_subscription_info(update.effective_user.id)
    parts = [f"📊 *Мой тариф:* **{info['tier'].capitalize()}**"]
    if info["is_admin"]:
        parts.append("👑 Администратор — безлимитный доступ")
    elif info["tier"] == "free":
        parts.append(f"Запросов: *{info['daily_used']}* / *{info['daily_limit']}*")
        parts.append(f"Документов: *{info['doc_used']}* / *{info['doc_limit']}*")
        parts.append("Купи подписку: /subscribe")
    elif info["tier"] == "pro":
        parts.append("♾️ Безлимит запросов и документов")
        if info["active_until"]:
            parts.append(f"Действует до: *{info['active_until']}*")
    else:
        parts.append(f"Запросов: *{info['daily_used']}* / *{info['daily_limit']}*")
        parts.append(f"Документов: *{info['doc_used']}* / *{info['doc_limit']}*")
        if info["active_until"]:
            parts.append(f"Действует до: *{info['active_until']}*")
    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


async def sessions_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions = await list_sessions(uid)
    if not sessions:
        await update.message.reply_text("Нет сессий. Создай: /session_create <название>")
        return
    lines = ["📁 *Твои сессии:*\n"]
    buttons = []
    row = []
    for sid, name in sessions:
        display = name[:20]
        row.append(InlineKeyboardButton(display, callback_data=f"sw_{sid}"))
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("➕ Новая", callback_data="sess_create"),
        InlineKeyboardButton("✏️ Переименовать", callback_data="sess_rename"),
    ])
    buttons.append([
        InlineKeyboardButton("🗑 Удалить текущую", callback_data="sess_delete"),
    ])
    for sid, name in sessions:
        marker = " ◀️ (текущая)" if sid == sessions[0][0] else ""
        lines.append(f"• `{name[:30]}`{marker}")
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def session_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = ctx.args
    if not args:
        await update.message.reply_text("Использование: /session_create <название>\nПример: /session_create Налоговый спор")
        return
    name = " ".join(args)[:50]
    await create_session(uid, name)
    await track_event(uid, "session_created", {"name": name})
    await update.message.reply_text(f"✅ Сессия «{name}» создана и активирована.")


async def session_delete_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions = await list_sessions(uid)
    if len(sessions) <= 1:
        await update.message.reply_text("Нельзя удалить единственную сессию.")
        return
    await update.message.reply_text(
        "🗑 Удалить текущую сессию? История будет потеряна.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Да, удалить", callback_data="sess_delete_confirm")]
        ]),
    )


async def session_rename(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = ctx.args
    if not args:
        await update.message.reply_text("Использование: /session rename <новое название>\nПример: /session rename Налоговое планирование")
        return
    parts = args[:]
    if parts[0].lower() == "rename":
        parts = parts[1:]
    if not parts:
        await update.message.reply_text("Укажи новое название: /session rename <новое название>")
        return
    name = " ".join(parts)[:50]
    await rename_session(uid, name)
    await update.message.reply_text(f"✏️ Сессия переименована в «{name}».")


async def sessions_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    data = q.data

    if data == "sess_create":
        await q.edit_message_text("Используй команду: /session_create <название>\nПример: /session_create Налоговый спор")
        return
    if data == "sess_rename":
        await q.edit_message_text("Используй команду: /session rename <новое название>\nПример: /session rename Налоговое планирование")
        return
    if data == "sess_delete_confirm":
        sessions = await list_sessions(uid)
        if len(sessions) <= 1:
            await q.edit_message_text("Нельзя удалить единственную сессию.")
            return
        deleted_name = await delete_session(uid)
        await q.edit_message_text(f"🗑 Сессия «{deleted_name}» удалена. Переключился на следующую.")
        return
    if data.startswith("sw_"):
        sid = int(data[3:])
        sessions = await list_sessions(uid)
        names = {s[0]: s[1] for s in sessions}
        ok = await switch_session(uid, sid)
        if not ok:
            await q.edit_message_text("Сессия не найдена.")
            return
        name = names.get(sid, "?")
        await q.edit_message_text(f"🔀 Переключился на сессию «{name}».")
        return
    tier, _ = await get_user_tier(update.effective_user.id)
    if tier == "free":
        await update.message.reply_text("У тебя и так бесплатный тариф.")
        return
    await update.message.reply_text(
        "Чтобы отменить подписку:\n"
        "1. Открой *Настройки Telegram* → *Звёзды*\n"
        "2. Найди «ЮрИИст» в списке активных подписок\n"
        "3. Нажми «Отменить»\n\n"
        "После отмены текущий период до конца оплачен.",
        parse_mode="Markdown",
    )


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return
    uid = update.effective_user.id

    MAX_DOC_SIZE = 5 * 1024 * 1024
    if doc.file_size and doc.file_size > MAX_DOC_SIZE:
        await update.message.reply_text("❌ Файл слишком большой. Максимум 5 МБ.")
        return

    allowed, remaining, tier = await check_document_limit(uid)
    if not allowed:
        text = "❌ Дневной лимит загрузки документов исчерпан.\n"
        if tier == "free":
            text += "Завтра лимит обновится (1 документ/день). Или купи подписку: /subscribe"
        elif tier == "plus":
            text += "Купи Pro для безлимита: /subscribe"
        else:
            text += "Купи подписку: /subscribe"
        await update.message.reply_text(text)
        await track_event(uid, "daily_limit_reached", {"context": "document", "tier": tier})
        return

    msg = await update.message.reply_text("📄 Обрабатываю файл...")
    result = await download_and_parse(update.get_bot(), doc.file_id, doc.file_name or "file", doc.mime_type or "")

    if "error" in result:
        await msg.edit_text(f"❌ {result['error']}")
        return

    text = result["text"]
    name = result["name"]
    chars = result["chars"]

    await save_document_to_session(uid, text, name)
    await increment_document_usage(uid)
    await track_event(uid, "document_uploaded", {"name": name, "chars": chars})
    await msg.edit_text(
        f"📄 *{name}* получен ({chars} символов).\n\n"
        "Можешь задавать вопросы — я учту содержимое документа при ответе.\n"
        "Отправить другой файл или `/reset` — документ будет забыт.",
        parse_mode="Markdown",
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    if len(question) < 3 or len(question) > 4096:
        return

    user_id = update.effective_user.id
    allowed, remaining, tier = await check_daily_limit(user_id)
    if not allowed:
        text = "❌ Дневной лимит запросов исчерпан.\n"
        if tier == "free":
            text += "Завтра лимит обновится. Или купи подписку: /subscribe"
        else:
            text += "Купи подписку: /subscribe"
        await update.message.reply_text(text)
        await track_event(user_id, "daily_limit_reached", {"context": "question", "tier": tier})
        return

    if not await _check_llm_rate_limit(user_id):
        await update.message.reply_text("⏳ Слишком много запросов. Подожди минуту.")
        return

    async with _AI_TASKS_LOCK:
        prev = _AI_TASKS.pop(update.effective_chat.id, None)
        if prev and not prev.done():
            prev.cancel()

    msg = await update.message.reply_text("🤔 *Запускаю ЮрИИста...*", parse_mode="Markdown")
    task = asyncio.create_task(_run_ai_and_edit(
        bot=update.get_bot(),
        chat_id=update.effective_chat.id,
        message_id=msg.message_id,
        question=question,
        user_id=user_id,
    ))
    async with _AI_TASKS_LOCK:
        _AI_TASKS[update.effective_chat.id] = task


def main():
    import os
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)

    global TELEGRAM_TOKEN, OPENDCODE_API_KEY
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OPENDCODE_API_KEY = os.getenv("OPENCODE_ZEN_API_KEY", "")

    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN не указан в .env")
        return

    log.info(f"Bot token configured: {'yes' if TELEGRAM_TOKEN else 'no'}, API key: {'set' if OPENDCODE_API_KEY else 'NOT SET'}")
    init_db()
    from src.shared.session import init_sessions
    asyncio.run(init_sessions())

    _request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )
    _pool_request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )
    _commands = [
        BotCommand("reset", "Очистить историю и документ сессии"),
        BotCommand("subscribe", "Выбрать тариф"),
        BotCommand("myplan", "Мой тариф и статистика"),
        BotCommand("sessions", "Управление сессиями"),
        BotCommand("help", "Показать справку"),
    ]

    async def _post_init(app):
        try:
            await app.bot.set_my_commands(_commands)
        except Exception as e:
            log.warning(f"Failed to set bot commands: {e}")

        async def _cleanup_job(ctx):
            count = await cleanup_expired_subscriptions()
            if count:
                log.info(f"Cleanup job: expired {count} subscriptions")

        if app.job_queue is not None:
            app.job_queue.run_repeating(_cleanup_job, interval=3600, first=3600)
        else:
            log.warning("JobQueue not available, cleanup disabled")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .request(_request)
        .get_updates_request(_pool_request)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("reset", reset_session))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CommandHandler("cancel", cancel_subscription))
    app.add_handler(CommandHandler("admin", admin_handler))
    app.add_handler(CommandHandler("sessions", sessions_handler))
    app.add_handler(CommandHandler("session_create", session_create))
    app.add_handler(CommandHandler("session_delete", session_delete_handler))
    app.add_handler(CommandHandler("session", session_rename))
    app.add_handler(CallbackQueryHandler(sessions_callback, pattern=r"^(sess_|sw_)"))
    app.add_handler(CallbackQueryHandler(subscribe_callback, pattern=r"sub_(plus|pro)"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
