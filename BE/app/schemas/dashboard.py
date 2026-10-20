import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import ORMModel


class AuditLogRead(ORMModel):
    id: int
    deal_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    summary: str
    details: dict[str, Any]
    created_at: datetime
    user_name: str | None = None


class CountBucket(BaseModel):
    key: str
    count: int


class DashboardSummary(BaseModel):
    active_deals: int
    total_deals: int
    documents_total: int
    documents_ready: int
    documents_processing: int
    open_risks: int
    critical_risks: int
    checklist_completion: int
    deals_by_stage: list[CountBucket]
    risks_by_severity: list[CountBucket]
    documents_by_category: list[CountBucket]
    recent_activity: list[AuditLogRead]


class SystemStatus(BaseModel):
    database: bool
    llm_configured: bool
    llm_model: str
    embedding_model: str
    reranker_model: str | None
    ocr_engine: str | None
