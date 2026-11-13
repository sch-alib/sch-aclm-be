from sqlalchemy.orm import Session

from app.models.job import Job


class JobRepository:
    def list_all(self, session: Session) -> list[Job]:
        return session.query(Job).order_by(Job.id.desc()).all()

    def create(self, session: Session, job: Job) -> Job:
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


job_repository = JobRepository()
