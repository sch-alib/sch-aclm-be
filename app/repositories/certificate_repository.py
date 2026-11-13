from sqlalchemy.orm import Session, selectinload

from app.models.certificate import Certificate


class CertificateRepository:
    def list_all(self, session: Session) -> list[Certificate]:
        return (
            session.query(Certificate)
            .options(selectinload(Certificate.targets))
            .order_by(Certificate.common_name)
            .all()
        )

    def get_by_id(self, session: Session, certificate_id: int) -> Certificate | None:
        return (
            session.query(Certificate)
            .options(selectinload(Certificate.targets))
            .filter(Certificate.id == certificate_id)
            .first()
        )

    def get_by_external_order_id(
        self,
        session: Session,
        order_id: str,
    ) -> Certificate | None:
        return (
            session.query(Certificate)
            .options(selectinload(Certificate.targets))
            .filter(Certificate.external_order_id == order_id)
            .first()
        )

    def save(self, session: Session, certificate: Certificate) -> Certificate:
        session.add(certificate)
        session.commit()
        session.refresh(certificate)
        return certificate


certificate_repository = CertificateRepository()
