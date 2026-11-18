"""Dashboard trend analysis, purchase costing, supplier payables, low-stock alarms and the stock-on-hand export.

Periods compare like with like: month to date and year to date against the same dates a year earlier, and full years
for the three-year trend. Days and months split by settings.business_timezone, like every report.

Costing: a goods receipt line carries the price of its purchase order line (DocumentLine.unit_price, per line unit), so the
value of a receipt is qty_actual * unit_price and its base quantity is the ledger row it posted. From that:
- average cost of an item = value of all priced receipts / their base quantity (stock valuation, value of losses)
- latest cost = the most recent priced receipt (recipe costing)
Receipts without a price are left out of costs; returns to supplier do not reduce purchases.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, distinct, false, func, literal_column, select, true
from sqlalchemy.orm import Session

from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader, DocumentLine
from app.models.item import Item, ItemUomConversion, Uom
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.services import stock_service as st
from app.services.document_common import DOC_GRN
from app.services.report_service import (
    _ITEM_COLUMNS,
    _cached,
    _item_brief,
    _num,
    _offset_minutes,
    load_by_ids,
    to_utc,
    today_local,
)

LOSS_TYPES = (st.MOVE_ADJUST_OUT, st.MOVE_COUNT_LOSS)
GAIN_TYPES = (st.MOVE_ADJUST_IN, st.MOVE_COUNT_GAIN)
# Rows per table on the dashboard (the biggest SKUs); the full picture is in the stock-on-hand export and the reports
TOP_ROWS = 20
TOP_PRICED = 12
TOP_SUPPLIERS = 5
# Trends read up to four years of ledger: recomputed at most this often per tenant (the dashboard does not need them by
# the second, unlike today's figures and the low-stock alarms, which follow REPORT_CACHE_SECONDS)
ANALYTICS_CACHE_SECONDS = 300
# Below the buffer is an alarm; up to this factor above it is a warning that the buffer is nearly used up
WARNING_FACTOR = Decimal("1.25")
ZERO = Decimal(0)
GRN_POSTED = "POSTED"
# Value of a receipt line: its quantity at its price (both in the line's unit)
PRICED = DocumentLine.unit_price.is_not(None)
VALUE = DocumentLine.qty_actual * DocumentLine.unit_price


def _year_ago(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 February
        return d.replace(year=d.year - 1, day=28)


@dataclass
class Periods:
    """Each period is [start, end) in local dates"""

    today: date
    mtd: tuple[date, date]
    mtd_ly: tuple[date, date]
    ytd: tuple[date, date]
    ytd_ly: tuple[date, date]
    last_year: tuple[date, date]
    three_years: tuple[date, date]  # the three full years before this one

    @classmethod
    def of(cls, today: date) -> "Periods":
        tomorrow = today + timedelta(days=1)
        year_ago = _year_ago(today) + timedelta(days=1)
        return cls(
            today=today,
            mtd=(today.replace(day=1), tomorrow),
            mtd_ly=(_year_ago(today.replace(day=1)), year_ago),
            ytd=(date(today.year, 1, 1), tomorrow),
            ytd_ly=(date(today.year - 1, 1, 1), year_ago),
            last_year=(date(today.year - 1, 1, 1), date(today.year, 1, 1)),
            three_years=(date(today.year - 3, 1, 1), date(today.year, 1, 1)),
        )

    @property
    def start(self) -> date:
        return self.three_years[0]

    def months(self) -> list[str]:
        """Every month from the start of the three-year window to this month, as YYYY-MM"""
        result, y, m = [], self.start.year, 1
        while (y, m) <= (self.today.year, self.today.month):
            result.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return result


def _month_key(column: str) -> literal_column:
    """yyyymm of a UTC datetime column in the business time zone; a literal so SELECT and GROUP BY match (see daily_flow)"""
    local = f"DATEADD(minute, {_offset_minutes():d}, {column})"
    return literal_column(f"(YEAR({local}) * 100 + MONTH({local}))")


def _month_text(key: int) -> str:
    return f"{key // 100:04d}-{key % 100:02d}"


def _in(column, period: tuple[date, date]):
    return and_(column >= to_utc(period[0]), column < to_utc(period[1]))


def _pct(now: Decimal | None, before: Decimal | None) -> Decimal | None:
    """Change in percent; none when there is nothing to compare with"""
    if now is None or not before:
        return None
    return round((now - before) / before * 100, 1)


@dataclass
class AnalyticsService:
    db: Session
    tenant_id: uuid.UUID
    can_view_costs: bool = False

    # ------------------------------------------------------------ building blocks

    def _receipts(self, *columns):
        """Ledger rows of posted receipts joined to their receipt line and document; by default with their value (null
        for a receipt line without a price) and the base quantity that has a price"""
        L, line, doc = StockLedger, DocumentLine, DocumentHeader
        if not columns:
            columns = (
                L.item_id,
                L.occurred_at,
                doc.partner_id,
                doc.id.label("document_id"),
                L.qty_change.label("base_qty"),
                case((PRICED, VALUE), else_=None).label("value"),
                case((PRICED, L.qty_change), else_=0).label("priced_qty"),
            )
        return (
            select(*columns)
            .select_from(L)
            .join(line, line.id == L.ref_document_line_id)
            .join(doc, doc.id == line.document_id)
            .where(L.tenant_id == self.tenant_id, L.movement_type == st.MOVE_RECEIVE)
        )

    def average_costs(self, item_ids=None) -> dict[uuid.UUID, Decimal]:
        """Weighted average purchase cost per base unit over all priced receipts"""
        r = self._receipts().subquery()
        stmt = select(r.c.item_id, func.sum(r.c.value), func.sum(r.c.priced_qty)).group_by(r.c.item_id).having(func.sum(r.c.priced_qty) > 0)
        if item_ids is not None:
            stmt = stmt.where(r.c.item_id.in_(list(item_ids)))
        return {item_id: Decimal(value) / Decimal(qty) for item_id, value, qty in self.db.execute(stmt) if value is not None}

    def latest_costs(self, item_ids) -> dict[uuid.UUID, tuple[Decimal, datetime]]:
        """Cost per base unit of each item's most recent priced receipt, with its time"""
        item_ids = list(item_ids)
        if not item_ids:
            return {}
        r = self._receipts().where(PRICED, StockLedger.item_id.in_(item_ids)).subquery()
        ranked = select(
            r.c.item_id, r.c.value, r.c.priced_qty, r.c.occurred_at,
            func.row_number().over(partition_by=r.c.item_id, order_by=r.c.occurred_at.desc()).label("n"),
        ).subquery()
        rows = self.db.execute(select(ranked.c.item_id, ranked.c.value, ranked.c.priced_qty, ranked.c.occurred_at).where(ranked.c.n == 1))
        return {item_id: (Decimal(value) / Decimal(qty), at) for item_id, value, qty, at in rows if qty}

    def _packings(self, item_ids) -> dict[uuid.UUID, dict]:
        """Largest packing unit per item (carton, bale, pallet...), for showing purchases in packing units"""
        item_ids = list(item_ids)
        if not item_ids:
            return {}
        C = ItemUomConversion
        rows = self.db.execute(
            select(C.item_id, C.factor, Uom.id, Uom.code, Uom.name)
            .join(Uom, Uom.id == C.from_uom_id)
            .join(Item, Item.id == C.item_id)
            .where(C.tenant_id == self.tenant_id, C.is_deleted == false(), C.to_uom_id == Item.base_uom_id, C.item_id.in_(item_ids))
        )
        best: dict[uuid.UUID, dict] = {}
        for item_id, factor, uom_id, code, name in rows:
            if item_id not in best or factor > best[item_id]["factor"]:
                best[item_id] = {"uom": {"id": uom_id, "code": code, "name": name}, "factor": factor}
        return best

    def _items(self, item_ids) -> dict[uuid.UUID, dict]:
        item_ids = list(item_ids)
        if not item_ids:
            return {}
        rows = self.db.execute(
            select(Item.id.label("item_id"), *_ITEM_COLUMNS).join(Uom, Uom.id == Item.base_uom_id).where(Item.id.in_(item_ids))
        ).mappings()
        return {r["item_id"]: _item_brief(r) for r in rows}

    # ------------------------------------------------------------ the dashboard's trend section

    def trends(self) -> dict:
        key = ("analytics", self.tenant_id, self.can_view_costs, today_local())
        return _cached(key, self._trends, ttl=ANALYTICS_CACHE_SECONDS)

    def _trends(self) -> dict:
        p = Periods.of(today_local())
        return {
            "date": p.today,
            "periods": {
                name: {"start": getattr(p, name)[0], "end": getattr(p, name)[1] - timedelta(days=1)}
                for name in ("mtd", "mtd_ly", "ytd", "ytd_ly", "last_year", "three_years")
            },
            "months": self._monthly(p),
            "totals": self._totals(p),
            "purchases": self._purchases_by_item(p),
            "losses": self._losses_by_item(p),
            "suppliers": self._suppliers(p),
        }

    def _monthly(self, p: Periods) -> list[dict]:
        """Purchases and losses per month over the three-year window and this year"""
        since = to_utc(p.start)
        L = StockLedger
        month = _month_key("stock_ledger.occurred_at")
        purchases = {
            m: (qty, value)
            for m, qty, value in self.db.execute(
                self._receipts(month, func.sum(L.qty_change), func.sum(case((PRICED, VALUE), else_=None)))
                .where(L.occurred_at >= since)
                .group_by(month)
            )
        }
        costs = self._average_cost_subquery()
        losses = {
            m: (qty, value)
            for m, qty, value in self.db.execute(
                select(month, -func.sum(L.qty_change), -func.sum(L.qty_change * costs.c.cost))
                .select_from(L)
                .outerjoin(costs, costs.c.item_id == L.item_id)
                .where(L.tenant_id == self.tenant_id, L.movement_type.in_(LOSS_TYPES), L.occurred_at >= since)
                .group_by(month)
            )
        }
        result = []
        for text in p.months():
            key = int(text.replace("-", ""))
            pq, pv = purchases.get(key, (None, None))
            lq, lv = losses.get(key, (None, None))
            result.append({
                "month": text,
                "purchased_qty": _num(pq),
                "purchased_value": _num(pv) if self.can_view_costs else None,
                "loss_qty": _num(lq),
                "loss_value": _num(lv) if self.can_view_costs else None,
            })
        return result

    def _totals(self, p: Periods) -> dict:
        """All SKUs together per comparison period (like-for-like dates, unlike the whole months of the monthly series)"""
        L = StockLedger
        since = to_utc(p.start)
        purchases = self.db.execute(
            self._receipts(*self._period_sums(L.occurred_at, L.qty_change, p),
                           *self._period_sums(L.occurred_at, case((PRICED, VALUE), else_=0), p, suffix="_value"))
            .where(L.occurred_at >= since)
        ).mappings().one()
        costs = self._average_cost_subquery()
        losses = self.db.execute(
            select(*self._period_sums(L.occurred_at, L.qty_change, p),
                   *self._period_sums(L.occurred_at, L.qty_change * costs.c.cost, p, suffix="_value"))
            .select_from(L)
            .outerjoin(costs, costs.c.item_id == L.item_id)
            .where(L.tenant_id == self.tenant_id, L.movement_type.in_(LOSS_TYPES), L.occurred_at >= since)
        ).mappings().one()

        def totals(r, sign: int) -> dict:
            values = {f"{k}_value": v for k, v in self._period_row(r, sign, suffix="_value").items()} if self.can_view_costs else {}
            return {**self._period_row(r, sign), **values}

        return {"purchases": totals(purchases, 1), "losses": totals(losses, -1)}

    def _average_cost_subquery(self):
        r = self._receipts().subquery()
        return (
            select(r.c.item_id, (func.sum(r.c.value) / func.nullif(func.sum(r.c.priced_qty), 0)).label("cost"))
            .group_by(r.c.item_id)
            .subquery()
        )

    def _period_sums(self, column, value, p: Periods, suffix: str = "") -> list:
        """Conditional sums of `value` for each comparison period, labeled by period name (+ suffix)"""
        return [func.sum(case((_in(column, getattr(p, name)), value), else_=0)).label(name + suffix)
                for name in ("mtd", "mtd_ly", "ytd", "ytd_ly", "last_year", "three_years")]

    def _period_row(self, r, sign=1, suffix: str = "") -> dict:
        def get(name):
            return _num(r[name + suffix]) * sign

        return {
            "mtd": get("mtd"),
            "mtd_ly": get("mtd_ly"),
            "ytd": get("ytd"),
            "ytd_ly": get("ytd_ly"),
            "last_year": get("last_year"),
            "avg_3y": round(get("three_years") / 3, 4),
        }

    def _purchases_by_item(self, p: Periods) -> dict:
        L = StockLedger
        priced_value = case((PRICED, VALUE), else_=0)
        rows = self.db.execute(
            self._receipts(
                L.item_id,
                *self._period_sums(L.occurred_at, L.qty_change, p),
                func.sum(case((_in(L.occurred_at, p.ytd), priced_value), else_=0)).label("ytd_value"),
                func.sum(case((_in(L.occurred_at, p.ytd_ly), priced_value), else_=0)).label("ytd_ly_value"),
                func.count().over().label("total"),
            )
            .where(L.occurred_at >= to_utc(p.start))
            .group_by(L.item_id)
            .order_by(func.sum(case((_in(L.occurred_at, p.ytd), L.qty_change), else_=0)).desc(), L.item_id)
            .limit(TOP_ROWS)
        ).mappings().all()
        return self._item_rows(rows, value_keys=("ytd_value", "ytd_ly_value"))

    def _losses_by_item(self, p: Periods) -> dict:
        L = StockLedger
        costs = self._average_cost_subquery()
        loss_value = L.qty_change * costs.c.cost
        rows = self.db.execute(
            select(
                L.item_id,
                *self._period_sums(L.occurred_at, L.qty_change, p),
                func.sum(case((_in(L.occurred_at, p.ytd), loss_value), else_=0)).label("ytd_value"),
                func.sum(case((_in(L.occurred_at, p.ytd_ly), loss_value), else_=0)).label("ytd_ly_value"),
                func.count().over().label("total"),
            )
            .select_from(L)
            .outerjoin(costs, costs.c.item_id == L.item_id)
            .where(L.tenant_id == self.tenant_id, L.movement_type.in_(LOSS_TYPES), L.occurred_at >= to_utc(p.start))
            .group_by(L.item_id)
            # Ledger quantities of losses are negative: the biggest loss sorts first
            .order_by(func.sum(case((_in(L.occurred_at, p.ytd), L.qty_change), else_=0)), L.item_id)
            .limit(TOP_ROWS)
        ).mappings().all()
        return self._item_rows(rows, value_keys=("ytd_value", "ytd_ly_value"), sign=-1)

    def _item_rows(self, rows, value_keys: tuple[str, ...], sign: int = 1) -> dict:
        ids = [r["item_id"] for r in rows]
        items, packings = self._items(ids), self._packings(ids)
        result = []
        for r in rows:
            row = {"item": items[r["item_id"]], "packing": packings.get(r["item_id"]), **self._period_row(r, sign)}
            for key in value_keys:
                row[key] = _num(r[key]) * sign if self.can_view_costs else None
            result.append(row)
        return {"total": rows[0]["total"] if rows else 0, "rows": result}

    # ------------------------------------------------------------ suppliers

    def _suppliers(self, p: Periods) -> dict:
        """Top suppliers this year (by purchase value with cost.view, otherwise by quantity) with their credit terms and payables"""
        r = self._receipts().where(StockLedger.occurred_at >= to_utc(p.ytd_ly[0])).subquery()
        in_ytd = _in(r.c.occurred_at, p.ytd)
        ytd_qty = func.sum(case((in_ytd, r.c.base_qty), else_=0))
        ytd_value = func.sum(case((in_ytd, r.c.value), else_=0))
        rank = ytd_value if self.can_view_costs else ytd_qty
        top = self.db.execute(
            select(
                r.c.partner_id,
                ytd_qty.label("ytd_qty"),
                ytd_value.label("ytd_value"),
                func.sum(case((_in(r.c.occurred_at, p.ytd_ly), r.c.value), else_=0)).label("ytd_ly_value"),
                func.count(distinct(case((in_ytd, r.c.document_id), else_=None))).label("receipts"),
            )
            .where(r.c.partner_id.is_not(None))
            .group_by(r.c.partner_id)
            .having(ytd_qty > 0)
            .order_by(rank.desc(), r.c.partner_id)
            .limit(TOP_SUPPLIERS)
        ).mappings().all()
        payables = self.payables_by_partner(p.today)
        partners = load_by_ids(self.db, BusinessPartner, [row["partner_id"] for row in top])
        total_ytd_value = self.db.scalar(select(func.sum(case((in_ytd, r.c.value), else_=0))))
        rows = []
        for row in top:
            partner = partners[row["partner_id"]]
            pay = payables.get(partner.id, {})
            rows.append({
                "partner": {"id": partner.id, "code": partner.code, "name": partner.name},
                "credit_terms_days": partner.credit_terms_days,
                "ytd_qty": _num(row["ytd_qty"]),
                "ytd_value": _num(row["ytd_value"]) if self.can_view_costs else None,
                "ytd_ly_value": _num(row["ytd_ly_value"]) if self.can_view_costs else None,
                "share_pct": (round(_num(row["ytd_value"]) / Decimal(total_ytd_value) * 100, 1)
                              if self.can_view_costs and total_ytd_value else None),
                "receipts": row["receipts"],
                **self._payable_fields(pay),
            })
        totals = {"outstanding": ZERO, "overdue": ZERO, "open_receipts": 0, "overdue_receipts": 0}
        for pay in payables.values():
            for k in totals:
                totals[k] += pay.get(k) or 0
        return {
            "rows": rows,
            "outstanding": totals["outstanding"] if self.can_view_costs else None,
            "overdue": totals["overdue"] if self.can_view_costs else None,
            "open_receipts": totals["open_receipts"],
            "overdue_receipts": totals["overdue_receipts"],
        }

    def _payable_fields(self, pay: dict) -> dict:
        return {
            "outstanding": pay.get("outstanding", ZERO) if self.can_view_costs else None,
            "overdue": pay.get("overdue", ZERO) if self.can_view_costs else None,
            "open_receipts": pay.get("open_receipts", 0),
            "overdue_receipts": pay.get("overdue_receipts", 0),
            "avg_days_to_settle": pay.get("avg_days_to_settle"),
            "on_time_pct": pay.get("on_time_pct"),
        }

    def _receipt_values(self):
        line = DocumentLine
        return (
            select(line.document_id, func.sum(line.qty_actual * line.unit_price).label("value"))
            .where(line.tenant_id == self.tenant_id, line.unit_price.is_not(None))
            .group_by(line.document_id)
            .subquery()
        )

    def payables_by_partner(self, today: date) -> dict[uuid.UUID, dict]:
        """Per supplier: open and overdue amounts of posted receipts, and over the last 12 months how many days settling
        took on average and how often it was on time. Receipts posted before payables existed (no due date) are left out."""
        H, values = DocumentHeader, self._receipt_values()
        open_ = H.settled_on.is_(None)
        overdue = and_(open_, H.payment_due_date < today)
        recent = H.settled_on >= today - timedelta(days=365)
        posted_day = literal_column(f"CAST(DATEADD(minute, {_offset_minutes():d}, document_header.posted_at) AS date)")
        days = func.datediff(literal_column("day"), posted_day, H.settled_on)
        rows = self.db.execute(
            select(
                H.partner_id,
                func.sum(case((open_, values.c.value), else_=0)),
                func.sum(case((overdue, values.c.value), else_=0)),
                func.sum(case((open_, 1), else_=0)),
                func.sum(case((overdue, 1), else_=0)),
                func.avg(case((recent, days * 1.0), else_=None)),
                func.sum(case((and_(recent, H.settled_on <= H.payment_due_date), 1), else_=0)),
                func.sum(case((recent, 1), else_=0)),
            )
            .select_from(H)
            .outerjoin(values, values.c.document_id == H.id)
            .where(
                H.tenant_id == self.tenant_id, H.doc_type == DOC_GRN, H.status == GRN_POSTED,
                H.payment_due_date.is_not(None), H.partner_id.is_not(None),
            )
            .group_by(H.partner_id)
        )
        return {
            partner_id: {
                "outstanding": _num(outstanding),
                "overdue": _num(overdue_value),
                "open_receipts": open_count or 0,
                "overdue_receipts": overdue_count or 0,
                "avg_days_to_settle": round(Decimal(avg_days), 1) if avg_days is not None else None,
                "on_time_pct": round(Decimal(on_time) / settled * 100, 1) if settled else None,
            }
            for partner_id, outstanding, overdue_value, open_count, overdue_count, avg_days, on_time, settled in rows
        }

    # ------------------------------------------------------------ pricing trend (cost.view only)

    def pricing(self, item_id: uuid.UUID | None = None) -> dict:
        """Average purchase cost per base unit and month for the items with the biggest spend in the last 12 months
        (plus `item_id` when given), over the three-year window"""
        p = Periods.of(today_local())
        since = to_utc(p.start)
        L = StockLedger
        last_12 = to_utc(p.today.replace(day=1) - timedelta(days=365))
        r = self._receipts().where(PRICED, L.occurred_at >= last_12).subquery()
        top = list(self.db.scalars(
            select(r.c.item_id).group_by(r.c.item_id).order_by(func.sum(r.c.value).desc(), r.c.item_id).limit(TOP_PRICED)
        ))
        if item_id and item_id not in top:
            top.append(item_id)
        if not top:
            return {"months": p.months(), "rows": []}
        month = _month_key("stock_ledger.occurred_at")
        series: dict[uuid.UUID, dict[int, tuple[Decimal, Decimal]]] = {}
        for item, m, v, q in self.db.execute(
            self._receipts(L.item_id, month, func.sum(VALUE), func.sum(L.qty_change))
            .where(PRICED, L.occurred_at >= since, L.item_id.in_(top))
            .group_by(L.item_id, month)
        ):
            series.setdefault(item, {})[m] = (Decimal(v), Decimal(q))
        items, latest = self._items(top), self.latest_costs(top)
        months = p.months()
        twelve_ago = months[-13] if len(months) > 12 else months[0]
        rows = []
        for item in top:
            by_month = series.get(item, {})
            points = [
                {"month": text, "avg_cost": (by_month[k][0] / by_month[k][1]) if (k := int(text.replace("-", ""))) in by_month and by_month[k][1] else None,
                 "qty": by_month[k][1] if k in by_month else ZERO}
                for text in months
            ]
            known = [pt for pt in points if pt["avg_cost"] is not None]
            before = [pt for pt in known if pt["month"] <= twelve_ago]
            ytd = [by_month[k] for k in by_month if k // 100 == p.today.year]
            ytd_cost = sum(v for v, _ in ytd) / sum(q for _, q in ytd) if ytd and sum(q for _, q in ytd) else None
            latest_cost = latest.get(item, (None, None))[0]
            year_ago = before[-1]["avg_cost"] if before else None
            rows.append({
                "item": items[item],
                "latest_cost": latest_cost,
                "latest_at": latest.get(item, (None, None))[1],
                "avg_cost_ytd": ytd_cost,
                "cost_year_ago": year_ago,
                "change_pct": _pct(latest_cost, year_ago),
                "min_cost": min((pt["avg_cost"] for pt in known), default=None),
                "max_cost": max((pt["avg_cost"] for pt in known), default=None),
                "points": points,
            })
        return {"months": months, "rows": rows}

    # ------------------------------------------------------------ low-stock alarms (live, part of the dashboard)

    def stock_alerts(self, limit: int = 50) -> dict:
        """Items whose available stock (on hand - allocated, all locations) is below their minimum stock (alarm) or within
        WARNING_FACTOR of it (warning). Most urgent first: lowest share of the buffer still available."""
        B = StockBalance
        stock = (
            select(B.item_id, func.sum(B.qty_on_hand).label("on_hand"), func.sum(B.qty_on_hand - B.qty_allocated).label("available"))
            .where(B.tenant_id == self.tenant_id)
            .group_by(B.item_id)
            .subquery()
        )
        available = func.coalesce(stock.c.available, 0)
        level = case((available <= 0, "out"), (available < Item.min_stock_qty, "below"), else_="low")
        rows = self.db.execute(
            select(
                Item.id.label("item_id"), *_ITEM_COLUMNS, Item.min_stock_qty, available.label("available"),
                func.coalesce(stock.c.on_hand, 0).label("on_hand"), level.label("level"),
            )
            .join(Uom, Uom.id == Item.base_uom_id)
            .outerjoin(stock, stock.c.item_id == Item.id)
            .where(
                Item.tenant_id == self.tenant_id, Item.is_active == true(), Item.is_deleted == false(),
                Item.min_stock_qty > 0, available < Item.min_stock_qty * WARNING_FACTOR,
            )
            .order_by(available / Item.min_stock_qty, Item.sku_code)
        ).mappings().all()
        counts = {"out": 0, "below": 0, "low": 0}
        for r in rows:
            counts[r["level"]] += 1
        return {
            "alarm_count": counts["out"] + counts["below"],
            "out_count": counts["out"],
            "warning_count": counts["low"],
            "rows": [
                {
                    "item": _item_brief(r),
                    "level": r["level"],
                    "min_stock_qty": _num(r["min_stock_qty"]),
                    "available": _num(r["available"]),
                    "on_hand": _num(r["on_hand"]),
                    "shortfall": max(_num(r["min_stock_qty"]) - _num(r["available"]), ZERO),
                }
                for r in rows[:limit]
            ],
        }

    # ------------------------------------------------------------ real-time stock on hand (export)

    def stock_on_hand(self, by: str = "location") -> list[dict]:
        """Every non-zero balance now: by location and batch, or one row per item. With cost.view, valued at average cost."""
        B = StockBalance
        nonzero = and_(B.tenant_id == self.tenant_id, (B.qty_on_hand != 0) | (B.qty_allocated != 0))
        if by == "item":
            rows = self.db.execute(
                select(
                    B.item_id, func.sum(B.qty_on_hand).label("on_hand"), func.sum(B.qty_allocated).label("allocated"),
                    func.count(distinct(B.location_id)).label("locations"),
                    Item.category.label("category"), Item.min_stock_qty.label("min_stock_qty"), *_ITEM_COLUMNS,
                )
                .join(Item, Item.id == B.item_id)
                .join(Uom, Uom.id == Item.base_uom_id)
                .where(nonzero)
                .group_by(B.item_id, Item.sku_code, Item.name, Item.is_batch_managed, Item.is_expiry_managed,
                          Item.category, Item.min_stock_qty, Uom.id, Uom.code, Uom.name)
                .order_by(Item.sku_code)
            ).mappings().all()
        else:
            rows = self.db.execute(
                select(
                    B.item_id, B.qty_on_hand.label("on_hand"), B.qty_allocated.label("allocated"), B.batch_no, B.expiry_date,
                    Location.code.label("location_code"), Location.location_type.label("location_type"),
                    Item.category.label("category"), Item.min_stock_qty.label("min_stock_qty"), *_ITEM_COLUMNS,
                )
                .join(Item, Item.id == B.item_id)
                .join(Uom, Uom.id == Item.base_uom_id)
                .join(Location, Location.id == B.location_id)
                .where(nonzero)
                .order_by(Item.sku_code, Location.code, B.batch_no, B.expiry_date)
            ).mappings().all()
        costs = self.average_costs() if self.can_view_costs else {}
        result = []
        for r in rows:
            on_hand, allocated = _num(r["on_hand"]), _num(r["allocated"])
            cost = costs.get(r["item_id"])
            result.append({
                **r,
                "on_hand": on_hand,
                "allocated": allocated,
                "available": on_hand - allocated,
                "avg_cost": round(cost, 6) if cost is not None else None,
                "value": round(on_hand * cost, 2) if cost is not None else None,
            })
        return result
