from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters.registry import adapter_registry
from app.core.config import settings
from app.core.exceptions import GovernanceError
from app.models.certificate import Certificate
from app.models.job import Job
from app.repositories.certificate_repository import certificate_repository
from app.repositories.job_repository import job_repository
from app.services.audit_service import audit_service


class OrchestrationService:
    def renew_and_deploy(
        self,
        session: Session,
        certificate: Certificate,
        actor: str,
    ) -> Job:
        if certificate.management_state != "Managed":
            raise GovernanceError("Certificate must be in Managed state")
        if session.query(Job).filter(
            Job.certificate_id == certificate.id, Job.job_type == "NewOrder"
        ).first():
            raise GovernanceError(
                "Renew and Deploy is unavailable for externally generated keys; "
                "deployment of new orders is not implemented"
            )

        if not settings.pfx_password:
            raise GovernanceError("PFX_PASSWORD must be configured before deployment")

        enabled_targets = [target for target in certificate.targets if target.enabled]
        if not enabled_targets:
            raise GovernanceError("At least one enabled installation target is required")

        ca_adapter = adapter_registry.get_ca_adapter(certificate.ca_type)
        result = ca_adapter.reissue_certificate(
            order_id=certificate.external_order_id or "",
            common_name=certificate.common_name,
            dns_names=[item for item in certificate.sans.split(",") if item],
            csr_pem=certificate.csr_pem,
            reason="Governed renewal and deployment",
        )

        certificate.external_certificate_id = result.get(
            "certificate_id",
            certificate.external_certificate_id,
        )

        artifact_path = Path(settings.artifacts_directory) / (
            f"certificate-{certificate.id}-{certificate.external_certificate_id}.pfx"
        )
        artifact_bytes = ca_adapter.download_certificate(
            certificate.external_certificate_id or ""
        )
        artifact_path.write_bytes(artifact_bytes)
        certificate.last_pfx_path = str(artifact_path)
        certificate.thumbprint = f"REISSUED-{certificate.external_certificate_id}"
        certificate_repository.save(session, certificate)

        deployment_messages: list[str] = []
        overall_success = True

        for target in enabled_targets:
            installation_adapter = adapter_registry.get_installation_adapter(
                target.adapter_type
            )
            deployment_result = installation_adapter.install(
                certificate=certificate,
                target=target,
                pfx_path=artifact_path,
                pfx_password=settings.pfx_password,
            )
            overall_success = overall_success and bool(
                deployment_result["success"]
            )
            deployment_messages.append(
                f"{target.name}: {deployment_result['message']}"
            )

        job = Job(
            certificate_id=certificate.id,
            external_order_id=certificate.external_order_id,
            job_type="RenewAndDeploy",
            status="Succeeded" if overall_success else "Failed",
            actor=actor,
            message=" | ".join(deployment_messages),
        )
        created_job = job_repository.create(session, job)

        audit_service.record(
            session=session,
            actor=actor,
            action="renew-and-deploy",
            entity_reference=f"certificate:{certificate.id}",
            reason="Governed renewal and deployment",
        )
        return created_job


orchestration_service = OrchestrationService()
