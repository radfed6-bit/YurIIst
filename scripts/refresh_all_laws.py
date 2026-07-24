#!/usr/bin/env python3
import logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CLIENT = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (compatible; LegalBot/1.0)"},
    timeout=120, follow_redirects=True,
)

DOCUMENTS = [
    # --- ППВС (Постановления Пленума Верховного Суда) ---
    {
        "slug": "ppvs-17",
        "title": "Постановление Пленума Верховного Суда РФ от 28.06.2012 № 17 «О рассмотрении судами гражданских дел по спорам о защите прав потребителей»",
        "short_title": "ППВС № 17",
        "doc_type": "plenum",
        "official_number": "17",
        "kremlin_url": "https://normativ.kontur.ru/document?moduleId=7&documentId=200802",
        "adoption_date": "2012-06-28",
    },
    {
        "slug": "ppvs-29",
        "title": "Постановление Пленума Верховного Суда РФ от 27.12.2002 № 29 «О судебной практике по делам о краже, грабеже и разбое»",
        "short_title": "ППВС № 29",
        "doc_type": "plenum",
        "official_number": "29",
        "kremlin_url": "https://normativ.kontur.ru/document?moduleId=7&documentId=439125",
        "adoption_date": "2002-12-27",
    },
    {
        "slug": "ppvs-58",
        "title": "Постановление Пленума Верховного Суда РФ от 22.12.2015 № 58 «О практике назначения судами Российской Федерации уголовного наказания»",
        "short_title": "ППВС № 58",
        "doc_type": "plenum",
        "official_number": "58",
        "kremlin_url": "https://normativ.kontur.ru/document?moduleId=7&documentId=500093",
        "adoption_date": "2015-12-22",
    },
    {
        "slug": "ppvs-10-22",
        "title": "Постановление Пленума Верховного Суда РФ № 10, Пленума ВАС РФ № 22 от 29.04.2010 «О некоторых вопросах, возникающих в судебной практике при разрешении споров, связанных с защитой права собственности и других вещных прав»",
        "short_title": "ППВС № 10/22",
        "doc_type": "plenum",
        "official_number": "10/22",
        "kremlin_url": "https://normativ.kontur.ru/document?moduleId=7&documentId=462545",
        "adoption_date": "2010-04-29",
    },

    # --- НК РФ ---
    {
        "slug": "nk-rf-ch1",
        "title": "Налоговый кодекс Российской Федерации (часть первая)",
        "short_title": "НК РФ (ч.1)",
        "doc_type": "code",
        "official_number": "146-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/12755/print",
        "adoption_date": "1998-07-31",
    },
    {
        "slug": "nk-rf-ch2",
        "title": "Налоговый кодекс Российской Федерации (часть вторая)",
        "short_title": "НК РФ (ч.2)",
        "doc_type": "code",
        "official_number": "117-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/15925/print",
        "adoption_date": "2000-08-05",
    },

    # --- Кодексы ---
    {
        "slug": "gk-rf-ch1",
        "title": "Гражданский кодекс Российской Федерации (часть первая)",
        "short_title": "ГК РФ (ч.1)",
        "doc_type": "code",
        "official_number": "51-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/7279/print",
        "adoption_date": "1994-11-30",
    },
    {
        "slug": "gk-rf-ch2",
        "title": "Гражданский кодекс Российской Федерации (часть вторая)",
        "short_title": "ГК РФ (ч.2)",
        "doc_type": "code",
        "official_number": "14-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/8804/print",
        "adoption_date": "1996-01-26",
    },
    {
        "slug": "gk-rf-ch3",
        "title": "Гражданский кодекс Российской Федерации (часть третья)",
        "short_title": "ГК РФ (ч.3)",
        "doc_type": "code",
        "official_number": "146-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/17547/print",
        "adoption_date": "2001-11-26",
    },
    {
        "slug": "gk-rf-ch4",
        "title": "Гражданский кодекс Российской Федерации (часть четвертая)",
        "short_title": "ГК РФ (ч.4)",
        "doc_type": "code",
        "official_number": "230-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/24743/print",
        "adoption_date": "2006-12-18",
    },
    {
        "slug": "koap-rf",
        "title": "Кодекс Российской Федерации об административных правонарушениях",
        "short_title": "КоАП РФ",
        "doc_type": "code",
        "official_number": "195-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/17704/print",
        "adoption_date": "2001-12-30",
    },
    {
        "slug": "tk-rf",
        "title": "Трудовой кодекс Российской Федерации",
        "short_title": "ТК РФ",
        "doc_type": "code",
        "official_number": "197-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/17706/print",
        "adoption_date": "2001-12-30",
    },
    {
        "slug": "semya-rf",
        "title": "Семейный кодекс Российской Федерации",
        "short_title": "СК РФ",
        "doc_type": "code",
        "official_number": "223-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/8671/print",
        "adoption_date": "1995-12-29",
    },

    # --- Федеральные законы ---
    {
        "slug": "fz-o-voinskoi-obyazannosti",
        "title": "Федеральный закон «О воинской обязанности и военной службе»",
        "short_title": "ФЗ №53-ФЗ",
        "doc_type": "federal_law",
        "official_number": "53-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/12128/print",
        "adoption_date": "1998-03-28",
    },
    {
        "slug": "fz-o-statuse-voennosluzhashchikh",
        "title": "Федеральный закон «О статусе военнослужащих»",
        "short_title": "ФЗ №76-ФЗ",
        "doc_type": "federal_law",
        "official_number": "76-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/12429/print",
        "adoption_date": "1998-05-27",
    },
    {
        "slug": "fz-ob-oborone",
        "title": "Федеральный закон «Об обороне»",
        "short_title": "ФЗ №61-ФЗ",
        "doc_type": "federal_law",
        "official_number": "61-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/9446/print",
        "adoption_date": "1996-05-31",
    },
    {
        "slug": "fz-ob-obrazovanii",
        "title": "Федеральный закон «Об образовании в Российской Федерации»",
        "short_title": "ФЗ №273-ФЗ",
        "doc_type": "federal_law",
        "official_number": "273-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/36698/print",
        "adoption_date": "2012-12-29",
    },

    # --- Новые законы ---
    {
        "slug": "fz-o-poryadke-vyezda",
        "title": "Федеральный закон «О порядке выезда из Российской Федерации и въезда в Российскую Федерацию»",
        "short_title": "ФЗ №114-ФЗ",
        "doc_type": "federal_law",
        "official_number": "114-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/9895/print",
        "adoption_date": "1996-08-15",
    },
    {
        "slug": "fz-o-personalnykh-dannykh",
        "title": "Федеральный закон «О персональных данных»",
        "short_title": "ФЗ №152-ФЗ",
        "doc_type": "federal_law",
        "official_number": "152-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/24154/print",
        "adoption_date": "2006-07-27",
    },
    {
        "slug": "fz-o-zakupkakh",
        "title": "Федеральный закон «О закупках товаров, работ, услуг отдельными видами юридических лиц»",
        "short_title": "ФЗ №223-ФЗ",
        "doc_type": "federal_law",
        "official_number": "223-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/33622/print",
        "adoption_date": "2011-07-18",
    },
    {
        "slug": "fz-o-kontraktnoi-sisteme",
        "title": "Федеральный закон «О контрактной системе в сфере закупок товаров, работ, услуг для обеспечения государственных и муниципальных нужд»",
        "short_title": "ФЗ №44-ФЗ",
        "doc_type": "federal_law",
        "official_number": "44-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/37056/print",
        "adoption_date": "2013-04-05",
    },
    {
        "slug": "zozpp",
        "title": "Закон Российской Федерации «О защите прав потребителей»",
        "short_title": "ЗоЗПП №2300-1",
        "doc_type": "federal_law",
        "official_number": "2300-1",
        "kremlin_url": "http://pravo.gov.ru/proxy/ips?doc_itself&nd=102014512&page=1&rdk=51",
        "adoption_date": "1992-02-07",
    },
    {
        "slug": "apk-rf",
        "title": "Арбитражный процессуальный кодекс Российской Федерации",
        "short_title": "АПК РФ",
        "doc_type": "code",
        "official_number": "95-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/18937/print",
        "adoption_date": "2002-07-24",
    },
    {
        "slug": "kas-rf",
        "title": "Кодекс административного судопроизводства Российской Федерации",
        "short_title": "КАС РФ",
        "doc_type": "code",
        "official_number": "21-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/39498/print",
        "adoption_date": "2015-03-08",
    },
    {
        "slug": "upk-rf",
        "title": "Уголовно-процессуальный кодекс Российской Федерации",
        "short_title": "УПК РФ",
        "doc_type": "code",
        "official_number": "174-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/17643/print",
        "adoption_date": "2001-12-18",
    },
    {
        "slug": "gpk-rf",
        "title": "Гражданский процессуальный кодекс Российской Федерации",
        "short_title": "ГПК РФ",
        "doc_type": "code",
        "official_number": "138-ФЗ",
        "kremlin_url": "http://kremlin.ru/acts/bank/18837/print",
        "adoption_date": "2002-11-14",
    },
]


def fetch_text(url: str) -> str | None:
    try:
        r = CLIENT.get(url)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"  Failed: {e}")
        return None
    clean = re.sub(r"<script[^>]*>.*?</script>", "", r.text, flags=re.DOTALL | re.I)
    clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.I)
    # Insert newlines before numbered пункты markers in kontur HTML
    clean = re.sub(r'<span class="dt-m">', r'\n<span class="dt-m">', clean)
    clean = re.sub(r"<br\s*/?>", "\n", clean)
    clean = re.sub(r"</p>", "\n\n", clean)
    clean = re.sub(r"</?[^>]+>", " ", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"&lt;", "<", clean)
    clean = re.sub(r"&gt;", ">", clean)
    clean = re.sub(r"&amp;", "&", clean)
    clean = re.sub(r"[ \t]+", " ", clean).strip()
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


def parse_plenum_items(text: str) -> list[dict]:
    items = []
    order = 0
    current_section = ""
    section_header_pattern = re.compile(r"^[А-ЯЁA-Z][А-ЯЁA-Za-z\s\-–—]{2,80}$")

    # Insert extra newlines before known section headers to help splitting
    for section_kw in ["Штраф", "Лишение права", "Лишение специального",
                       "Обязательные работы", "Исправительные работы",
                       "Ограничение свободы", "Принудительные работы",
                       "Лишение свободы", "Общие начала", "Учет обстоятельств",
                       "Порядок исчисления", "Назначение наказания по совокупности",
                       "Назначение дополнительного", "Условное осуждение",
                       "Заключительные положения",
                       "Отношения, регулируемые", "Существенный недостаток",
                       "Процессуальные особенности", "Способы защиты"]:
        text = text.replace(section_kw, f"\n{section_kw}")

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if section_header_pattern.match(line) and not re.match(r"^\d+\.\s", line):
            current_section = line
            continue

    # Now extract items by matching numbered пункты across the text
    # Pattern: number. content (followed by next number. or end)
    pattern = re.compile(r"(?<!\d)(\d+)\.\s+(.*?)(?=(?<!\d)\d+\.\s+[A-ZА-Я]|\Z)", re.DOTALL)
    for m in pattern.finditer(text):
        num = m.group(1).strip()
        content = m.group(2).strip()
        content = re.sub(r"\s+", " ", content).strip()
        if len(content) < 10:
            continue
        order += 1
        title = ""
        colon_pos = content.find(":")
        if colon_pos > 0 and colon_pos < 200:
            candidate = content[:colon_pos].strip()
            if not re.search(r"[а-я]\s*[а-я]", candidate, re.I) or len(candidate.split()) <= 10:
                title = candidate
                content = content[colon_pos + 1:].strip()
                content = re.sub(r"^\d+\s*", "", content).strip()
        if not content:
            content = title
            title = ""
        items.append({
            "number": num,
            "title": title or "",
            "content": content,
            "chapter": "",
            "section": current_section,
            "order": order,
        })

    return items


def main():
    from src.shared.database import init_db, get_db
    from src.shared.queries import UPSERT_DOCUMENT, UPSERT_ARTICLE
    init_db()
    log.info("DB initialized")

    total_articles = 0
    total_chars = 0

    for law in DOCUMENTS:
        log.info(f"\n=== {law['title']} ({law['slug']}) ===")
        log.info(f"  Fetching {law['kremlin_url']}...")
        t0 = time.time()
        text = fetch_text(law["kremlin_url"])
        elapsed = time.time() - t0
        if not text:
            log.warning(f"  FAILED after {elapsed:.1f}s")
            continue

        log.info(f"  Downloaded {len(text)} chars in {elapsed:.1f}s")

        if law["doc_type"] == "plenum":
            articles = parse_plenum_items(text)
        else:
            articles = parse_articles(text)
        log.info(f"  Parsed {len(articles)} articles")

        if not articles:
            log.warning("  No articles parsed, skip")
            continue

        with get_db() as conn:
            doc_id = conn.execute(
                UPSERT_DOCUMENT,
                (law["slug"], law["title"], law["short_title"],
                 law["doc_type"], law["official_number"],
                 law["adoption_date"], None, law["kremlin_url"], "{}"),
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
        total_articles += len(articles)
        total_chars += len(text)

    CLIENT.close()
    log.info(f"\n{'='*60}")
    log.info(f"Done! Total: {total_articles} articles from {len(DOCUMENTS)} documents")
    log.info(f"Total chars downloaded: {total_chars:,}")


if __name__ == "__main__":
    main()
