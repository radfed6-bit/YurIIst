from src.agent.agent import _sanitize_input, _validate_tool_call, ALLOWED_SLUGS


def test_sanitize_input_truncates():
    long_text = "x" * 5000
    assert len(_sanitize_input(long_text)) <= 4096


def test_sanitize_input_filters_angle_brackets():
    assert _sanitize_input("a <<b>> c") == "a <>b<> c"
    assert _sanitize_input("a >>> b") == "a <> b"


def test_sanitize_input_strips():
    assert _sanitize_input("  hello world  ") == "hello world"


def test_validate_search_legal_db():
    args = {"query": "test query", "top_k": "100", "doc_slug": "uk-rf"}
    result = _validate_tool_call("search_legal_db", args)
    assert result["query"] == "test query"
    assert result["top_k"] <= 50
    assert result["doc_slug"] == "uk-rf"


def test_validate_search_legal_db_invalid_slug():
    args = {"query": "test", "doc_slug": "malicious-slug"}
    result = _validate_tool_call("search_legal_db", args)
    assert "doc_slug" not in result or result["doc_slug"] == ""


def test_validate_get_article():
    args = {"slug": "gk-rf", "article_number": "158"}
    result = _validate_tool_call("get_article", args)
    assert result["slug"] == "gk-rf"
    assert result["article_number"] == "158"


def test_validate_get_article_invalid_slug():
    args = {"slug": "evil-site", "article_number": "1"}
    result = _validate_tool_call("get_article", args)
    assert result["slug"] == ""


def test_validate_web_fetch():
    args = {"url": "https://example.com/page"}
    result = _validate_tool_call("web_fetch", args)
    assert result["url"] == "https://example.com/page"


def test_validate_truncates_long_values():
    args = {"query": "x" * 1000, "top_k": "3"}
    result = _validate_tool_call("search_legal_db", args)
    assert len(result["query"]) <= 500


def test_allowed_slugs_are_defined():
    assert len(ALLOWED_SLUGS) >= 20
    assert "uk-rf" in ALLOWED_SLUGS
    assert "gk-rf" in ALLOWED_SLUGS
