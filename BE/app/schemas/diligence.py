import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    AnalysisStatus,
    ChecklistStatus,
    DocumentCategory,
    EvidenceCoverage,
    FindingSource,
    FindingStatus,
    FindingType,
    Priority,
    Severity,
)
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


# --- Checklist ----------------------------------------------------------------
class ChecklistItemCreate(BaseModel):
    category: DocumentCategory
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    priority: Priority = Priority.MEDIUM
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None


class ChecklistItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: ChecklistStatus | None = None
    priority: Priority | None = None
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ChecklistItemRead(ORMModel):
    id: uuid.UUID
    category: DocumentCategory
    title: str
    description: str | None
    status: ChecklistStatus
    priority: Priority
    assignee: UserBrief | None
    due_date: date | None
    notes: str | None
    ai_coverage: EvidenceCoverage | None
    ai_note: str | None
    ai_citations: list[dict[str, Any]]
    ai_reviewed_at: datetime | None
    updated_at: datetime


class ChecklistReviewResult(BaseModel):
    reviewed: int
    found: int
    partial: int
    missing: int


# --- Risk findings ------------------------------------------------------------
class RiskFindingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3, max_length=8000)
    category: DocumentCategory
    finding_type: FindingType = FindingType.RISK
    severity: Severity = Severity.MEDIUM
    recommendation: str | None = Field(default=None, max_length=4000)
    financial_impact: str | None = Field(default=None, max_length=255)
    owner_id: uuid.UUID | None = None


class RiskFindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=3, max_length=8000)
    category: DocumentCategory | None = None
    finding_type: FindingType | None = None
    severity: Severity | None = None
    status: FindingStatus | None = None
    recommendation: str | None = Field(default=None, max_length=4000)
    financial_impact: str | None = Field(default=None, max_length=255)
    owner_id: uuid.UUID | None = None
    resolution_note: str | None = Field(default=None, max_length=4000)


class RiskFindingRead(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    title: str
    description: str
    category: DocumentCategory
    finding_type: FindingType
    severity: Severity
    status: FindingStatus
    source: FindingSource
    recommendation: str | None
    financial_impact: str | None
    citations: list[dict[str, Any]]
    owner: UserBrief | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime


# --- Analysis runs ------------------------------------------------------------
class AnalysisRequest(BaseModel):
    categories: list[DocumentCategory] = Field(default_factory=list)
    replace_previous_ai_findings: bool = True


class AnalysisRunRead(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    status: AnalysisStatus
    categories: list[str]
    progress: int
    findings_count: int
    summary: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
