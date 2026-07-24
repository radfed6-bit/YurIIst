from dataclasses import dataclass

from src.pipeline.parsers.xml_parser import ParsedArticle


@dataclass
class Chunk:
    article_id: int | None
    document_id: int
    document_slug: str
    article_number: str
    chapter: str
    section: str
    text: str
    metadata: dict


def chunk_articles(
    document_id: int,
    document_slug: str,
    articles: list[ParsedArticle],
    existing_article_ids: dict[str, int] | None = None,
) -> list[Chunk]:
    chunks = []
    for art in articles:
        art_id = existing_article_ids.get(art.article_number) if existing_article_ids else None
        chunks.append(Chunk(
            article_id=art_id,
            document_id=document_id,
            document_slug=document_slug,
            article_number=art.article_number,
            chapter=art.chapter,
            section=art.section,
            text=art.content,
            metadata={
                "doc_type": "",
                "doc_title": document_slug,
            },
        ))
    return chunks
