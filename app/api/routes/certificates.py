from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, require_roles
from app.core.exceptions import DigiCertApiError, GovernanceError
from app.database.session import get_database_session
from app.models.job import Job
from app.models.issuance_check import IssuanceCheck
from app.models.user import User
from app.schemas.certificate import (
    CertificateDetailResponse,
    CertificateResponse,
    IssuanceCheckResponse,
    NewCertificateOrderRequest,
    OffboardRequest,
    OrderDefaultsResponse,
    RevokeRequest,
)
from app.schemas.job import JobResponse
from app.services.certificate_service import certificate_service
from app.services.new_order_service import new_order_service
from app.services.issuance_monitor import issuance_monitor

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get("", response_model=list[CertificateResponse])
def list_certificates(
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
):
    return certificate_service.list_certificates(session)


@router.get("/order-defaults", response_model=OrderDefaultsResponse)
def order_defaults(_: User = Depends(get_current_user)):
    return OrderDefaultsResponse(
        product_name_id=settings.digicert_default_product_name_id,
        organization_id=settings.digicert_default_organization_id or None,
        validity_days=settings.digicert_default_validity_days,
    )


@router.post("", response_model=CertificateResponse, status_code=201)
def create_new_certificate_order(
    request: NewCertificateOrderRequest,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin", "Operator")),
):
    try:
        return new_order_service.create(session, request, user.username)
    except GovernanceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DigiCertApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{certificate_id}", response_model=CertificateDetailResponse)
def get_certificate(
    certificate_id: int,
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
):
    certificate = certificate_service.get_certificate(session, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate was not found")
    detail = CertificateDetailResponse.model_validate(certificate)
    detail.renewal_available = not bool(
        session.query(Job)
        .filter(Job.certificate_id == certificate_id, Job.job_type == "NewOrder")
        .first()
    )
    check = session.get(IssuanceCheck, certificate_id)
    if check is not None:
        detail.issuance_check = IssuanceCheckResponse.model_validate(check)
    return detail


@router.post("/{certificate_id}/renew", response_model=JobResponse)
def renew_and_deploy(
    certificate_id: int,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin", "Operator")),
):
    certificate = certificate_service.get_certificate(session, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate was not found")

    try:
        return certificate_service.renew_and_deploy(
            session=session,
            certificate=certificate,
            actor=user.username,
        )
    except GovernanceError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.post("/{certificate_id}/check-issuance", response_model=CertificateResponse)
def check_issuance(
    certificate_id: int,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin", "Operator")),
):
    certificate = certificate_service.get_certificate(session, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate was not found")
    try:
        return issuance_monitor.check_one(
            session, certificate_id, user.username, force=True
        )
    except GovernanceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DigiCertApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/{certificate_id}/offboard", response_model=CertificateResponse)
def offboard_certificate(
    certificate_id: int,
    request: OffboardRequest,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin", "Operator")),
):
    certificate = certificate_service.get_certificate(session, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate was not found")
    try:
        return certificate_service.offboard(session, certificate, user.username, request.reason)
    except GovernanceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{certificate_id}/revoke", response_model=CertificateResponse)
def revoke_certificate(
    certificate_id: int,
    request: RevokeRequest,
    session: Session = Depends(get_database_session),
    user: User = Depends(require_roles("Admin")),
):
    certificate = certificate_service.get_certificate(session, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate was not found")

    return certificate_service.revoke(
        session=session,
        certificate=certificate,
        actor=user.username,
        reason=request.reason,
    )
