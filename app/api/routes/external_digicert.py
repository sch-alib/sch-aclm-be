from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.core.exceptions import GovernanceError
from app.database.session import get_database_session
from app.models.user import User
from app.schemas.certificate import CertificateResponse
from app.schemas.external_digicert import (
    CaOnlyReissueRequest,
    ExternalCertificateResponse,
    ExternalDetailResponse,
    OnboardRequest,
)
from app.schemas.job import JobResponse
from app.services.certificate_service import certificate_service
from app.services.external_inventory_service import external_inventory_service

router = APIRouter(
    prefix="/external/digicert",
    tags=["External DigiCert Inventory"],
)


@router.get("", response_model=list[ExternalCertificateResponse])
def list_external_certificates(
    common_name: str | None = None,
    domain_name: str | None = None,
    valid_till: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
):
    filters = {
        "common_name": common_name,
        "domain_name": domain_name,
        "valid_till": valid_till,
        "limit": limit,
        "offset": offset,
    }
    return external_inventory_service.list_digicert_certificates(
        session,
        filters,
    )


@router.get("/{order_id}", response_model=ExternalDetailResponse)
def get_external_certificate_details(
    order_id: str,
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
):
    return external_inventory_service.get_digicert_details(session, order_id)


@router.post("/{order_id}/onboard", response_model=CertificateResponse)
def onboard_external_certificate(
    order_id: str,
    request: OnboardRequest,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin", "Operator")),
):
    try:
        return external_inventory_service.onboard(
            session=session,
            order_id=order_id,
            request=request,
            actor=user.username,
        )
    except GovernanceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{order_id}/ca-only-reissue", response_model=JobResponse)
def ca_only_reissue(
    order_id: str,
    request: CaOnlyReissueRequest,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin")),
):
    return certificate_service.ca_only_reissue(
        session=session,
        order_id=order_id,
        request=request,
        actor=user.username,
    )
