from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_database_session
from app.models.user import User
from app.repositories.job_repository import job_repository
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    session: Session = Depends(get_database_session),
    _: User = Depends(get_current_user),
):
    return job_repository.list_all(session)
