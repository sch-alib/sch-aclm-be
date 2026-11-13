from fastapi import APIRouter

from app.api.routes import auth, certificates, dashboard, external_digicert, jobs

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(certificates.router)
api_router.include_router(external_digicert.router)
api_router.include_router(jobs.router)
