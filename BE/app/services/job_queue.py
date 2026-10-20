"""In-process background job queue for long-running work (document ingestion, AI analysis).

Jobs run on worker tasks owned by the FastAPI lifespan, so requests return immediately while
CPU-bound steps (OCR, embeddings) execute in threads. For multi-node deployments replace this
with Celery/RQ/Arq — callers only depend on `submit()`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]


class JobQueue:
    def __init__(self, name: str, concurrency: int = 1) -> None:
        self.name = name
        self.concurrency = concurrency
        self._queue: asyncio.Queue[tuple[str, Job]] | None = None
        self._workers: list[asyncio.Task] = []

    def start(self) -> None:
        self._queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"{self.name}-worker-{index}")
            for index in range(self.concurrency)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    def submit(self, label: str, job: Job) -> None:
        if self._queue is None:
            raise RuntimeError(f"Job queue '{self.name}' is not running")
        self._queue.put_nowait((label, job))

    @property
    def pending(self) -> int:
        return self._queue.qsize() if self._queue else 0

    async def _worker(self, index: int) -> None:
        assert self._queue is not None
        while True:
            label, job = await self._queue.get()
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one failing job must not kill the worker
                logger.exception("%s job '%s' failed", self.name, label)
            finally:
                self._queue.task_done()


ingestion_queue = JobQueue("ingestion", concurrency=settings.ingestion_concurrency)
analysis_queue = JobQueue("analysis", concurrency=1)
