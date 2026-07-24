#!/usr/bin/env python3
"""Скачивает официальные тексты кодексов с pravo.gov.ru и загружает в SQLite."""

import logging
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CLIENT = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (compatible; LegalBot/1.0)"},
    timeout=30,
    follow_redirects=True,
)

CODES = [
    {
        "slug": "konstitutsiya",
        "title": "Конституция Российской Федерации",
        "short_title": "Конституция РФ",
        "doc_type": "constitution",
        "official_number": "",
        "nd": "102027595",
        "rdk": "0",
    },
    {
        "slug": "uk-rf",
        "title": "Уголовный кодекс Российской Федерации",
        "short_title": "УК РФ",
        "doc_type": "code",
        "official_number": "63-ФЗ",
        "nd": "102041891",
        "rdk": "0",
    },
    {
        "slug": "gk-rf-ch1",
        "title": "Гражданский кодекс Российской Федерации. Часть первая",
        "short_title": "ГК РФ (ч.1)",
        "doc_type": "code",
        "official_number": "51-ФЗ",
        "nd": "102033239",
        "rdk": "0",
    },
    {
        "slug": "gk-rf-ch2",
        "title": "Гражданский кодекс Российской Федерации. Часть вторая",
        "short_title": "ГК РФ (ч.2)",
        "doc_type": "code",
        "official_number": "14-ФЗ",
        "nd": "102039276",
        "rdk": "0",
    },
    {
        "slug": "gk-rf-ch3",
        "title": "Гражданский кодекс Российской Федерации. Часть третья",
        "short_title": "ГК РФ (ч.3)",
        "doc_type": "code",
        "official_number": "146-ФЗ",
        "nd": "102073578",
        "rdk": "0",
    },
    {
        "slug": "gk-rf-ch4",
        "title": "Гражданский кодекс Российской Федерации. Часть четвертая",
        "short_title": "ГК РФ (ч.4)",
        "doc_type": "code",
        "official_number": "230-ФЗ",
        "nd": "102110716",
        "rdk": "0",
    },
    {
        "slug": "koap-rf",
        "title": "Кодекс Российской Федерации об административных правонарушениях",
        "short_title": "КоАП РФ",
        "doc_type": "code",
        "official_number": "195-ФЗ",
        "nd": "102074277",
        "rdk": "0",
    },
    {
        "slug": "tk-rf",
        "title": "Трудовой кодекс Российской Федерации",
        "short_title": "ТК РФ",
        "doc_type": "code",
        "official_number": "197-ФЗ",
        "nd": "102074279",
        "rdk": "0",
    },
    {
        "slug": "semya-rf",
        "title": "Семейный кодекс Российской Федерации",
        "short_title": "СК РФ",
        "doc_type": "code",
        "official_number": "223-ФЗ",
        "nd": "102038925",
        "rdk": "0",
    },
    {
        "slug": "fz-ob-obrazovanii",
        "title": "Федеральный закон «Об образовании в Российской Федерации»",
        "short_title": "ФЗ №273-ФЗ",
        "doc_type": "federal_law",
        "official_number": "273-ФЗ",
        "nd": "102162745",
        "rdk": "0",
    },
]


def fetch_text(nd: str, rdk: str = "0") -> str | None:
    url = f"http://pravo.gov.ru/proxy/ips?doc_itself=&nd={nd}&page=all&rdk={rdk}"
    try:
        r = CLIENT.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"  Failed to fetch {url}: {e}")
        return None

    r.encoding = "windows-1251"

    body = re.search(r"<body[^>]*>(.*?)</body>", r.text, re.DOTALL)
    if not body:
        return None

    html = body.group(1)

    clean = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)

    clean = re.sub(r"<br\s*/?>", "\n", clean)
    clean = re.sub(r"</p>", "\n\n", clean)
    clean = re.sub(r"</?[^>]+>", " ", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"&lt;", "<", clean)
    clean = re.sub(r"&gt;", ">", clean)
    clean = re.sub(r"&amp;", "&", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = clean.replace("Complex", "").strip()
    clean = re.sub(r"Print false false false MicrosoftInternetExplorer4", "", clean)
    clean = re.sub(r"td:first-child:before\{.*?\}", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    return clean


def parse_articles(text: str) -> list[dict]:
    articles = []
    order = 0

    article_pattern = re.compile(
        r"Статья\s+(\d+(?:\.\d+)?(?:-\d+)?)\s*[.。]?\s*(.*?)(?=Статья\s+\d+|$)",
        re.DOTALL | re.IGNORECASE,
    )

    for m in article_pattern.finditer(text):
        num = m.group(1).strip()
        rest = m.group(2).strip()

        title = ""
        content = rest

        colon_pos = content.find(":")
        if colon_pos > 0 and colon_pos < 200:
            candidate = content[:colon_pos].strip()
            if not re.search(r"[а-я]\s*[а-я]", candidate, re.I) or len(candidate.split()) <= 10:
                title = candidate
                content = content[colon_pos + 1:].strip()

        if not content:
            continue

        content = re.sub(r"\s+", " ", content).strip()
        content = re.sub(r"^\d+[.。]\s*", "", content).strip()

        if len(content) < 5:
            continue

        order += 1
        articles.append({
            "number": num,
            "title": title or "",
            "content": content,
            "chapter": "",
            "section": "",
            "order": order,
        })

    return articles


def main():
    from src.shared.database import init_db, get_db
    from src.shared.queries import UPSERT_DOCUMENT, UPSERT_ARTICLE

    init_db()
    log.info("Database initialized")

    total_articles = 0

    for code in CODES:
        log.info(f"\n=== {code['title']} ===")

        source_url = f"http://pravo.gov.ru/proxy/ips?doc_itself=&nd={code['nd']}&page=all&rdk={code['rdk']}"

        text = fetch_text(code["nd"], code["rdk"])
        if not text:
            log.warning(f"  FAILED to fetch {code['title']}")
            continue

        articles = parse_articles(text)
        log.info(f"  Parsed {len(articles)} articles from {len(text)} chars")

        if not articles:
            log.warning("  No articles parsed, skipping")
            continue

        with get_db() as conn:
            doc_id = conn.execute(
                UPSERT_DOCUMENT,
                (code["slug"], code["title"], code["short_title"],
                 code["doc_type"], code["official_number"],
                 None, None, source_url, "{}"),
            ).fetchone()[0]

            conn.execute("DELETE FROM articles WHERE document_id = ?", (doc_id,))

            for art in articles:
                conn.execute(
                    UPSERT_ARTICLE,
                    (doc_id, art["number"], art["title"],
                     art["content"], art.get("chapter", ""),
                     art.get("section", ""), art["order"]),
                )

        log.info(f"  Inserted {len(articles)} articles (doc_id={doc_id})")
        total_articles += len(articles)

    CLIENT.close()
    log.info(f"\nDone! Total: {total_articles} articles loaded")


if __name__ == "__main__":
    main()
