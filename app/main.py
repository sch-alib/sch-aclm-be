from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.database.base import Base
from app.database.seed import seed_database
from app.database.session import SessionFactory, engine
from app.services.issuance_monitor import issuance_monitor
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.jwt_secret or settings.jwt_secret == "change-this-in-production":
        raise RuntimeError("Set a unique JWT_SECRET before starting the backend")
    Base.metadata.create_all(bind=engine)
    with SessionFactory() as session:
        seed_database(session)
        issuance_monitor.schedule_existing(session)
    issuance_monitor.start()
    try:
        yield
    finally:
        issuance_monitor.stop()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok"}
