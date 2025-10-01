from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import database
from .routes import user, broadcast, contacts, auth, woocommerce, integration, wallet, analytics
from .services import dramatiq_router
from . import oauth2
from .models import ChatBox
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.future import select
from datetime import datetime, timedelta
from typing import AsyncGenerator


app = FastAPI()
scheduler = AsyncIOScheduler()
scheduler_started = False


# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(broadcast.router, prefix="/broadcast")
# app.include_router(broadcast.router)  # also expose broadcast routes at root (e.g. /template)
app.include_router(contacts.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(wallet.router)
app.include_router(oauth2.router)
app.include_router(dramatiq_router.router)
app.include_router(woocommerce.router)
app.include_router(integration.router)
app.include_router(analytics.router)


async def create_db_and_tables():
    async with database.engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)


async def close_expired_chats() -> None:
    """
    Close chats that have been inactive for more than 1440 minutes (1 day).
    """
    try:
        async for session in database.get_db():  # assumes get_db is an async generator
            now = datetime.utcnow()
            threshold = now - timedelta(minutes=1440)

            result = await session.execute(
                select(ChatBox.Last_Conversation).where(
                    ChatBox.Last_Conversation.active == True,
                    ChatBox.Last_Conversation.last_chat_time < threshold
                )
            )
            expired_conversations = result.scalars().all()

            for conversation in expired_conversations:
                conversation.active = False

            await session.commit()
            break  # use the first session returned from the generator
    except Exception as e:
        print(f"Error in close_expired_chats: {e}")


@app.on_event("startup")
async def startup_event() -> None:
    """
    Runs DB creation and starts scheduler once at app startup.
    """
    global scheduler_started
    await create_db_and_tables()
    if not scheduler_started:
        scheduler.add_job(close_expired_chats, "interval", minutes=1)
        scheduler.start()
        scheduler_started = True
        print("Scheduler started.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """
    Stops scheduler on shutdown.
    """
    global scheduler_started
    if scheduler_started:
        scheduler.shutdown(wait=False)
        scheduler_started = False
        print("Scheduler shut down.")