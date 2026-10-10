import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.security import hash_password

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with async_sessionmaker(engine)() as db:
        hp = hash_password("admin123")
        await db.execute(
            text("UPDATE users SET hashed_password=:hp WHERE email=:e"),
            {"hp": hp, "e": "admin@seyarkai.example"}
        )
        await db.commit()
        print("password reset ok")
    await engine.dispose()

asyncio.run(main())
