import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup

from src.pipeline.crawlers.base import BaseCrawler, CrawledDocument

PRAVO_BASE = "http://pravo.gov.ru"
KNOWN_CODES = [
    {
        "slug": "konstitutsiya",
        "title": "Конституция Российской Федерации",
        "short_title": "Конституция РФ",
        "doc_type": "constitution",
        "urls": [
            "http://pravo.gov.ru/konstituc/",
            "http://publication.pravo.gov.ru/document/0001202210060013",
        ],
    },
    {
        "slug": "gk-rf-ch1",
        "title": "Гражданский кодекс Российской Федерации (часть 1)",
        "short_title": "ГК РФ ч.1",
        "doc_type": "code",
        "urls": [
            "http://pravo.gov.ru/proxy/ips/?docbody=&nd=102038709",
        ],
    },
    {
        "slug": "uk-rf",
        "title": "Уголовный кодекс Российской Федерации",
        "short_title": "УК РФ",
        "doc_type": "code",
        "urls": [
            "http://pravo.gov.ru/proxy/ips/?docbody=&nd=102041561",
        ],
    },
    {
        "slug": "koap-rf",
        "title": "Кодекс Российской Федерации об административных правонарушениях",
        "short_title": "КоАП РФ",
        "doc_type": "code",
        "urls": [
            "http://pravo.gov.ru/proxy/ips/?docbody=&nd=102074229",
        ],
    },
]


class PravoGovCrawler(BaseCrawler):
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; LegalBot/1.0)"},
            timeout=30.0,
            follow_redirects=True,
        )

    async def crawl(self) -> list[CrawledDocument]:
        results = []
        for code in KNOWN_CODES:
            for url in code["urls"]:
                try:
                    resp = await self.client.get(url)
                    resp.raise_for_status()
                    results.append(CrawledDocument(
                        source_url=url,
                        title=code["title"],
                        short_title=code["short_title"],
                        doc_type=code["doc_type"],
                        official_number=None,
                        adoption_date=None,
                        effective_date=None,
                        raw_html=resp.text,
                        raw_xml=None,
                    ))
                    break
                except Exception:
                    continue
        await self.client.aclose()
        return results

    async def close(self):
        await self.client.aclose()
