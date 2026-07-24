from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection

from src.api.dependencies import get_db_conn
from src.shared.queries import GET_CODES, GET_DOCUMENT_BY_SLUG, GET_ARTICLES_BY_DOC
from src.shared.schemas import DocumentOut, DocumentDetail, ArticleOut

router = APIRouter(prefix="/api/v1/codes", tags=["codes"])


@router.get("")
def list_codes(conn: Connection = Depends(get_db_conn)):
    rows = conn.execute(GET_CODES).fetchall()
    return [
        DocumentOut(
            id=r["id"], slug=r["slug"], title=r["title"],
            short_title=r["short_title"] or "", doc_type=r["doc_type"],
            official_number=r["official_number"] or "",
            adoption_date=r["adoption_date"],
            source_url=r["source_url"] or "",
            article_count=r["article_count"],
        )
        for r in rows
    ]


@router.get("/{slug}")
def get_code(slug: str, conn: Connection = Depends(get_db_conn)):
    doc_row = conn.execute(GET_DOCUMENT_BY_SLUG, (slug,)).fetchone()
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found")

    article_rows = conn.execute(GET_ARTICLES_BY_DOC, (doc_row["id"],)).fetchall()
    return DocumentDetail(
        id=doc_row["id"], slug=doc_row["slug"], title=doc_row["title"],
        short_title=doc_row["short_title"] or "", doc_type=doc_row["doc_type"],
        official_number=doc_row["official_number"] or "",
        adoption_date=doc_row["adoption_date"],
        source_url=doc_row["source_url"] or "",
        article_count=len(article_rows),
        articles=[
            ArticleOut(id=a["id"], document_id=a["document_id"],
                       article_number=a["article_number"], title=a["title"] or "",
                       content=a["content"], chapter=a["chapter"] or "",
                       section=a["section"] or "")
            for a in article_rows
        ],
    )
