from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditService:
    def record(
        self,
        session: Session,
        actor: str,
        action: str,
        entity_reference: str,
        reason: str,
    ) -> AuditEvent:
        event = AuditEvent(
            actor=actor,
            action=action,
            entity_reference=entity_reference,
            reason=reason,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


audit_service = AuditService()
