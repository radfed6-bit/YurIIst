import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import aiosqlite
import httpx

from bs4 import BeautifulSoup

log = logging.getLogger("legal_bot.tools")

SQLITE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "legal.db"
PARALLEL_SEARCH_URL = "https://search.parallel.ai/mcp"
OPENDCODE_MODEL = "deepseek-v4-flash-free"
_HTTP_CLIENT: httpx.AsyncClient | None = None
_HTTP_CLIENT_LOCK = asyncio.Lock()
_ARTICLE_CACHE: dict[str, str] = {}
_ARTICLE_CACHE_LOCK = asyncio.Lock()
_MAX_CACHE = 500

_RATE_LIMITER: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()
_RATE_WINDOW = 60
_RATE_MAX_CALLS = 6


async def _check_rate_limit(key: str) -> bool:
    now = time.monotonic()
    async with _RATE_LIMIT_LOCK:
        timestamps = _RATE_LIMITER.get(key, [])
        timestamps = [t for t in timestamps if now - t < _RATE_WINDOW]
        if len(timestamps) >= _RATE_MAX_CALLS:
            return False
        timestamps.append(now)
        _RATE_LIMITER[key] = timestamps
    return True


_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]


def _is_internal_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        if host.lower() in _BLOCKED_HOSTS:
            return True
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        return False

STOP_WORDS = {
    "какое", "какой", "какая", "какие", "какого", "какому", "каким", "каких",
    "что", "кто", "где", "когда", "куда", "откуда", "почему", "зачем", "как",
    "сколько", "чей", "который", "для", "за", "на", "по", "под", "над", "о",
    "об", "от", "до", "из", "у", "при", "с", "со", "в", "во", "к", "ко",
    "а", "но", "и", "или", "да", "же", "бы", "ли", "не", "ни", "нет",
    "это", "этот", "эта", "эти", "этого", "этому", "этим", "этих",
    "тот", "та", "те", "того", "тому", "тем", "тех",
    "весь", "вся", "все", "всего", "всем", "всеми", "всех",
    "быть", "есть", "будет", "можно", "нужно", "надо",
    "является", "называется", "составляет", "предусматривает",
    "меня", "тебя", "его", "её", "ее", "нас", "вас", "их",
    "мне", "тебе", "ему", "нам", "вам", "им",
}


def _extract_fts_keywords(text: str) -> str:
    words = re.findall(r"[а-яёА-ЯЁa-zA-Z]+", text.lower())
    keywords = [w for w in words if len(w) > 2 and w not in STOP_WORDS]
    if not keywords:
        return text
    return " OR ".join(keywords[:15])


def _make_fts_query(raw: str) -> str:
    clean = raw.strip()
    clean = re.sub(r'[.]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean)
    if not clean:
        return raw
    has_operators = bool(re.search(r'\b(OR|AND|NOT)\b', clean, re.IGNORECASE))
    if '"' in clean or has_operators:
        return clean
    words = clean.split()
    if len(words) <= 6:
        return clean
    return f'"{clean}"'


async def search_legal_db(query: str, top_k: int = 10, doc_slug: str | None = None) -> str:
    try:
        fts_query = _make_fts_query(query)
        log.info(f"FTS query: {fts_query} (original: {query})")
        async with aiosqlite.connect(str(SQLITE_PATH)) as conn:
            conn.row_factory = aiosqlite.Row
            if doc_slug:
                cursor = await conn.execute("""
                    SELECT a.*, d.title as doc_title, d.slug as doc_slug
                    FROM articles_fts
                    JOIN articles a ON a.id = articles_fts.rowid
                    JOIN documents d ON d.id = a.document_id
                    WHERE articles_fts MATCH ? AND d.slug = ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, doc_slug, top_k))
                rows = await cursor.fetchall()
            else:
                cursor = await conn.execute("""
                    SELECT a.*, d.title as doc_title, d.slug as doc_slug
                    FROM articles_fts
                    JOIN articles a ON a.id = articles_fts.rowid
                    JOIN documents d ON d.id = a.document_id
                    WHERE articles_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, top_k))
                rows = await cursor.fetchall()

            if not rows:
                kw = _extract_fts_keywords(query)
                if kw != fts_query:
                    log.info(f"Retrying with keywords: {kw}")
                    if doc_slug:
                        cursor = await conn.execute("""
                            SELECT a.*, d.title as doc_title, d.slug as doc_slug
                            FROM articles_fts
                            JOIN articles a ON a.id = articles_fts.rowid
                            JOIN documents d ON d.id = a.document_id
                            WHERE articles_fts MATCH ? AND d.slug = ?
                            ORDER BY rank
                            LIMIT ?
                        """, (kw, doc_slug, top_k))
                        rows = await cursor.fetchall()
                    else:
                        cursor = await conn.execute("""
                            SELECT a.*, d.title as doc_title, d.slug as doc_slug
                            FROM articles_fts
                            JOIN articles a ON a.id = articles_fts.rowid
                            JOIN documents d ON d.id = a.document_id
                            WHERE articles_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?
                        """, (kw, top_k))
                        rows = await cursor.fetchall()

            results = []
            for r in rows:
                results.append({
                    "document": r["doc_title"],
                    "slug": r["doc_slug"],
                    "article_number": r["article_number"],
                    "title": r["title"] or "",
                    "content": r["content"][:1500],
                    "chapter": r["chapter"] or "",
                    "section": r["section"] or "",
                })
            return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"search_legal_db error: {e}")
        return json.dumps({"error": "search_legal_db: internal error"}, ensure_ascii=False)


async def _get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    async with _HTTP_CLIENT_LOCK:
        if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
            limits = httpx.Limits(max_keepalive_connections=4, max_connections=10)
            _HTTP_CLIENT = httpx.AsyncClient(timeout=20, limits=limits)
    return _HTTP_CLIENT


async def get_article(slug: str, article_number: str) -> str:
    cache_key = f"{slug}:{article_number}"
    cached = _ARTICLE_CACHE.get(cache_key)
    if cached is not None:
        log.info(f"get_article cache hit: {cache_key}")
        return cached

    try:
        async with aiosqlite.connect(str(SQLITE_PATH)) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("""
                SELECT a.*, d.title as doc_title, d.slug as doc_slug
                FROM articles a
                JOIN documents d ON d.id = a.document_id
                WHERE d.slug = ? AND a.article_number = ?
            """, (slug, article_number))
            row = await cursor.fetchone()

            if not row:
                return json.dumps({"error": f"Статья {article_number} в {slug} не найдена"}, ensure_ascii=False)

            result = {
                "document": row["doc_title"],
                "slug": row["doc_slug"],
                "article_number": row["article_number"],
                "title": row["title"] or "",
                "content": row["content"],
                "chapter": row["chapter"] or "",
                "section": row["section"] or "",
            }
            text = json.dumps(result, ensure_ascii=False, indent=2)
            async with _ARTICLE_CACHE_LOCK:
                if len(_ARTICLE_CACHE) >= _MAX_CACHE:
                    _ARTICLE_CACHE.pop(next(iter(_ARTICLE_CACHE), None))
                _ARTICLE_CACHE[cache_key] = text
            return text
    except Exception as e:
        log.warning(f"get_article error: {e}")
        return json.dumps({"error": "get_article: internal error"}, ensure_ascii=False)


async def web_search(query: str) -> str:
    if not await _check_rate_limit("web_search"):
        return json.dumps({"error": "Слишком много поисковых запросов. Подожди минуту."}, ensure_ascii=False)
    user_id = int(hashlib.sha256(query.encode()).hexdigest()[:8], 16)
    session_id = hashlib.sha256(f"legal_agent_{user_id}".encode()).hexdigest()[:32]
    objective = f"Найти актуальную информацию по российскому законодательству: {query}"

    client = await _get_http_client()
    try:
        r = await client.post(
            PARALLEL_SEARCH_URL,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "web_search",
                    "arguments": {
                        "objective": objective,
                        "search_queries": [query[:80]],
                        "session_id": session_id,
                        "model_name": OPENDCODE_MODEL,
                    },
                },
                "id": 1,
            },
        )
        r.raise_for_status()
        data = r.json()
        if "result" in data and "content" in data["result"]:
            texts = []
            for item in data["result"]["content"]:
                texts.append(item.get("text", ""))
            combined = "\n\n".join(texts)[:5000]
            return combined if combined.strip() else json.dumps({"error": "Пустой результат поиска"}, ensure_ascii=False)
        return json.dumps({"error": "Нет результатов от поискового сервиса"}, ensure_ascii=False)
    except Exception as e:
        log.warning(f"web_search error: {e}")
        return json.dumps({"error": "web_search: internal error"}, ensure_ascii=False)


async def web_fetch(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return json.dumps({"error": "Некорректный URL. Допускаются только http/https ссылки."}, ensure_ascii=False)
    if _is_internal_url(url):
        return json.dumps({"error": "Доступ к внутренним ресурсам запрещён."}, ensure_ascii=False)
    if not await _check_rate_limit("web_fetch"):
        return json.dumps({"error": "Слишком много запросов. Подожди минуту."}, ensure_ascii=False)
    client = await _get_http_client()
    try:
        r = await client.get(url, follow_redirects=True, timeout=30)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "application/pdf" in content_type:
            return json.dumps({"error": "Не могу обработать PDF. Используй загрузку документа."}, ensure_ascii=False)
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        MAX_FETCH = 15000
        if len(text) > MAX_FETCH:
            text = text[:MAX_FETCH] + "\n\n...(обрезано, полный текст по ссылке)"
        return text if text.strip() else json.dumps({"error": "Не удалось извлечь текст со страницы."}, ensure_ascii=False)
    except httpx.TimeoutException:
        return json.dumps({"error": "Превышено время ожидания при загрузке страницы."}, ensure_ascii=False)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Страница вернула ошибку {e.response.status_code}."}, ensure_ascii=False)
    except Exception as e:
        log.warning(f"web_fetch error: {e}")
        return json.dumps({"error": "web_fetch: internal error"}, ensure_ascii=False)
