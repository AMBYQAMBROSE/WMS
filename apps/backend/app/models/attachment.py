"""Photos attached to documents: damaged goods on receipt, what was found at a count, a loaded truck.

Stored in the database rather than on disk, so the existing backup, restore and upgrade rollback (docs/deployment.md)
cover them without a second place to back up. Photos are downscaled on the PDA (a few hundred KB), and the content is a
deferred column, so listing a document's photos never loads the images.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, Unicode
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.models.base import Base, TenantScopedMixin


class DocumentAttachment(Base, TenantScopedMixin):
    __tablename__ = "document_attachment"
    __table_args__ = (Index("ix_document_attachment_document", "tenant_id", "document_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_header.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    content_type: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    content: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
