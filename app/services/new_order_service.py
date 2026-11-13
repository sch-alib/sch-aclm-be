"""New CertCentral orders; issuance is confirmed separately from submission."""

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID
from sqlalchemy.orm import Session

from app.adapters.registry import adapter_registry
from app.core.exceptions import DigiCertApiError, GovernanceError
from app.models.certificate import Certificate
from app.models.job import Job
from app.models.issuance_check import IssuanceCheck
from app.core.config import settings
from app.repositories.certificate_repository import certificate_repository
from app.repositories.job_repository import job_repository
from app.schemas.certificate import NewCertificateOrderRequest
from app.services.audit_service import audit_service
from app.services.certificate_dates import parse_certificate_expiry


class NewOrderService:
    @staticmethod
    def validate_csr(request: NewCertificateOrderRequest) -> None:
        try:
            csr = x509.load_pem_x509_csr(request.csr_pem.encode("ascii"))
            if not csr.is_signature_valid:
                raise ValueError("CSR signature is invalid")
            names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if len(names) != 1 or names[0].value.lower() != request.common_name.lower():
                raise ValueError("CSR common name does not match the order")
            try:
                csr_sans = csr.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                ).value.get_values_for_type(x509.DNSName)
            except x509.ExtensionNotFound:
                csr_sans = []
            # The CSR may also include the common name in its SAN extension.
            expected = {name.lower() for name in request.dns_names}
            actual = {name.lower() for name in csr_sans}
            actual.discard(request.common_name.lower())
            expected.discard(request.common_name.lower())
            if actual != expected:
                raise ValueError("CSR SANs do not match the requested SANs")
        except (ValueError, UnicodeError) as error:
            raise GovernanceError(f"Invalid CSR: {error}") from error

    def create(
        self, session: Session, request: NewCertificateOrderRequest, actor: str
    ) -> Certificate:
        self.validate_csr(request)
        # Guard against accidental repeat submissions while awaiting approval.
        existing = (
            session.query(Certificate)
            .filter(
                Certificate.csr_pem == request.csr_pem,
                Certificate.management_state == "Pending issuance",
            )
            .first()
        )
        if existing:
            raise GovernanceError("A pending order already uses this CSR")

        adapter = adapter_registry.get_ca_adapter("digicert")
        response = adapter.order_certificate(
            common_name=request.common_name,
            dns_names=request.dns_names,
            csr_pem=request.csr_pem,
            product_name_id=request.product_name_id,
            organization_id=request.organization_id,
            validity_days=request.validity_days,
        )
        order_id = str(response["id"])
        certificate = certificate_repository.save(
            session,
            Certificate(
                common_name=request.common_name,
                sans=",".join(request.dns_names),
                ca_type="digicert",
                external_order_id=order_id,
                management_state="Pending issuance",
                status="Pending issuance",
                csr_pem=request.csr_pem,
            ),
        )
        session.add(IssuanceCheck(
            certificate_id=certificate.id,
            status="Pending",
            next_check_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                seconds=max(1, settings.issuance_check_interval_seconds)
            ),
        ))
        job_repository.create(session, Job(
            certificate_id=certificate.id, external_order_id=order_id,
            job_type="NewOrder", status="Pending", actor=actor,
            message="Order submitted to DigiCert; awaiting issuance confirmation.",
        ))
        audit_service.record(session, actor, "order-submitted", f"certificate:{certificate.id}",
                             f"DigiCert order {order_id}")
        return certificate

    def check_issuance(
        self, session: Session, certificate: Certificate, actor: str
    ) -> Certificate:
        if certificate.management_state != "Pending issuance" or not certificate.external_order_id:
            raise GovernanceError("Only pending new orders can be checked")
        adapter = adapter_registry.get_ca_adapter("digicert")
        details = adapter.get_order_details(certificate.external_order_id)
        state = str(details.get("status", "")).lower()
        issued = details.get("certificate") or {}
        certificate_id = issued.get("id") or details.get("certificate_id")
        if not state or (state in {"issued", "active_issued"} and not certificate_id):
            raise DigiCertApiError("DigiCert returned an incomplete order status")
        job = (
            session.query(Job)
            .filter(Job.certificate_id == certificate.id, Job.job_type == "NewOrder")
            .order_by(Job.id.desc())
            .first()
        )
        if state in {"issued", "active_issued"} and certificate_id:
            certificate.management_state = "Managed"
            certificate.status = "Active"
            certificate.external_certificate_id = str(certificate_id)
            certificate.valid_to = parse_certificate_expiry(
                issued.get("valid_till") or details.get("valid_till")
            )
            if job:
                job.status = "Succeeded"
                job.message = "DigiCert issuance confirmed; no deployment performed."
            saved = certificate_repository.save(session, certificate)
            audit_service.record(session, actor, "issuance-confirmed",
                                 f"certificate:{certificate.id}", "DigiCert reports issued")
            return saved
        if state in {"rejected", "cancelled", "canceled"}:
            certificate.management_state = "Order failed"
            certificate.status = state.capitalize()
            if job:
                job.status = "Failed"
                job.message = f"DigiCert order {state}."
            saved = certificate_repository.save(session, certificate)
            audit_service.record(session, actor, "order-failed", f"certificate:{certificate.id}",
                                 f"DigiCert reports {state}")
            return saved
        return certificate


new_order_service = NewOrderService()
