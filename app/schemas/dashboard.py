from pydantic import BaseModel


class DashboardResponse(BaseModel):
    total_certificates: int
    managed_certificates: int
    onboarding_certificates: int
    total_jobs: int
    failed_jobs: int
