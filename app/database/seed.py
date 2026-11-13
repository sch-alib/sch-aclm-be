"""Bootstrap one administrator on a new database; never seed known credentials."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


def seed_database(session: Session) -> None:
    if session.query(User).count() == 0:
        if len(settings.bootstrap_admin_password) < 12:
            raise RuntimeError(
                "Set BOOTSTRAP_ADMIN_PASSWORD (at least 12 characters) before starting "
                "with an empty database"
            )
        session.add(User(
            username="admin",
            full_name="Certificate Administrator",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="Admin",
        ))
        session.commit()
