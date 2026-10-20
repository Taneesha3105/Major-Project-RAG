"""FastAPI application factory and lifespan (job workers, model warm-up)."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.ai import embeddings, reranker
from app.controllers import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import engine
from app.services.document_service import resume_pending_documents
from app.services.job_queue import analysis_queue, ingestion_queue

configure_logging()
logger = logging.getLogger(__name__)


async def _warm_models() -> None:
    try:
        await asyncio.to_thread(embeddings.warmup)
        await asyncio.to_thread(reranker.warmup)
        logger.info("Embedding and reranker models are ready.")
    except Exception:  # noqa: BLE001 - models also load lazily on first use
        logger.exception("Model warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    ingestion_queue.start()
    analysis_queue.start()
    resumed = await resume_pending_documents()
    if resumed:
        logger.info("Re-queued %s unfinished document(s).", resumed)
    warmup_task = asyncio.create_task(_warm_models())
    if not settings.llm_configured:
        logger.warning("GEMINI_API_KEY is not set: chat and AI analysis are disabled.")
    yield
    warmup_task.cancel()
    await ingestion_queue.stop()
    await analysis_queue.stop()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-assisted M&A due diligence: virtual data room, evidence-backed Q&A, risk register and checklist.",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
