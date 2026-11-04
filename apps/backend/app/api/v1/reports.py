import csv
import io
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.report import Dashboard, ExpiryPage, OccupancyArea, PartnerLedgerPage, PickerKpiPage, TurnoverPage
from app.services.report_service import ReportService, today_local

router = APIRouter(prefix="/reports", tags=["reports"])

# Maximum rows shown on screen; full data via format=csv (turnover/ledger in a large warehouse can have tens of thousands of rows)
DEFAULT_LIMIT = 1000
Fmt = Literal["json", "csv"]


def _range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Default to the last 30 days (including today) when no dates are given"""
    date_to = date_to or today_local()
    return date_from or date_to - timedelta(days=29), date_to


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        # No scientific notation or trailing zeros: 1E+1 -> 10, 10.5000 -> 10.5
        text = format(value.normalize(), "f")
        return text
    return str(value)


def _csv(filename: str, columns: list[tuple[str, Callable[[dict], object]]], rows: list[dict]) -> Response:
    """UTF-8 CSV with BOM so Excel opens it with the right encoding"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([title for title, _ in columns])
    for row in rows:
        writer.writerow([_cell(get(row)) for _, get in columns])
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _page(rows: list[dict], limit: int) -> dict:
    return {"total": len(rows), "rows": rows[:limit]}


@router.get("/dashboard", response_model=Dashboard)
def dashboard(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    return ReportService(db, user.tenant_id).dashboard()


@router.get("/occupancy", response_model=list[OccupancyArea])
def occupancy(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    return ReportService(db, user.tenant_id).occupancy()


@router.get("/turnover", response_model=TurnoverPage)
def turnover(
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=5000),
    format: Fmt = "json",
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    start, end = _range(date_from, date_to)
    svc = ReportService(db, user.tenant_id)
    if format == "csv":
        _, rows = svc.turnover(start, end, keyword, None)
        return _csv(f"stock-turnover_{start}_{end}.csv", [
            ("SKU", lambda r: r["item"]["sku_code"]), ("Item", lambda r: r["item"]["name"]),
            ("Unit", lambda r: r["item"]["base_uom"]["code"]), ("Opening", lambda r: r["opening"]),
            ("Received", lambda r: r["received"]), ("Shipped", lambda r: r["shipped"]),
            ("Adjust/count/repack", lambda r: r["other"]), ("Closing", lambda r: r["closing"]),
            ("Average stock", lambda r: r["average"]), ("Turnover", lambda r: r["turnover"]),
            ("Days on hand", lambda r: r["days_on_hand"]),
        ], rows)
    total, rows = svc.turnover(start, end, keyword, limit)
    return {"total": total, "rows": rows}


@router.get("/picker-kpi", response_model=PickerKpiPage)
def picker_kpi(
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=5000),
    format: Fmt = "json",
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    start, end = _range(date_from, date_to)
    rows = ReportService(db, user.tenant_id).picker_kpi(start, end)
    if format == "csv":
        return _csv(f"picker-performance_{start}_{end}.csv", [
            ("Username", lambda r: r["username"]), ("Name", lambda r: r["display_name"]),
            ("Pick lists", lambda r: r["picks"]), ("Lines", lambda r: r["lines"]),
            ("Quantity", lambda r: r["qty"]), ("Short lines", lambda r: r["short_lines"]),
            ("Fill rate %", lambda r: r["fill_rate"]),
            ("First confirm (UTC)", lambda r: r["first_at"].isoformat(timespec="seconds")),
            ("Last confirm (UTC)", lambda r: r["last_at"].isoformat(timespec="seconds")),
        ], rows)
    return _page(rows, limit)


@router.get("/expiry", response_model=ExpiryPage)
def expiry(
    within_days: int = Query(default=30, ge=0, le=3650),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=5000),
    format: Fmt = "json",
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    rows = ReportService(db, user.tenant_id).expiry(within_days)
    if format == "csv":
        return _csv(f"expiring-stock_{within_days}-days.csv", [
            ("SKU", lambda r: r["item"].sku_code), ("Item", lambda r: r["item"].name),
            ("Location", lambda r: r["location_code"]), ("Batch", lambda r: r["batch_no"]),
            ("Expiry date", lambda r: r["expiry_date"]), ("Days left", lambda r: r["days_left"]),
            ("On hand", lambda r: r["qty_on_hand"]), ("Allocated", lambda r: r["qty_allocated"]),
            ("Unit", lambda r: r["item"].base_uom.code),
        ], rows)
    return _page(rows, limit)


@router.get("/partner-ledger", response_model=PartnerLedgerPage)
def partner_ledger(
    date_from: date | None = None,
    date_to: date | None = None,
    partner_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=5000),
    format: Fmt = "json",
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("report.read")),
):
    start, end = _range(date_from, date_to)
    svc = ReportService(db, user.tenant_id)
    if format == "csv":
        _, rows = svc.partner_ledger(start, end, partner_id, None)
        return _csv(f"partner-ledger_{start}_{end}.csv", [
            ("Partner code", lambda r: r["partner"]["code"]), ("Partner", lambda r: r["partner"]["name"]),
            ("SKU", lambda r: r["item"]["sku_code"]), ("Item", lambda r: r["item"]["name"]),
            ("Unit", lambda r: r["item"]["base_uom"]["code"]), ("Received", lambda r: r["received"]),
            ("Returned to supplier", lambda r: r["returned_to_supplier"]), ("Shipped", lambda r: r["shipped"]),
            ("Customer returns", lambda r: r["returned_by_customer"]), ("Documents", lambda r: r["documents"]),
        ], rows)
    total, rows = svc.partner_ledger(start, end, partner_id, limit)
    return {"total": total, "rows": rows}
