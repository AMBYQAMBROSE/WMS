import uuid

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    display_name: str
    email: str | None = None
    password: str
    role_codes: list[str] = []


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    email: str | None = None
    is_active: bool
