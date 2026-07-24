import pytest

from src.shared.session import (
    clear_session_history,
    create_session,
    delete_session,
    list_sessions,
    load_session,
    rename_session,
    save_document_to_session,
    save_session,
    switch_session,
)


@pytest.mark.asyncio
async def test_create_session(test_db):
    sid, name = await create_session(1, "Моя сессия")
    assert sid > 0
    assert name == "Моя сессия"


@pytest.mark.asyncio
async def test_create_session_truncates_name(test_db):
    sid, name = await create_session(1, "a" * 100)
    assert len(name) == 50


@pytest.mark.asyncio
async def test_list_sessions(test_db):
    await create_session(1, "Первая")
    sessions = await list_sessions(1)
    assert len(sessions) >= 1
    assert sessions[0][1] == "Первая"


@pytest.mark.asyncio
async def test_list_sessions_empty_user(test_db):
    sessions = await list_sessions(999)
    assert len(sessions) == 1  # создаётся дефолтная


@pytest.mark.asyncio
async def test_switch_session(test_db):
    s1, _ = await create_session(1, "A")
    s2, _ = await create_session(1, "B")
    ok = await switch_session(1, s1)
    assert ok is True
    sessions = await list_sessions(1)
    assert sessions[0][0] == s1  # первая — активная


@pytest.mark.asyncio
async def test_switch_session_wrong_user(test_db):
    s1, _ = await create_session(1, "A")
    ok = await switch_session(2, s1)
    assert ok is False


@pytest.mark.asyncio
async def test_delete_session(test_db):
    await create_session(1, "A")
    await create_session(1, "B")
    name = await delete_session(1)
    assert name == "A" or name == "B"
    sessions = await list_sessions(1)
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_save_and_load_session(test_db):
    await create_session(1, "Тест")
    msgs = [{"role": "user", "content": "Привет"}, {"role": "assistant", "content": "И тебе привет"}]
    await save_session(1, msgs)
    loaded, doc_text, doc_name = await load_session(1)
    assert len(loaded) == 2
    assert loaded[0]["content"] == "Привет"
    assert doc_text is None


@pytest.mark.asyncio
async def test_save_session_trims_to_max(test_db):
    await create_session(1, "Тест")
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(50)]
    await save_session(1, msgs)
    loaded, _, _ = await load_session(1)
    assert len(loaded) <= 30


@pytest.mark.asyncio
async def test_clear_session_history(test_db):
    await create_session(1, "Тест")
    await save_session(1, [{"role": "user", "content": "x"}])
    await save_document_to_session(1, "doc text", "doc.txt")
    await clear_session_history(1)
    loaded, doc_text, doc_name = await load_session(1)
    assert loaded == []
    assert doc_text is None
    assert doc_name is None


@pytest.mark.asyncio
async def test_save_document_to_session(test_db):
    await create_session(1, "Тест")
    await save_document_to_session(1, "содержимое документа", "contract.pdf")
    loaded, doc_text, doc_name = await load_session(1)
    assert doc_text == "содержимое документа"
    assert doc_name == "contract.pdf"


@pytest.mark.asyncio
async def test_rename_session(test_db):
    sid, _ = await create_session(1, "Старое имя")
    await rename_session(1, "Новое имя")
    sessions = await list_sessions(1)
    current_name = dict(sessions).get(sid)
    # активная сессия — первая в списке
    assert sessions[0][1] == "Новое имя"


@pytest.mark.asyncio
async def test_user_isolation(test_db):
    s1, _ = await create_session(1, "Пользователь А")
    await save_session(1, [{"role": "user", "content": "секрет А"}])
    s2, _ = await create_session(2, "Пользователь Б")
    await save_session(2, [{"role": "user", "content": "секрет Б"}])
    msgs1, _, _ = await load_session(1)
    msgs2, _, _ = await load_session(2)
    assert msgs1[0]["content"] == "секрет А"
    assert msgs2[0]["content"] == "секрет Б"


@pytest.mark.asyncio
async def test_save_preserves_document_not_overwritten(test_db):
    """save_session без document не затирает документ, добавленный через save_document"""
    await create_session(1, "Тест")
    await save_document_to_session(1, "важный документ", "doc.txt")
    await save_session(1, [{"role": "user", "content": "привет"}])
    loaded, doc_text, doc_name = await load_session(1)
    assert doc_text == "важный документ"
    assert doc_name == "doc.txt"
    assert loaded[0]["content"] == "привет"


@pytest.mark.asyncio
async def test_ensure_active_session_respects_user_id(test_db):
    """_ensure_active_session не возвращает чужую сессию"""
    await create_session(1, "Юзер 1")
    sessions1 = await list_sessions(1)
    await create_session(2, "Юзер 2")
    sessions2 = await list_sessions(2)
    assert sessions1[0][1] == "Юзер 1"
    assert sessions2[0][1] == "Юзер 2"
