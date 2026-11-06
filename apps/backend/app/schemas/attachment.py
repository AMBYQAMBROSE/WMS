import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentIn(BaseModel):
    # Base64 of the image file (JPEG, PNG or WebP; the PDA sends a downscaled JPEG). JSON rather than multipart:
    # simpler and more reliable from the PDA app, whose offline queue stores the photo until it can send it.
    content_base64: str = Field(min_length=1, max_length=6 * 1024 * 1024)
    caption: str | None = Field(default=None, max_length=200)


class AttachmentRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    caption: str | None
    created_at: datetime
    # Username of whoever took or uploaded it
    created_by: str | None
