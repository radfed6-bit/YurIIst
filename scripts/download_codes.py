#!/usr/bin/env python3
"""
Загрузчик официальных текстов кодексов РФ.
Пытается скачать из нескольких источников.
"""

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
except ImportError:
    print("Установи httpx: pip install httpx beautifulsoup4 lxml")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CLIENT = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (compatible; LegalBot/1.0)"},
    timeout=30,
    follow_redirects=True,
)

# Список кодексов с ID на pravo.gov.ru и альтернативными источниками
CODES = [
    {
        "slug": "konstitutsiya",
        "title": "Конституция Российской Федерации",
        "short_title": "Конституция РФ",
        "doc_type": "constitution",
        "official_number": "",
        "sources": [
            {"url": "http://pravo.gov.ru/proxy/ips/?doc_itself=&nd=102027665&page=all&rdk=0",
             "type": "pravo_doc_itself"},
            {"url": "https://www.consultant.ru/document/cons_doc_LAW_28399/",
             "type": "consultant"},
        ],
    },
    {
        "slug": "gk-rf",
        "title": "Гражданский кодекс Российской Федерации",
        "short_title": "ГК РФ",
        "doc_type": "code",
        "official_number": "51-ФЗ",
        "sources": [
            {"url": "http://pravo.gov.ru/proxy/ips/?doc_itself=&nd=102038709&page=all&rdk=0",
             "type": "pravo_doc_itself"},
            {"url": "https://www.consultant.ru/document/cons_doc_LAW_5142/",
             "type": "consultant"},
        ],
    },
    {
        "slug": "uk-rf",
        "title": "Уголовный кодекс Российской Федерации",
        "short_title": "УК РФ",
        "doc_type": "code",
        "official_number": "63-ФЗ",
        "sources": [
            {"url": "http://pravo.gov.ru/proxy/ips/?doc_itself=&nd=102041561&page=all&rdk=0",
             "type": "pravo_doc_itself"},
            {"url": "https://www.consultant.ru/document/cons_doc_LAW_10699/",
             "type": "consultant"},
        ],
    },
    {
        "slug": "koap-rf",
        "title": "Кодекс Российской Федерации об административных правонарушениях",
        "short_title": "КоАП РФ",
        "doc_type": "code",
        "official_number": "195-ФЗ",
        "sources": [
            {"url": "http://pravo.gov.ru/proxy/ips/?doc_itself=&nd=102074229&page=all&rdk=0",
             "type": "pravo_doc_itself"},
            {"url": "https://www.consultant.ru/document/cons_doc_LAW_34661/",
             "type": "consultant"},
        ],
    },
]


def fetch_text(source: dict) -> str | None:
    url = source["url"]
    try:
        r = CLIENT.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"  Не удалось загрузить {url}: {e}")
        return None

    if source["type"] == "pravo_doc_itself":
        r.encoding = "windows-1251"
        text = r.text
        body = re.search(r"<body[^>]*>(.*?)</body>", text, re.DOTALL)
        if body:
            clean = re.sub(r"<[^>]+>", " ", body.group(1))
            clean = re.sub(r"\s+", " ", clean).strip()
            if len(clean) > 100:
                return clean
        return None

    elif source["type"] == "consultant":
        r.encoding = "utf-8"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup.find_all(["div", "p", "span"]):
            text = tag.get_text(strip=True)
            if re.search(r"Статья\s+\d+", text):
                return r.text
        return None

    return None


def parse_articles(text: str, doc_title: str) -> list[dict]:
    articles = []
    order = 0

    # Pattern: Статья 1. [Title] Content
    pattern = re.compile(r"(Статья\s+([\d\.]+)(?:[^.]*?)[.。]?\s*)(.*?)(?=Статья\s+\d+|$)", re.DOTALL | re.IGNORECASE)

    for m in pattern.finditer(text):
        header = m.group(1).strip()
        num = m.group(2).strip()
        content = m.group(3).strip()

        title = ""
        if ":" in content:
            title, content = content.split(":", 1)
            title = title.strip()
            content = content.strip()

        content = re.sub(r"\s+", " ", content).strip()
        if len(content) < 10:
            continue

        order += 1
        articles.append({
            "number": num,
            "title": title,
            "content": content,
            "chapter": "",
            "section": "",
            "order": order,
        })

    return articles


def download_and_save():
    from src.shared.database import init_db, get_db
    from src.shared.queries import UPSERT_DOCUMENT, UPSERT_ARTICLE

    init_db()
    log.info("База инициализирована")

    for code in CODES:
        log.info(f"\n=== {code['title']} ===")
        text = None
        for source in code["sources"]:
            log.info(f"  Пробую: {source['url'][:60]}...")
            text = fetch_text(source)
            if text:
                log.info(f"  Загружено {len(text)} символов")
                break

        if not text:
            log.warning(f"  НЕ УДАЛОСЬ загрузить {code['title']}")
            continue

        articles = parse_articles(text, code["title"])
        log.info(f"  Найдено статей: {len(articles)}")

        with get_db() as conn:
            doc_id = conn.execute(
                UPSERT_DOCUMENT,
                (code["slug"], code["title"], code["short_title"],
                 code["doc_type"], code["official_number"],
                 None, None, code["sources"][0]["url"], "{}"),
            ).fetchone()[0]

            for art in articles:
                conn.execute(
                    UPSERT_ARTICLE,
                    (doc_id, art["number"], art["title"],
                     art["content"], art.get("chapter", ""),
                     art.get("section", ""), art["order"]),
                )

        log.info(f"  Загружено {len(articles)} статей (id={doc_id})")

    CLIENT.close()
    log.info("\nГотово!")


if __name__ == "__main__":
    download_and_save()
