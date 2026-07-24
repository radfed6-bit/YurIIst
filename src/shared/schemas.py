from pydantic import BaseModel, Field


class ArticleOut(BaseModel):
    id: int
    document_id: int
    article_number: str
    title: str
    content: str
    chapter: str
    section: str


class DocumentOut(BaseModel):
    id: int
    slug: str
    title: str
    short_title: str
    doc_type: str
    official_number: str
    adoption_date: str | None = None
    source_url: str
    article_count: int = 0


class DocumentDetail(DocumentOut):
    articles: list[ArticleOut] = []


class SearchResult(BaseModel):
    article: ArticleOut
    document_title: str
    document_slug: str
    score: float
    excerpt: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    doc_type: str | None = None
