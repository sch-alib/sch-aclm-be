from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    adapter_type: str
    host: str
    site_name: str
    hostname: str
    port: int
    enabled: bool


class CertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    common_name: str
    sans: str
    ca_type: str
    external_order_id: str | None
    external_certificate_id: str | None
    management_state: str
    status: str
    valid_to: datetime | None
    thumbprint: str | None
    last_pfx_path: str | None


class IssuanceCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    consecutive_failures: int
    last_checked_at: datetime | None
    next_check_at: datetime | None
    last_error: str | None

    @field_serializer("last_checked_at", "next_check_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class CertificateDetailResponse(CertificateResponse):
    targets: list[TargetResponse]
    renewal_available: bool = True
    issuance_check: IssuanceCheckResponse | None = None


class RevokeRequest(BaseModel):
    reason: str


class OffboardRequest(BaseModel):
    reason: str = Field(min_length=5)


class NewCertificateOrderRequest(BaseModel):
    common_name: str = Field(min_length=1, max_length=300)
    dns_names: list[str] = Field(default_factory=list, max_length=100)
    csr_pem: str = Field(min_length=50, max_length=20000)
    product_name_id: Literal["ssl_plus", "ssl_multi_domain", "ssl_wildcard"]
    organization_id: int = Field(gt=0)
    validity_days: int = Field(ge=1, le=199)


class OrderDefaultsResponse(BaseModel):
    product_name_id: str
    organization_id: int | None
    validity_days: int
