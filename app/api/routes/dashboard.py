from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_database_session
from app.models.certificate import Certificate
from app.models.job import Job
from app.models.user import User
from app.schemas.dashboard import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
) -> DashboardResponse:
    return DashboardResponse(
        total_certificates=session.query(Certificate).count(),
        managed_certificates=(
            session.query(Certificate)
            .filter(Certificate.management_state == "Managed")
            .count()
        ),
        onboarding_certificates=(
            session.query(Certificate)
            .filter(Certificate.management_state == "Onboarding")
            .count()
        ),
        total_jobs=session.query(Job).count(),
        failed_jobs=session.query(Job).filter(Job.status == "Failed").count(),
    )
