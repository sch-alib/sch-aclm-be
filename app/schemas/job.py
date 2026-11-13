from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    certificate_id: int | None
    external_order_id: str | None
    job_type: str
    status: str
    actor: str
    message: str
    created_at: datetime
