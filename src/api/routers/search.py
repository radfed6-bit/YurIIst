from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlite3 import Connection

from src.api.dependencies import get_db_conn
from src.agent import agent as agent_runner
from src.shared.queries import FTS_SEARCH, SEARCH_WITH_TYPE
from src.shared.schemas import SearchRequest, SearchResponse, SearchResult, ArticleOut

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/fts")
def fts_search(req: SearchRequest, conn: Connection = Depends(get_db_conn)):
    fts_query = " OR ".join(req.query.strip().split())

    if req.doc_type:
        rows = conn.execute(SEARCH_WITH_TYPE, (fts_query, req.doc_type, req.top_k)).fetchall()
    else:
        rows = conn.execute(FTS_SEARCH, (fts_query, req.top_k)).fetchall()

    results = []
    for r in rows:
        score = 1.0 / (1.0 + abs(r["rank_score"])) if r["rank_score"] else 0.5
        results.append(SearchResult(
            article=ArticleOut(
                id=r["id"], document_id=r["document_id"],
                article_number=r["article_number"], title=r["title"] or "",
                content=r["content"], chapter=r["chapter"] or "",
                section=r["section"] or "",
            ),
            document_title=r["doc_title"],
            document_slug=r["doc_slug"],
            score=round(score, 4),
            excerpt=r["content"][:300],
        ))

    return SearchResponse(query=req.query, results=results, total=len(results))


class AgentAskRequest(BaseModel):
    query: str

class AgentAskResponse(BaseModel):
    answer: str
    sources: list[str]


@router.post("/agent/ask")
async def agent_ask(req: AgentAskRequest):
    from src.config import settings
    answer, sources = await agent_runner.run(
        user_query=req.query,
        api_key=settings.opencode_zen_api_key,
    )
    return AgentAskResponse(answer=answer, sources=sources)
