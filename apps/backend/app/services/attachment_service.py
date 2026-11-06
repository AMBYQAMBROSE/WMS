"""Photos on documents (app/models/attachment.py).

Who may do what follows the document: viewing needs the document's read permission, adding or removing needs the
permission of the people who work on it (create, or count/confirm for counts and picks).
"""

import base64
import binascii
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, ForbiddenError, NotFoundError
from app.models.attachment import DocumentAttachment
from app.models.document import DocumentHeader
from app.models.user import User

if TYPE_CHECKING:  # the API layer's type only; no runtime import from services into app.api
    from app.api.deps import CurrentUser

MAX_BYTES = 4 * 1024 * 1024
MAX_PER_DOCUMENT = 50

# Document type -> permission module, and the action that may add photos
_PERMISSIONS = {
    "PO": ("purchase_order", "create"),
    "GRN": ("grn", "create"),
    "PUTAWAY": ("putaway", "create"),
    "MOVE": ("move", "create"),
    "ADJUST": ("adjustment", "create"),
    "COUNT": ("cycle_count", "count"),
    "SO": ("sales_order", "create"),
    "PICK": ("pick", "confirm"),
    "SHIP": ("shipment", "create"),
    "RETURN_IN": ("return_in", "create"),
    "RETURN_OUT": ("return_out", "create"),
    "REPACK": ("repack", "create"),
}

# The file's own first bytes decide its type, never the name or the client's claim
_SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


def _sniff(data: bytes) -> tuple[str, str]:
    for prefix, content_type, extension in _SIGNATURES:
        if data.startswith(prefix):
            return content_type, extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise DomainError("Only photos are accepted (JPEG, PNG or WebP)")


class AttachmentService:
    def __init__(self, db: Session, user: "CurrentUser"):
        self.db = db
        self.user = user

    def _document(self, document_id: uuid.UUID, action: str) -> DocumentHeader:
        doc = self.db.get(DocumentHeader, document_id)
        if doc is None or doc.tenant_id != self.user.tenant_id or doc.is_deleted:
            raise NotFoundError("Document not found")
        module, write_action = _PERMISSIONS.get(doc.doc_type, (None, None))
        needed = f"{module}.{'read' if action == 'read' else write_action}" if module else None
        if needed is None or needed not in self.user.permissions:
            # Without read access the document does not exist for this user
            if action == "read" or needed is None:
                raise NotFoundError("Document not found")
            raise ForbiddenError(f"Missing permission: {needed}")
        return doc

    def list(self, document_id: uuid.UUID) -> list[dict]:
        self._document(document_id, "read")
        rows = self.db.execute(
            select(DocumentAttachment, User.username)
            .outerjoin(User, User.id == DocumentAttachment.created_by)
            .where(
                DocumentAttachment.tenant_id == self.user.tenant_id,
                DocumentAttachment.document_id == document_id,
                DocumentAttachment.is_deleted == false(),
            )
            .order_by(DocumentAttachment.created_at)
        ).all()
        return [self._read(a, username) for a, username in rows]

    def content(self, attachment_id: uuid.UUID) -> DocumentAttachment:
        attachment = self._get(attachment_id)
        self._document(attachment.document_id, "read")
        return attachment

    def add(self, document_id: uuid.UUID, content_base64: str, caption: str | None) -> dict:
        doc = self._document(document_id, "write")
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise DomainError("The photo is not valid base64") from exc
        if not data:
            raise DomainError("The photo is empty")
        if len(data) > MAX_BYTES:
            raise DomainError(f"The photo is larger than {MAX_BYTES // (1024 * 1024)} MB")
        content_type, extension = _sniff(data)
        existing = self.db.scalar(
            select(func.count()).where(
                DocumentAttachment.document_id == doc.id, DocumentAttachment.is_deleted == false()
            )
        )
        if existing >= MAX_PER_DOCUMENT:
            raise DomainError(f"A document can have at most {MAX_PER_DOCUMENT} photos")
        attachment = DocumentAttachment(
            tenant_id=self.user.tenant_id,
            document_id=doc.id,
            file_name=f"{doc.doc_no}-{uuid.uuid4().hex[:6]}.{extension}",
            content_type=content_type,
            size_bytes=len(data),
            caption=(caption or "").strip()[:200] or None,
            content=data,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.db.add(attachment)
        self.db.flush()
        return self._read(attachment, self.user.username)

    def delete(self, attachment_id: uuid.UUID) -> None:
        attachment = self._get(attachment_id)
        self._document(attachment.document_id, "write")
        attachment.is_deleted = True
        attachment.updated_by = self.user.id
        self.db.flush()

    def _get(self, attachment_id: uuid.UUID) -> DocumentAttachment:
        attachment = self.db.get(DocumentAttachment, attachment_id)
        if attachment is None or attachment.tenant_id != self.user.tenant_id or attachment.is_deleted:
            raise NotFoundError("Photo not found")
        return attachment

    @staticmethod
    def _read(a: DocumentAttachment, username: str | None) -> dict:
        return {
            "id": a.id,
            "document_id": a.document_id,
            "file_name": a.file_name,
            "content_type": a.content_type,
            "size_bytes": a.size_bytes,
            "caption": a.caption,
            "created_at": a.created_at,
            "created_by": username,
        }
