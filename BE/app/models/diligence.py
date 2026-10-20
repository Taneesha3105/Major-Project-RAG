"""Due-diligence workflow models: checklist items, risk findings and AI analysis runs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
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
    enum_column,
)

if TYPE_CHECKING:
    from app.models.user import User


class ChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "checklist_items"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[DocumentCategory] = mapped_column(enum_column(DocumentCategory), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ChecklistStatus] = mapped_column(
        enum_column(ChecklistStatus), default=ChecklistStatus.PENDING, nullable=False
    )
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), default=Priority.MEDIUM, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_coverage: Mapped[EvidenceCoverage | None] = mapped_column(enum_column(EvidenceCoverage))
    ai_note: Mapped[str | None] = mapped_column(Text)
    ai_citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    ai_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])


class RiskFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_findings"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[DocumentCategory] = mapped_column(enum_column(DocumentCategory), nullable=False)
    finding_type: Mapped[FindingType] = mapped_column(
        enum_column(FindingType), default=FindingType.RISK, nullable=False
    )
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), default=Severity.MEDIUM, nullable=False)
    status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus), default=FindingStatus.OPEN, nullable=False
    )
    source: Mapped[FindingSource] = mapped_column(
        enum_column(FindingSource), default=FindingSource.MANUAL, nullable=False
    )
    recommendation: Mapped[str | None] = mapped_column(Text)
    financial_impact: Mapped[str | None] = mapped_column(String(255))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])


class AnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_runs"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        enum_column(AnalysisStatus), default=AnalysisStatus.QUEUED, nullable=False
    )
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
