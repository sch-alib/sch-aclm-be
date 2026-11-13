from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    certificate_id: Mapped[int] = mapped_column(ForeignKey("certificates.id"))
    name: Mapped[str] = mapped_column(String(200))
    adapter_type: Mapped[str] = mapped_column(String(50), default="iis")
    host: Mapped[str] = mapped_column(String(300))
    site_name: Mapped[str] = mapped_column(
        String(300), default="Default Web Site"
    )
    hostname: Mapped[str] = mapped_column(String(300))
    port: Mapped[int] = mapped_column(default=443)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    certificate: Mapped["Certificate"] = relationship(back_populates="targets")
