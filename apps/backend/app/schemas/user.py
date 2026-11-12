import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import PartnerBrief
from app.schemas.versioning import ExpectedVersion

Password = Field(min_length=6, max_length=100)


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    password: str = Password
    role_codes: list[str] = []
    # Customer account: the shopping cart always orders for this customer (see User.partner_id)
    partner_id: uuid.UUID | None = None


class UserUpdate(ExpectedVersion):
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    is_active: bool = True
    role_codes: list[str] = []
    partner_id: uuid.UUID | None = None


class PasswordReset(BaseModel):
    password: str = Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    email: str | None = None
    is_active: bool
    roles: list[RoleBrief] = []
    partner: PartnerBrief | None = None
    row_version: int


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    module: str
    description: str


class RoleIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    permission_codes: list[str] = []


class RoleUpdate(ExpectedVersion):
    name: str = Field(min_length=1, max_length=100)
    permission_codes: list[str] = []


class RoleRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_system: bool
    permission_codes: list[str]
    user_count: int
    row_version: int
