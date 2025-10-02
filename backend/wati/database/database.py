import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present (safe locally, ignored in production)
load_dotenv()

# Tries SQLALCHEMY_DATABASE_URL first, falls back to DATABASE_URL
SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL") or os.getenv("DATABASE_URL")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# This will raise an error early if env variable is missing or blank
if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError("No database URL found! Set SQLALCHEMY_DATABASE_URL or DATABASE_URL as an environment variable.")

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=True,
    pool_recycle=120,
    pool_pre_ping=True,
    pool_size=30
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# Dependency for FastAPI routes to get DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
