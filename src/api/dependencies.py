from src.shared.database import get_db


def get_db_conn():
    with get_db() as conn:
        yield conn
