"""Durable polling schedule for new certificate orders (UTC timestamps)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class IssuanceCheck(Base):
    __tablename__ = "issuance_checks"

    certificate_id: Mapped[int] = mapped_column(
        ForeignKey("certificates.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="Pending")
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
