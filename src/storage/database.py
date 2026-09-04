import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.storage.models import Base


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "a_share_review.db"


def database_url(path: str | Path | None = None) -> str:
    configured = path or os.getenv("A_SHARE_DB_PATH") or DEFAULT_DB_PATH
    if str(configured) == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    db_path = Path(configured).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def create_db_engine(path: str | Path | None = None) -> Engine:
    engine = create_engine(database_url(path), future=True)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]):
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
