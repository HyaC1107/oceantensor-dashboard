import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.config import settings
from app.metrics import update_sensor_metrics  # noqa: F401 — must import before routers to register gauges first
from app.db import init_db
from app.routers import sensor, predict, explain, rag, ws, admin, v7, realdata


async def _run_collectors():
    """공공API 수집 스케줄러"""
    from data_pipeline.collectors import nifs_collector, kma_collector

    # 서버 시작 시 femoSeaList 1년치 초기 수집 (1회)
    try:
        saved = await nifs_collector.collect_femo_and_save(days=365)
        print(f"[scheduler] NIFS femoSeaList 초기 수집: {saved}건 저장")
    except Exception as e:
        print(f"[scheduler] NIFS femoSeaList 초기 수집 실패: {e}")

    # 서버 시작 시 sooList 1년치 초기 수집 (1회)
    try:
        from data_pipeline.collectors import nifs_soo_collector
        saved = await nifs_soo_collector.collect_soo_and_save(days=365)
        print(f"[scheduler] NIFS sooList 초기 수집: {saved}건 저장")
    except Exception as e:
        print(f"[scheduler] NIFS sooList 초기 수집 실패: {e}")

    while True:
        await asyncio.sleep(3600)
        # risaList: 실시간 수온 (1시간 주기)
        try:
            saved = await nifs_collector.collect_and_save()
            print(f"[scheduler] NIFS risaList: {saved}건 저장")
        except Exception as e:
            print(f"[scheduler] NIFS risaList 실패: {e}")

        # KMA 일자료 강수량 (1시간 주기, 최근 7일)
        try:
            cnt = await kma_collector.collect_and_save(days=7)
            print(f"[scheduler] KMA ASOS 일자료: {cnt}건 확인")
        except Exception as e:
            print(f"[scheduler] KMA ASOS 일자료 실패: {e}")

        # KMA 시간자료 강수량 (1시간 주기, 최근 24시간)
        try:
            from data_pipeline.collectors import kma_hourly_collector
            cnt = await kma_hourly_collector.collect_and_save(hours=24)
            print(f"[scheduler] KMA ASOS 시간자료: {cnt}건 확인")
        except Exception as e:
            print(f"[scheduler] KMA ASOS 시간자료 실패: {e}")

        # sooList 정선관측 (1시간 주기로 체크 — 분기 조사라 신규건만 저장)
        try:
            from data_pipeline.collectors import nifs_soo_collector
            saved = await nifs_soo_collector.collect_soo_and_save(days=90)
            print(f"[scheduler] NIFS sooList: {saved}건 저장")
        except Exception as e:
            print(f"[scheduler] NIFS sooList 실패: {e}")

        # K-water 수문 운영 정보 (1시간 주기, 최근 1일)
        try:
            from data_pipeline.collectors import kwater_collector
            saved = await kwater_collector.collect_and_save(days=1)
            print(f"[scheduler] K-water 수문: {saved}건 저장")
        except Exception as e:
            print(f"[scheduler] K-water 수문 실패: {e}")


async def _run_metrics_updater():
    """15초마다 Prometheus 게이지 갱신 — WebSocket 연결 없어도 동작"""
    from app.routers.ws import _generate_mock_payload, _get_latest_from_db
    while True:
        try:
            if settings.use_mock_data:
                data = _generate_mock_payload()
            else:
                data = await _get_latest_from_db() or _generate_mock_payload()
            update_sensor_metrics(data)
        except Exception as e:
            print(f"[metrics] 갱신 실패: {e}")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(_run_collectors())
    metrics_task = asyncio.create_task(_run_metrics_updater())
    yield
    task.cancel()
    metrics_task.cancel()


app = FastAPI(
    title="어텐션플리즈 — 황백화 조기경보 시스템",
    description="Edge Tiny Transformer 기반 양식 김 황백화 조기 탐지 (ATTENTIONPLZ)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensor.router, prefix="/sensor", tags=["sensor"])
app.include_router(predict.router, prefix="/predict", tags=["predict"])
app.include_router(v7.router, prefix="/predict", tags=["predict-v7"])
app.include_router(explain.router, prefix="/explain", tags=["explain"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(ws.router, tags=["websocket"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
# 실데이터(Bronze) — 어장 최근접 관측소 실측값 (mock 모드와 무관하게 DB 직결)
app.include_router(realdata.router, prefix="/real", tags=["realdata"])

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "seaweed-hwangbaek"}
