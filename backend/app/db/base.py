from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from app.core.logging import logger

# SQLite needs check_same_thread=False for FastAPI's threaded access
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema():
    """
    create_all() creates missing tables but never missing columns, so a DB from an
    older build keeps working only if we patch new columns in.
    ponytail: good enough for SQLite dev data — use Alembic once migrations get real.
    """
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table.name})")}
            for column in table.columns:
                if existing and column.name not in existing:
                    col_type = column.type.compile(engine.dialect)
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"
                    )
                    logger.info(f"Schema updated: added {table.name}.{column.name}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
