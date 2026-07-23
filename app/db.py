from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import text
from app.config import settings


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from app.models import sensor, feature, prediction, audit, farm, weather, dam, rag_document  # noqa: F401

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("""
                SELECT create_hypertable(
                    'ocean_sensor_raw', 'observed_at',
                    if_not_exists => TRUE
                );
            """))
    except Exception as e:
        # DB 미실행 시 Mock 모드로 계속 동작
        print(f"[DB] 연결 실패 - Mock 모드로 실행합니다. ({e})")
