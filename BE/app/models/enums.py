"""Domain enumerations shared by models, schemas and services."""

from enum import StrEnum

import sqlalchemy as sa


def enum_column(enum_cls: type[StrEnum]) -> sa.Enum:
    """Store enums as VARCHAR values (not native PG enums) so adding values needs no migration."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class UserRole(StrEnum):
    ADMIN = "admin"
    DEAL_LEAD = "deal_lead"
    ANALYST = "analyst"
    VIEWER = "viewer"


class DealType(StrEnum):
    ACQUISITION = "acquisition"
    MERGER = "merger"
    ASSET_PURCHASE = "asset_purchase"
    JOINT_VENTURE = "joint_venture"
    DIVESTITURE = "divestiture"


class DealStage(StrEnum):
    SCREENING = "screening"
    LOI = "loi"
    DUE_DILIGENCE = "due_diligence"
    NEGOTIATION = "negotiation"
    CLOSING = "closing"
    CLOSED = "closed"
    TERMINATED = "terminated"


class DealMemberRole(StrEnum):
    LEAD = "lead"
    MEMBER = "member"
    OBSERVER = "observer"


class DocumentCategory(StrEnum):
    FINANCIAL = "financial"
    LEGAL = "legal"
    TAX = "tax"
    CONTRACTS = "contracts"
    HR = "hr"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    REGULATORY = "regulatory"
    OPERATIONAL = "operational"
    COMMERCIAL = "commercial"
    IT = "it"
    ENVIRONMENTAL = "environmental"
    CORPORATE = "corporate"
    OTHER = "other"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChecklistStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FLAGGED = "flagged"
    NOT_APPLICABLE = "not_applicable"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceCoverage(StrEnum):
    FOUND = "found"
    PARTIAL = "partial"
    MISSING = "missing"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(StrEnum):
    RISK = "risk"
    CONTRADICTION = "contradiction"
    MISSING_INFORMATION = "missing_information"
    OPPORTUNITY = "opportunity"


class FindingStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class FindingSource(StrEnum):
    AI = "ai"
    MANUAL = "manual"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
