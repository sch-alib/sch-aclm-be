from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    common_name: Mapped[str] = mapped_column(String(300), index=True)
    sans: Mapped[str] = mapped_column(Text, default="")
    ca_type: Mapped[str] = mapped_column(String(50), default="digicert")
    external_order_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    external_certificate_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    management_state: Mapped[str] = mapped_column(
        String(50), default="Onboarding"
    )
    status: Mapped[str] = mapped_column(String(50), default="Active")
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbprint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    csr_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_pfx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    targets: Mapped[list["Target"]] = relationship(
        back_populates="certificate",
        cascade="all, delete-orphan",
    )
