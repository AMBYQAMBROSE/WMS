from datetime import date, timedelta

from fastapi import Query

from app.services.report_service import to_utc


def document_filters(
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None, max_length=100, description="Part of the document or source document number, partner code/name or remark"),
    created_from: date | None = Query(default=None, description="First day (business time zone), inclusive"),
    created_to: date | None = Query(default=None, description="Last day (business time zone), inclusive"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Filters shared by every document list endpoint, passed on to list_documents"""
    return {
        "status": status_filter,
        "keyword": keyword,
        "created_from": to_utc(created_from) if created_from else None,
        "created_to": to_utc(created_to + timedelta(days=1)) if created_to else None,
        "skip": skip,
        "limit": limit,
    }
