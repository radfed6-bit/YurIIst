#!/usr/bin/env python3
import logging, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CLIENT = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (compatible; LegalBot/1.0)"},
    timeout=30, follow_redirects=True,
)

LAWS = [
    {
        "slug": "fz-o-voinskoi-obyazannosti",
        "title": "Федеральный закон «О воинской обязанности и военной службе»",
        "short_title": "ФЗ №53-ФЗ",
        "doc_type": "federal_law",
        "official_number": "53-ФЗ",
        "nd": "102052265",
        "adoption_date": "1998-03-28",
    },
    {
        "slug": "fz-o-statuse-voennosluzhashchikh",
        "title": "Федеральный закон «О статусе военнослужащих»",
        "short_title": "ФЗ №76-ФЗ",
        "doc_type": "federal_law",
        "official_number": "76-ФЗ",
        "nd": "102053139",
        "adoption_date": "1998-05-27",
    },
    {
        "slug": "fz-ob-oborone",
        "title": "Федеральный закон «Об обороне»",
        "short_title": "ФЗ №61-ФЗ",
        "doc_type": "federal_law",
        "official_number": "61-ФЗ",
        "nd": "102041583",
        "adoption_date": "1996-05-31",
    },
]


def fetch_text(nd: str, rdk: str = "0") -> str | None:
    url = f"http://pravo.gov.ru/proxy/ips?doc_itself=&nd={nd}&page=all&rdk={rdk}"
    try:
        r = CLIENT.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"  Failed: {e}")
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
            "number": num, "title": title or "",
            "content": content, "chapter": "", "section": "", "order": order,
        })
    return articles


def main():
    from src.shared.database import init_db, get_db
    from src.shared.queries import UPSERT_DOCUMENT, UPSERT_ARTICLE
    init_db()
    log.info("DB initialized")

    total = 0
    for law in LAWS:
        log.info(f"\n=== {law['title']} ===")
        source_url = f"http://pravo.gov.ru/proxy/ips?doc_itself=&nd={law['nd']}&page=all&rdk=0"
        text = fetch_text(law["nd"])
        if not text:
            log.warning(f"  FAILED")
            continue
        articles = parse_articles(text)
        log.info(f"  Parsed {len(articles)} articles from {len(text)} chars")
        if not articles:
            log.warning("  No articles, skip")
            continue
        with get_db() as conn:
            doc_id = conn.execute(
                UPSERT_DOCUMENT,
                (law["slug"], law["title"], law["short_title"],
                 law["doc_type"], law["official_number"],
                 law["adoption_date"], None, source_url, "{}"),
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
        total += len(articles)

    CLIENT.close()
    log.info(f"\nDone! Total: {total} articles loaded")


if __name__ == "__main__":
    main()
