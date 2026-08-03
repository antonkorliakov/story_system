from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.users.models import Role


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
