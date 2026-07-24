from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection

from src.api.dependencies import get_db_conn
from src.shared.queries import GET_ARTICLE_BY_ID
from src.shared.schemas import ArticleOut

router = APIRouter(prefix="/api/v1/articles", tags=["articles"])


@router.get("/{article_id}")
def get_article(article_id: int, conn: Connection = Depends(get_db_conn)):
    row = conn.execute(GET_ARTICLE_BY_ID, (article_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleOut(
        id=row["id"], document_id=row["document_id"],
        article_number=row["article_number"], title=row["title"] or "",
        content=row["content"], chapter=row["chapter"] or "",
        section=row["section"] or "",
    )
