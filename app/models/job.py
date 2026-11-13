from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    certificate_id: Mapped[int | None] = mapped_column(nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
