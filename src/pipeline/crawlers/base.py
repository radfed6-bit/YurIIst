from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CrawledDocument:
    source_url: str
    title: str
    short_title: str | None
    doc_type: str
    official_number: str | None
    adoption_date: str | None
    effective_date: str | None
    raw_html: str | None
    raw_xml: str | None
    metadata: dict | None = None


class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self) -> list[CrawledDocument]:
        ...
