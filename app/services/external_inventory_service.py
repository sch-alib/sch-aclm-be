from typing import Any

from sqlalchemy.orm import Session

from app.adapters.registry import adapter_registry
from app.core.exceptions import GovernanceError
from app.models.certificate import Certificate
from app.models.target import Target
from app.repositories.certificate_repository import certificate_repository
from app.schemas.external_digicert import OnboardRequest
from app.services.audit_service import audit_service
from app.services.certificate_dates import parse_certificate_expiry


class ExternalInventoryService:
    def list_digicert_certificates(
        self,
        session: Session,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        adapter = adapter_registry.get_ca_adapter("digicert")
        external_records = adapter.list_certificates(filters)

        for record in external_records:
            local_record = certificate_repository.get_by_external_order_id(
                session,
                str(record["order_id"]),
            )
            record["management_state"] = (
                local_record.management_state if local_record else "Discovered"
            )
            record["local_certificate_id"] = (
                local_record.id if local_record else None
            )

        return external_records

    def get_digicert_details(
        self,
        session: Session,
        order_id: str,
    ) -> dict[str, Any]:
        adapter = adapter_registry.get_ca_adapter("digicert")
        external_details = adapter.get_order_details(order_id)
        local_record = certificate_repository.get_by_external_order_id(
            session,
            order_id,
        )

        return {
            "external": external_details,
            "management_state": (
                local_record.management_state if local_record else "Discovered"
            ),
            "local_certificate_id": local_record.id if local_record else None,
        }

    def onboard(
        self,
        session: Session,
        order_id: str,
        request: OnboardRequest,
        actor: str,
    ) -> Certificate:
        existing = certificate_repository.get_by_external_order_id(
            session,
            order_id,
        )
        if existing and (existing.management_state != "Offboarded" or existing.status == "Revoked"):
            raise GovernanceError("Certificate is already registered or cannot be onboarded")

        adapter = adapter_registry.get_ca_adapter("digicert")
        details = adapter.get_order_details(order_id)
        external_certificate = details.get("certificate") or {}
        certificate_id = external_certificate.get("id") or details.get("certificate_id")
        valid_to = parse_certificate_expiry(
            external_certificate.get("valid_till") or details.get("valid_till")
        )
        if str(details.get("status", "")).lower() not in {"issued", "active_issued"} or not certificate_id:
            raise GovernanceError("DigiCert has not issued this certificate")

        if existing:
            # Old targets stay in history but remain disabled until explicitly selected.
            target = next(
                (item for item in existing.targets if
                 (item.host, item.site_name, item.hostname, item.port) ==
                 (request.host, request.site_name, request.hostname, request.port)),
                None,
            )
            if target is None:
                target = Target(
                    name=request.target_name, adapter_type="iis", host=request.host,
                    site_name=request.site_name, hostname=request.hostname,
                    port=request.port,
                )
                existing.targets.append(target)
            else:
                target.enabled = True
            existing.management_state = "Managed"
            if valid_to:
                existing.valid_to = valid_to
            if request.csr_pem:
                existing.csr_pem = request.csr_pem
            saved = certificate_repository.save(session, existing)
            audit_service.record(session, actor, "re-onboard", f"digicert-order:{order_id}", request.reason)
            return saved

        common_name = external_certificate.get("common_name") or details.get("common_name") or request.common_name
        dns_names = external_certificate.get("dns_names") or details.get("dns_names") or []

        certificate = Certificate(
            common_name=common_name,
            sans=",".join(dns_names),
            ca_type="digicert",
            external_order_id=order_id,
            external_certificate_id=(
                str(certificate_id) if certificate_id else None
            ),
            management_state="Managed",
            status="Active",
            valid_to=valid_to,
            csr_pem=request.csr_pem,
        )
        certificate.targets.append(
            Target(
                name=request.target_name,
                adapter_type="iis",
                host=request.host,
                site_name=request.site_name,
                hostname=request.hostname,
                port=request.port,
            )
        )

        saved_certificate = certificate_repository.save(session, certificate)
        audit_service.record(
            session=session,
            actor=actor,
            action="onboard",
            entity_reference=f"digicert-order:{order_id}",
            reason=request.reason,
        )
        return saved_certificate


external_inventory_service = ExternalInventoryService()
