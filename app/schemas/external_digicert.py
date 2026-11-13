from typing import Any

from pydantic import BaseModel, Field


class ExternalCertificateResponse(BaseModel):
    order_id: str
    certificate_id: str | None = None
    common_name: str
    dns_names: list[str] = []
    status: str
    valid_till: str | None = None
    days_remaining: int | None = None
    product_name_id: str | None = None
    organization_name: str | None = None
    management_state: str
    local_certificate_id: int | None = None


class ExternalDetailResponse(BaseModel):
    external: dict[str, Any]
    management_state: str
    local_certificate_id: int | None = None


class OnboardRequest(BaseModel):
    common_name: str = ""
    certificate_id: str | None = None
    target_name: str = "IIS target"
    host: str
    site_name: str = "Default Web Site"
    hostname: str
    port: int = 443
    csr_pem: str | None = None
    reason: str = Field(min_length=5)


class CaOnlyReissueRequest(BaseModel):
    common_name: str = ""
    csr_pem: str | None = None
    reason: str = Field(min_length=5)
