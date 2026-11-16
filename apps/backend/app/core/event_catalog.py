"""Business events pushed to external systems. External systems (ERP/TMS/the customer's own) subscribe per event under "System > Integrations".

Events are produced automatically from document status changes (see the before_flush hook in app/models/integration.py),
so business code does not call anything; to add an event, register its (document type, new status) here.
"""

EVENT_TEST = "test.ping"

# (event code, document type, triggering status, name)
EVENTS: list[tuple[str, str, str, str]] = [
    ("purchase_order.confirmed", "PO", "CONFIRMED", "Purchase order confirmed"),
    ("purchase_order.received", "PO", "RECEIVED", "Purchase order fully received"),
    ("purchase_order.closed", "PO", "CLOSED", "Purchase order closed"),
    ("purchase_order.cancelled", "PO", "CANCELLED", "Purchase order cancelled"),
    ("grn.posted", "GRN", "POSTED", "Goods receipt posted"),
    ("putaway.posted", "PUTAWAY", "POSTED", "Putaway posted"),
    ("move.posted", "MOVE", "POSTED", "Move posted"),
    ("adjustment.posted", "ADJUST", "POSTED", "Stock adjustment posted"),
    ("cycle_count.posted", "COUNT", "POSTED", "Cycle count posted"),
    ("sales_order.confirmed", "SO", "CONFIRMED", "Sales order confirmed"),
    ("sales_order.shipped", "SO", "SHIPPED", "Sales order fully shipped"),
    ("sales_order.closed", "SO", "CLOSED", "Sales order closed"),
    ("sales_order.cancelled", "SO", "CANCELLED", "Sales order cancelled"),
    ("pick.posted", "PICK", "POSTED", "Pick list posted"),
    ("pick.reversed", "PICK", "REVERSED", "Picked goods returned to stock"),
    ("shipment.posted", "SHIP", "POSTED", "Shipment posted (goods left the warehouse)"),
    ("return_in.posted", "RETURN_IN", "POSTED", "Customer return posted"),
    ("return_out.posted", "RETURN_OUT", "POSTED", "Return to supplier posted"),
    ("repack.posted", "REPACK", "POSTED", "Repack posted"),
]

EVENT_BY_STATUS = {(doc_type, status): code for code, doc_type, status, _ in EVENTS}
EVENT_CODES = {code for code, _, _, _ in EVENTS}
EVENT_NAMES = {code: name for code, _, _, name in EVENTS} | {EVENT_TEST: "Test delivery"}
