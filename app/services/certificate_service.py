from sqlalchemy.orm import Session

from app.adapters.registry import adapter_registry
from app.core.exceptions import GovernanceError
from app.models.certificate import Certificate
from app.models.job import Job
from app.repositories.certificate_repository import certificate_repository
from app.repositories.job_repository import job_repository
from app.schemas.external_digicert import CaOnlyReissueRequest
from app.services.audit_service import audit_service
from app.services.orchestration_service import orchestration_service


class CertificateService:
    def list_certificates(self, session: Session) -> list[Certificate]:
        return certificate_repository.list_all(session)

    def get_certificate(
        self,
        session: Session,
        certificate_id: int,
    ) -> Certificate | None:
        return certificate_repository.get_by_id(session, certificate_id)

    def renew_and_deploy(
        self,
        session: Session,
        certificate: Certificate,
        actor: str,
    ) -> Job:
        return orchestration_service.renew_and_deploy(
            session=session,
            certificate=certificate,
            actor=actor,
        )

    def offboard(
        self,
        session: Session,
        certificate: Certificate,
        actor: str,
        reason: str,
    ) -> Certificate:
        if certificate.management_state != "Managed":
            raise GovernanceError("Only managed certificates can be offboarded")
        certificate.management_state = "Offboarded"
        for target in certificate.targets:
            target.enabled = False
        saved = certificate_repository.save(session, certificate)
        audit_service.record(
            session=session,
            actor=actor,
            action="offboard",
            entity_reference=f"certificate:{certificate.id}",
            reason=reason,
        )
        return saved

    def revoke(
        self,
        session: Session,
        certificate: Certificate,
        actor: str,
        reason: str,
    ) -> Certificate:
        adapter = adapter_registry.get_ca_adapter(certificate.ca_type)
        adapter.revoke_certificate(
            certificate_id=certificate.external_certificate_id or "",
            reason=reason,
        )
        certificate.status = "Revoked"
        saved_certificate = certificate_repository.save(session, certificate)
        audit_service.record(
            session=session,
            actor=actor,
            action="revoke",
            entity_reference=f"certificate:{certificate.id}",
            reason=reason,
        )
        return saved_certificate

    def ca_only_reissue(
        self,
        session: Session,
        order_id: str,
        request: CaOnlyReissueRequest,
        actor: str,
    ) -> Job:
        adapter = adapter_registry.get_ca_adapter("digicert")
        details = adapter.get_order_details(order_id)
        external_certificate = details.get("certificate") or details

        adapter.reissue_certificate(
            order_id=order_id,
            common_name=(
                external_certificate.get("common_name") or request.common_name
            ),
            dns_names=external_certificate.get("dns_names") or [],
            csr_pem=request.csr_pem,
            reason=f"CA-only reissue: {request.reason}",
        )

        job = Job(
            external_order_id=order_id,
            job_type="CAOnlyReissue",
            status="Succeeded",
            actor=actor,
            message="CA operation completed; no target devices were updated.",
        )
        created_job = job_repository.create(session, job)
        audit_service.record(
            session=session,
            actor=actor,
            action="ca-only-reissue",
            entity_reference=f"digicert-order:{order_id}",
            reason=request.reason,
        )
        return created_job


certificate_service = CertificateService()
