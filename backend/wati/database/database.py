import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL") or os.getenv("DATABASE_URL")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True, pool_recycle=120, pool_pre_ping=True, pool_size=30)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
