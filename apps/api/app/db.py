from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings

SCHEMA_REVISION = "0008_agent_workbench"


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(
        settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
    )


def database():
    with Session(engine()) as session:
        yield session
