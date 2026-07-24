import json
import logging

from src.shared.database import get_db
from src.shared.queries import UPSERT_DOCUMENT, UPSERT_ARTICLE

log = logging.getLogger(__name__)


def load_document(slug: str, title: str, short_title: str, doc_type: str,
                  official_number: str, source_url: str, articles: list[dict]) -> int:
    with get_db() as conn:
        doc_id = conn.execute(
            UPSERT_DOCUMENT,
            (slug, title, short_title, doc_type, official_number,
             None, None, source_url, "{}"),
        ).fetchone()[0]

        for art in articles:
            conn.execute(
                UPSERT_ARTICLE,
                (doc_id, art["number"], art.get("title", ""),
                 art["content"], art.get("chapter", ""),
                 art.get("section", ""), art.get("order", 0)),
            )

        log.info(f"Loaded {title}: {len(articles)} articles (id={doc_id})")
        return doc_id


def load_from_json(path: str) -> int | None:
    import json as j
    with open(path, encoding="utf-8") as f:
        data = j.load(f)
    return load_document(
        slug=data["slug"],
        title=data["title"],
        short_title=data.get("short_title", ""),
        doc_type=data["doc_type"],
        official_number=data.get("official_number", ""),
        source_url=data.get("source_url", ""),
        articles=data["articles"],
    )
