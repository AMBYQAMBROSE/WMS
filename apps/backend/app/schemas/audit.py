import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AuditChange(BaseModel):
    field: str
    # Ids of referenced records are shown as their codes (item SKU, location code, ...); "***" for secrets
    old: Any = None
    new: Any = None


class AuditLogRead(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    user_id: uuid.UUID | None
    # Null with a null user_id: done by the system (background worker, scripts)
    username: str | None
    request_id: str | None
    action: Literal["CREATE", "UPDATE", "DELETE", "PRINT"]
    entity_type: str
    entity_id: uuid.UUID
    entity_label: str | None
    parent_id: uuid.UUID | None
    changes: list[AuditChange]
