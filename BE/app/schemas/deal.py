import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DealMemberRole, DealStage, DealType
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class DealBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code_name: str | None = Field(default=None, max_length=60)
    deal_type: DealType = DealType.ACQUISITION
    stage: DealStage = DealStage.DUE_DILIGENCE
    acquirer_name: str = Field(min_length=1, max_length=160)
    target_name: str = Field(min_length=1, max_length=160)
    target_industry: str | None = Field(default=None, max_length=120)
    target_country: str | None = Field(default=None, max_length=80)
    deal_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    expected_close_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.upper()


class DealCreate(DealBase):
    seed_checklist: bool = True


class DealUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code_name: str | None = Field(default=None, max_length=60)
    deal_type: DealType | None = None
    stage: DealStage | None = None
    acquirer_name: str | None = Field(default=None, min_length=1, max_length=160)
    target_name: str | None = Field(default=None, min_length=1, max_length=160)
    target_industry: str | None = Field(default=None, max_length=120)
    target_country: str | None = Field(default=None, max_length=80)
    deal_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    expected_close_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)


class DealStats(BaseModel):
    document_count: int = 0
    ready_document_count: int = 0
    open_risk_count: int = 0
    critical_risk_count: int = 0
    checklist_total: int = 0
    checklist_completed: int = 0
    member_count: int = 0
    readiness_score: int = 0


class DealRead(ORMModel):
    id: uuid.UUID
    name: str
    code_name: str | None
    deal_type: DealType
    stage: DealStage
    acquirer_name: str
    target_name: str
    target_industry: str | None
    target_country: str | None
    deal_value: Decimal | None
    currency: str
    expected_close_date: date | None
    description: str | None
    executive_summary: str | None
    created_at: datetime
    updated_at: datetime
    stats: DealStats = Field(default_factory=DealStats)


class DealMemberCreate(BaseModel):
    user_id: uuid.UUID
    member_role: DealMemberRole = DealMemberRole.MEMBER


class DealMemberRead(ORMModel):
    id: uuid.UUID
    member_role: DealMemberRole
    added_at: datetime
    user: UserBrief
