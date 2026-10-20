from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DealMemberRole, DealStage, DealType, enum_column

if TYPE_CHECKING:
    from app.models.user import User


class Deal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deals"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code_name: Mapped[str | None] = mapped_column(String(60))
    deal_type: Mapped[DealType] = mapped_column(enum_column(DealType), default=DealType.ACQUISITION, nullable=False)
    stage: Mapped[DealStage] = mapped_column(
        enum_column(DealStage), default=DealStage.DUE_DILIGENCE, nullable=False, index=True
    )
    acquirer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_industry: Mapped[str | None] = mapped_column(String(120))
    target_country: Mapped[str | None] = mapped_column(String(80))
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    members: Mapped[list[DealMember]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", passive_deletes=True
    )


class DealMember(Base):
    __tablename__ = "deal_members"
    __table_args__ = (UniqueConstraint("deal_id", "user_id", name="uq_deal_members_deal_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_role: Mapped[DealMemberRole] = mapped_column(
        enum_column(DealMemberRole), default=DealMemberRole.MEMBER, nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    deal: Mapped[Deal] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
