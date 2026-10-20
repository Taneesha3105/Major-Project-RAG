from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(slots=True)
class ReadinessSnapshot:
    status: str
    database_ready: bool
    embedding_ready: bool
    embedding_required: bool
    embedding_state: str
    embedding_runtime: str | None
    message: str


class AppReadinessState:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._database_ready = False
            self._embedding_ready = True
            self._embedding_required = False
            self._embedding_state = "not_required"
            self._embedding_runtime: str | None = None
            self._message = "Service is starting."

    def begin_startup(self, *, requires_local_embedding: bool, embedding_runtime: str | None) -> None:
        with self._lock:
            self._database_ready = False
            self._embedding_required = requires_local_embedding
            self._embedding_ready = not requires_local_embedding
            self._embedding_state = "warming" if requires_local_embedding else "not_required"
            self._embedding_runtime = embedding_runtime
            self._message = "Service is starting."

    def mark_database_ready(self) -> None:
        with self._lock:
            self._database_ready = True
            if self._embedding_ready:
                self._message = "Service is ready."
            else:
                self._message = "Database is ready. Local embedding warmup is still in progress."

    def mark_database_not_ready(self) -> None:
        with self._lock:
            self._database_ready = False
            self._message = "Database is not ready."

    def mark_embedding_warming(self, *, runtime: str | None) -> None:
        with self._lock:
            self._embedding_required = True
            self._embedding_ready = False
            self._embedding_state = "warming"
            self._embedding_runtime = runtime
            self._message = "Local embedding warmup is in progress."

    def mark_embedding_ready(self, *, runtime: str | None) -> None:
        with self._lock:
            self._embedding_required = runtime is not None or self._embedding_required
            self._embedding_ready = True
            self._embedding_state = "ready" if self._embedding_required else "not_required"
            self._embedding_runtime = runtime
            self._message = "Service is ready." if self._database_ready else "Waiting for database readiness."

    def mark_embedding_skipped(self, message: str = "Local embedding warmup is not required.") -> None:
        with self._lock:
            self._embedding_required = False
            self._embedding_ready = True
            self._embedding_state = "not_required"
            self._embedding_runtime = None
            self._message = "Service is ready." if self._database_ready else message

    def mark_embedding_failed(self, message: str, *, runtime: str | None) -> None:
        with self._lock:
            self._embedding_required = True
            self._embedding_ready = False
            self._embedding_state = "failed"
            self._embedding_runtime = runtime
            self._message = message

    def snapshot(self) -> ReadinessSnapshot:
        with self._lock:
            is_ready = self._database_ready and self._embedding_ready
            return ReadinessSnapshot(
                status="ready" if is_ready else "starting",
                database_ready=self._database_ready,
                embedding_ready=self._embedding_ready,
                embedding_required=self._embedding_required,
                embedding_state=self._embedding_state,
                embedding_runtime=self._embedding_runtime,
                message=self._message,
            )


readiness_state = AppReadinessState()
