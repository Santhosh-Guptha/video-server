from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from .config import settings

# Active database engine and session maker references
engine = create_async_engine(settings.database_url, future=True, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

def reset_db_engine(new_url: str):
    """Dynamically re-binds the database engine to a fallback database."""
    global engine, SessionLocal
    engine = create_async_engine(new_url, future=True, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    print(f"[db] Database engine re-bound to: {new_url}")
