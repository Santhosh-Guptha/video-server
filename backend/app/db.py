from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from .config import settings

# Configure SQLite specific options to prevent database locks
connect_args = {}
if "sqlite" in settings.database_url:
    connect_args = {"timeout": 30.0}

# Active database engine and session maker references
engine = create_async_engine(settings.database_url, future=True, echo=False, connect_args=connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in settings.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

def reset_db_engine(new_url: str):
    """Dynamically re-binds the database engine to a fallback database."""
    global engine, SessionLocal
    connect_args = {"timeout": 30.0} if "sqlite" in new_url else {}
    engine = create_async_engine(new_url, future=True, echo=False, connect_args=connect_args)
    
    # Listen to connection event for fallback DB
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma_fallback(dbapi_connection, connection_record):
        if "sqlite" in new_url:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
            
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    print(f"[db] Database engine re-bound to: {new_url}")
