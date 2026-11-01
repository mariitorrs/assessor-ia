from functools import wraps
import logging

import psycopg2

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)


def get_conn():
    """Open and return a PostgreSQL connection. The caller closes it."""
    if not DATABASE_URL:
        raise psycopg2.OperationalError("DATABASE_URL is not configured")
    return psycopg2.connect(DATABASE_URL)


def handle_database_unavailable(func):
    """Return a tool-friendly error when PostgreSQL cannot be reached."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except psycopg2.OperationalError:
            logger.exception("Could not connect to the financial database")
            return {
                "status": "error",
                "message": (
                    "Banco financeiro indisponivel. Confira se o PostgreSQL esta ativo "
                    "e se DATABASE_URL aponta para o host e a porta atuais."
                ),
            }

    return wrapped
