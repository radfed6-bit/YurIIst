"""SQL-запросы для работы с БД."""

GET_CODES = """
    SELECT d.*, COUNT(a.id) as article_count
    FROM documents d
    LEFT JOIN articles a ON a.document_id = d.id
    WHERE d.doc_type IN ('constitution', 'code')
    GROUP BY d.id
    ORDER BY d.title
"""

GET_DOCUMENT_BY_SLUG = """
    SELECT d.*, COUNT(a.id) as article_count
    FROM documents d
    LEFT JOIN articles a ON a.document_id = d.id
    WHERE d.slug = ?
    GROUP BY d.id
"""

GET_ARTICLES_BY_DOC = """
    SELECT * FROM articles
    WHERE document_id = ?
    ORDER BY "order"
"""

GET_ARTICLE_BY_ID = """
    SELECT a.*, d.title as doc_title, d.slug as doc_slug, d.doc_type
    FROM articles a
    JOIN documents d ON d.id = a.document_id
    WHERE a.id = ?
"""

FTS_SEARCH = """
    SELECT a.*, d.title as doc_title, d.slug as doc_slug,
           rank as rank_score
    FROM articles_fts
    JOIN articles a ON a.id = articles_fts.rowid
    JOIN documents d ON d.id = a.document_id
    WHERE articles_fts MATCH ?
    ORDER BY rank
    LIMIT ?
"""

SEARCH_WITH_TYPE = """
    SELECT a.*, d.title as doc_title, d.slug as doc_slug,
           rank as rank_score
    FROM articles_fts
    JOIN articles a ON a.id = articles_fts.rowid
    JOIN documents d ON d.id = a.document_id
    WHERE articles_fts MATCH ? AND d.doc_type = ?
    ORDER BY rank
    LIMIT ?
"""

UPSERT_DOCUMENT = """
    INSERT INTO documents (slug, title, short_title, doc_type, official_number,
                           adoption_date, effective_date, source_url, metadata)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(slug) DO UPDATE SET
        title = excluded.title,
        short_title = excluded.short_title,
        official_number = excluded.official_number,
        source_url = excluded.source_url,
        updated_at = datetime('now')
    RETURNING id
"""

UPSERT_ARTICLE = """
    INSERT INTO articles (document_id, article_number, title, content,
                          chapter, section, "order")
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(document_id, article_number) DO UPDATE SET
        title = excluded.title,
        content = excluded.content,
        "order" = excluded."order"
    RETURNING id
"""
