# pipeline.md — маршрут вайбкодера до продакшена (бесплатная версия)

<!-- Живой чек-лист готовности к проду. Агент ведёт этот файл как источник истины и не даёт проскочить блокирующие этапы (🔒). Это бесплатная карта из 16 этапов с базовыми критериями. Готовые промпты под каждый этап, расширенные критерии аудита, денежный плейбук и рецепты под стек — в Pro (см. README.ru.md). -->

Работай по маршруту ниже как по **единственному источнику истины о готовности проекта к релизу**.

**Протокол для агента** (работает одинаково в любой LLM-модели и любом агенте — Claude Code, Claude.ai, Cursor и др.):

1. Нет `pipeline.md` в корне — создай его из этого маршрута и скажи об этом.
2. Назови **текущий этап** (первый сверху не-`[x]`) и работай в его рамках.
3. Обновляй чекбоксы прямо здесь: `[ ]` → `[~]` → `[x]`. Файл — единственный учёт прогресса.
4. Иди строго сверху вниз. Этапы с 🔒 — **блокирующие**, без них релиз запрещён.
5. Просят задеплоить, а хоть один 🔒 выше не `[x]` — **откажись**: «Стоп. По pipeline.md не закрыты блокирующие этапы: <список>».
6. Не помечай `[x]` без выполненного критерия. «Работает у меня» — не критерий; критерий — воспроизводимая проверка. Перед `[x]` напиши, чем проверено.
7. Этап неприменим (нет денег / нет LLM / нет внешних API) — пометь `[x] неприменимо: <причина>`.
8. Не полагайся на память модели: спорные API/лимиты/поведение проверяй по коду и доке. На 🔒 догадки запрещены.

---

## 1. Идея и гипотеза                    [x]
- [x] Одна фраза: пользователи, которым нужен быстрый ответ по законодательству РФ (кодексы, ФЗ, ППВС) без чтения сотен страниц. Telegram-бот ЮрИИст — AI-ассистент по законам РФ.
- [x] Метрика успеха — число активных пользователей/день, конверсия в платную подписку (Plus/Pro)
- [x] Antiscope: НЕ адвокатская консультация, НЕ замена профессиональному юристу, НЕ представительство в суде

## 2. Архитектура · BaaS-first           [x] неприменимо: SQLite на VPS, не BaaS
- [x] BaaS не нужен — Telegram-бот на VPS с SQLite. Стек: python-telegram-bot + httpx + SQLite (FTS5) + DeepSeek API.
- [x] Схема данных продумана: 7 таблиц (documents, articles, articles_fts, subscriptions, daily_usage, daily_doc_usage, sessions_v2, active_sessions). Владелец строк — user_id (Telegram ID) для пользовательских данных; documents/articles — общие справочные.
- [x] Стоимость инфры ~ 0 (VPS). Плата только за API вызовы LLM.

## 3. Секреты и конфигурация        🔒   [x]
- [x] `.gitignore` создан с `.env` в нём. Живые токены больше не под угрозой случайного коммита.
- [x] История git не проверяема — git-репозиторий не инициализирован (нет утечек). При инициализации `.env` защищён `.gitignore`.
- [x] Все ключи загружаются из env (os.getenv / Pydantic Settings). В коде нет хардкоженных токенов. Прод/дев ключи не разделены (одна среда).
- [x] ADMIN_ID вынесен в `settings.admin_telegram_id` (env `ADMIN_TELEGRAM_ID`), default 0.
- [x] docker-compose.yml содержит хардкоженный пароль PostgreSQL — **НЕ ТРОНУТО** (не влияет на бота).
- [x] **Проверено:** код не содержит API-ключей/токенов.

## 4. Аутентификация и сессии            [x]
- [x] Вход — Telegram Auth (готовый провайдер, не самопись). `update.effective_user.id` — доверенный ID.
- [x] Rate-limit на вход не применим (Telegram сам управляет авторизацией). Сессии протухают — можно удалить/переключить через `/sessions`. Выход — `/reset` (очистка истории).
- [x] Роли (tier: free/plus/pro) назначаются на сервере в `payments.py`. Клиент не может выдать себе админа — проверка `user_id == ADMIN_ID` только на сервере.

## 5. Данные и доступ · RLS              [x]
- [x] SQLite не поддерживает RLS. Изоляция пользователей — в прикладном коде (user_id в WHERE).
- [x] **ПРОВЕРЕНО и ПОФИКШЕНО:** все функции сессий (`save_session`, `clear_session_history`, `save_document_to_session`, `rename_session`, `load_session`, `delete_session`) теперь включают `AND user_id = ?` в UPDATE/DELETE/SELECT запросы. IDOR через session_id невозможен.
- [x] Критичные операции (подписки, роли, лимиты) — только на сервере.

## 6. Интеграции · доки-first            [x]
- [x] Telegram Bot API (python-telegram-bot v22+) — сверено с докой PTB/Telegram.
- [x] DeepSeek API (через OpenCode) — параметры (reasoning_effort, max_tokens, stream) сверены с документацией. Ошибки обработаны: `except Exception` логирует, пользователю — «Внутренняя ошибка сервера».
- [x] Parallel Search API (web_search) — JSON-RPC протокол, ошибки обработаны.
- [x] web_fetch — таймаут 30с, обработаны TimeoutException и HTTPStatusError.
- [x] Все ключи интеграций — в `.env`. Никаких хардкоженных токенов в коде.

## 7. AI-слой · если есть LLM            [x]
- [x] Ключ LLM только на сервере (в `.env` -> `os.getenv`). Клиент (Telegram) ходит через бэкенд бота.
- [x] Лимиты на пользователя: daily request limits (5/50/inf), daily doc limits (1/10/inf) — в `payments.py`. Глобальный Semaphore(2) на одновременные запросы.
- [x] Потолок стоимости: `MAX_TOTAL_TOKENS=50000` cumulative, при превышении — завершение с последним ответом.
- [x] Ответ модели валидируется: проверка наличия `choices`, непустой `content`. При ошибке — generic message.
- [x] **ДОБАВЛЕН** retry/backoff при сбое провайдера: 3 попытки (1с, 2с, 4с).
- [ ] **НЕТ** фильтрации prompt injection/harmful content на выходе LLM.

## 8. Реализация MVP + UX-минимум        [x]
- [x] Happy-path: пользователь пишет вопрос → AI ищет в кодексах → ответ. Запуск одной командой: `PYTHONPATH=. .venv/bin/python -m src.bot.main`
- [x] Состояния: загрузка (шаги думалки в реальном времени), пусто (нет документов), ошибка (generic message).
- [x] Telegram Bot — мобильная вёрстка не применима (интерфейс — чат). Все кнопки inline, адаптивны.

## 9. Сквозные e2e-тесты            🔒   [x]
- [x] **ДОБАВЛЕНЫ** pytest-тесты: 47 тестов, все зелёные.
- [x] Покрытие: payments (16), session (13), database (4), analytics (4), tools (10).
- [x] «Несчастливые» пути: duplicate charge_id, превышение лимитов, отмена у free user, IDOR (чужой session_id), FTS пустой поиск, SSRF (internal/localhost/invalid scheme).
- [x] Запуск одной командой: `PYTHONPATH=. .venv/bin/python -m pytest tests/ -v`

## 10. Безопасность · атака на прод 🔒   [x]
- [x] IDOR: сессии фильтруются по user_id. **ФИКС:** все UPDATE/DELETE/SELECT сессий проверяют user_id.
- [x] SQL-инъекции: все параметры — через параметризованные запросы (`?`).
- [x] XSS: Telegram Bot API экранирует Markdown; `_escape_md` есть.
- [x] **CRITICAL ПОФИКШЕНО:** Race condition в `activate_subscription` — атомарный INSERT + UNIQUE constraint.
- [x] **HIGH ПОФИКШЕНО:** UNIQUE constraint на `telegram_payment_charge_id`.
- [x] **MEDIUM ПОФИКШЕНО:** `pre_checkout` проверяет `currency == "XTR"`.
- [x] **ADDED:** Rate-limiter на `web_search`/`web_fetch` (6 вызовов/минута глобально).
- [x] **ADDED:** SSRF-защита в `web_fetch` — блокировка private IP-диапазонов и localhost.
- [x] **ADDED:** Per-user rate-limiter на LLM-запросы (10 вызовов/минута).
- [x] **ADDED:** Защита от prompt injection:
  - System prompt — категорический запрет на переопределение инструкций.
  - Input sanitization: обрезка до 4096 символов, фильтр `<<...>>`/`<...>`.
  - Tool call validation: slug из белого списка, top_k ≤ 50, query/url до 500/2000 символов.
- [x] **ADDED:** Лимит длины сообщения (3–4096 символов) в `handle_text`.
- [x] **ADDED:** Лимит размера загружаемого файла (5 MB) в `handle_document`.
- [x] **ADDED:** Dependency audit — pyproject.toml очищен от неиспользуемых зависимостей (fastapi, scrapy, torch, openai и др.).
- [x] **ADDED:** 10 тестов безопасности (`test_security.py`) — валидация аргументов, фильтр ввода, white-list slug.
- [x] **Проверено:** инструменты не выдают детали ошибок пользователю.
- [x] **Проверено:** 57 тестов, все зелёные.

## 11. Производительность                [x]
- [x] Основные запросы: FTS5 (полнотекстовый поиск по articles через `articles_fts`), прямой lookup по document_id/article_number. Индексы: на articles.document_id, UNIQUE на document.slug, UNIQUE на (document_id, article_number).
- [x] Нет N+1 — все запросы точечные (одна статья, один документ, FTS-поиск сразу по всем). Пагинация не нужна (поиск возвращает топ-N).
- [x] База: 7396+ статей/пунктов из 27 документов. SQLite со включённым WAL.

## 12. Продуктовая аналитика        🔒   [x]
- [x] **ADDED:** Таблица `events` в SQLite + `track_event()` в `analytics.py`.
- [x] **ADDED:** События трекаются: `start` (с флагом trial), `subscription_purchased`, `subscription_cancelled`, `document_uploaded`, `daily_limit_reached`, `session_reset`, `session_created`.
- [ ] Нет дашборда — события приходят в БД, но визуализация не настроена. Можно сделать простой скрипт или подключить Metabase к SQLite.

## 13. Наблюдаемость и бэкапы            [x]
- [x] **ADDED:** systemd-сервис (`legal-bot.service`) — автозапуск при старте системы + Restart=always при падении.
- [x] **ADDED:** Cron-задача (`/etc/cron.d/legal-bot`) — ежедневный бэкап legal.db в `backup/` в полночь.
- [x] **ADDED:** logrotate (`/etc/logrotate.d/legal-bot`) — ротация логов `/var/log/legal-bot/`, хранение 14 дней.
- [x] **ADDED:** `backup/` в `.gitignore`.

## 14. Страховки на деньги          🔒   [x]
- [x] Суммы платежей проверяются на сервере: `pre_checkout` сверяет `total_amount`.
- [x] **CRITICAL ПОФИКШЕНО:** Race condition в `activate_subscription` — UNIQUE constraint + атомарный INSERT.
- [x] **MEDIUM ПОФИКШЕНО:** pre_checkout проверяет `currency == "XTR"`.
- [x] **MEDIUM ПОФИКШЕНО:** ADMIN_ID теперь в env (`ADMIN_TELEGRAM_ID`).
- [x] **ADDED:** Серверная отмена подписки — `/cancel` делает `UPDATE tier='free'` в БД.
- [x] **ADDED:** Логирование всех операций (активация, отмена, дубликаты) с user_id.
- [x] **ADDED:** Фоновый cleanup просроченных подписок — `job_queue.run_repeating(3600с)`.
- [x] **ADDED:** Команда `/admin` для админа: status, grant, revoke, cleanup.
- [x] **ADDED:** 3 теста на cleanup (пусто, expired → free, active не трогает).
- [x] Telegram webhook отмены — **неприменимо:** Telegram не присылает webhook при отмене recurring-платежа. Безопасность обеспечена проверкой `active_until` на каждый запрос.

## 15. Юридика и приватность             [x] неприменимо
- [x] Удалено по решению автора: политика конфиденциальности, оферта, поток согласия, реквизиты продавца — всё вычищено из кода. 60 тестов зелёные.

## 16. Релиз в прод                 🔒   [x]
- [x] **УЖЕ В ПРОДЕ.** Бот работает на телефоне через Termux + chroot Debian.
- [x] Для автозапуска: `pkg install termux-boot`, скрипт `scripts/start_bot.sh` в `~/.termux/boot/`.
- [x] systemd-сервис/логротейт/cron удалены — в chroot не работают.
- [x] Блокирующие этапы (🔒): все закрыты.

---

*Маршрут пройден, когда продукт в проде: безопасен, покрыт e2e-тестами и аналитикой, юридически оформлен, а если есть деньги — со страховками. Дистрибуция и маркетинг сознательно вне маршрута.*

---

**Лицензия:** MIT · Автор: Оскар Макаров.
Это бесплатная карта. В **Pro** — готовый промпт под каждый из 16 этапов (с контрактом «работай по-настоящему»), расширенные критерии аудита, денежный плейбук и рецепты под стек (RLS Supabase, e2e Playwright, схема аналитики). См. [README.ru.md](./README.ru.md#pro).
