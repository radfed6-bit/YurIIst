import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class ParsedArticle:
    article_number: str
    title: str
    content: str
    chapter: str = ""
    section: str = ""
    order: int = 0


@dataclass
class ParsedDocument:
    title: str
    short_title: str | None
    articles: list[ParsedArticle]

    @property
    def article_count(self) -> int:
        return len(self.articles)


def parse_pravo_html(html: str) -> ParsedDocument | None:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    body = soup.find("body") or soup
    articles = []
    order = 0

    for tag in body.find_all(["p", "div", "span"]):
        text = tag.get_text(strip=True)
        if not text:
            continue

        m = re.match(r"^(Статья\s+[\d.]+[^.]*)[.。]?\s*(.*)", text, re.IGNORECASE)
        if m:
            num_text = m.group(1).strip()
            content = m.group(2).strip()
            num_match = re.search(r"[\d.]+", num_text)
            article_number = num_match.group() if num_match else num_text
            title = ""
            if ":" in content:
                title, content = content.split(":", 1)
                title = title.strip()
                content = content.strip()
            articles.append(ParsedArticle(
                article_number=article_number,
                title=title,
                content=content,
                order=order,
            ))
            order += 1
        elif articles and not text.startswith("("):
            articles[-1].content += " " + text

    return ParsedDocument(title=title, short_title=None, articles=articles)
