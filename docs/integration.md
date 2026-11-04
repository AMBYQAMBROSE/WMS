# Integrations: Event Push Guide

For developers of the receiving system (ERP, TMS, or the customer's own system).

When a document changes status (for example, a goods receipt or shipment is posted), WMS sends the document as an HTTP POST to an address you provide. Your side only needs a receiving endpoint that verifies the signature, deduplicates as described here, and returns 2xx.

> Currently only WMS → your system pushes are provided. To write data into WMS (for example, sending purchase orders or sales orders), call the WMS REST API directly (`/api/v1/purchase-orders` etc.; API docs at `http://<WMS address>/docs`). Sign in with a dedicated system account to get a token. Dedicated connectors for SAP and other ERPs will be built when a project needs them.

## 1. Setup

A WMS administrator goes to **System → Integrations → New connector** and fills in:

| Field | Description |
|---|---|
| Endpoint URL | Your receiving address, `http://` or `https://`; the WMS server must be able to reach it |
| Subscribed events | Only the selected events are pushed |
| Extra headers | Authentication headers your side requires, e.g. `Authorization: Bearer xxx` |
| Timeout / max attempts | Default 10 seconds, 8 attempts |

After saving, the UI shows the signing secret (starting with `whsec_`) **only once**. The WMS administrator passes it to you to store. Use "Test push" to send a `test.ping` that checks connectivity and the signature.

## 2. Request format

```
POST <endpoint URL>
Content-Type: application/json; charset=utf-8
X-WMS-Event: grn.posted
X-WMS-Event-Id: 6f1c2a9e-...        Event ID; unchanged across retries of the same event, use it to deduplicate
X-WMS-Delivery: 0b7d4e1f-...        ID of this delivery attempt
X-WMS-Timestamp: 1793355796          Unix seconds
X-WMS-Signature: sha256=3a99...      Signature, see section 3
```

Body:

```json
{
  "event_id": "6f1c2a9e-...",
  "event_type": "grn.posted",
  "occurred_at": "2026-10-30T10:23:15Z",
  "tenant": "DEFAULT",
  "data": {
    "doc_type": "GRN",
    "doc_no": "GRN20261030-0005",
    "status": "POSTED",
    "partner": { "code": "S001", "name": "Example Supplier" },
    "ref_document": { "doc_type": "PO", "doc_no": "PO20261030-0003" },
    "reason_code": null,
    "expected_date": null,
    "posted_at": "2026-10-30T10:23:15Z",
    "remark": null,
    "lines": [
      {
        "line_no": 1,
        "sku": "A1001",
        "item_name": "Example item",
        "uom": "EA",
        "qty_planned": 7,
        "qty_actual": 7,
        "batch_no": "L20261001",
        "expiry_date": "2027-10-01",
        "from_location": null,
        "to_location": "IN-01"
      }
    ]
  }
}
```

- All times are UTC (ending in `Z`); quantities are numbers.
- Data is identified by business codes (document no., SKU, partner code, location code); WMS internal IDs are not exposed.
- **Quantity meaning by document**: `uom` is the line's unit.
  - **Purchase order lines**: `qty_planned` is the ordered quantity and `qty_actual` the cumulative received quantity, both in the order unit.
  - **Sales order lines**: `qty_actual` is the cumulative shipped quantity, **in the item's base unit**.
  - **Goods receipts, putaways, moves, adjustments, shipments, returns etc.**: `qty_actual` is the actual quantity on this document. Adjustment quantities are signed.
- The payload is snapshotted when the event is first dispatched and does not change across retries.

## 3. Verifying the signature

`X-WMS-Signature` = `sha256=` + HEX( HMAC-SHA256( secret, `timestamp` + `.` + raw request body ) )

Compute it over the **raw body bytes**; do not parse and re-serialize the JSON first. We also recommend rejecting requests whose timestamp is more than 5 minutes from the current time, to prevent replays.

Python:

```python
import hashlib, hmac, time

def verify(secret: str, headers: dict, body: bytes) -> bool:
    ts = headers["X-WMS-Timestamp"]
    if abs(time.time() - int(ts)) > 300:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers["X-WMS-Signature"])
```

C#:

```csharp
static bool Verify(string secret, string timestamp, byte[] body, string signature)
{
    using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
    var payload = Encoding.UTF8.GetBytes(timestamp + ".").Concat(body).ToArray();
    var expected = "sha256=" + Convert.ToHexString(hmac.ComputeHash(payload)).ToLowerInvariant();
    return CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(expected), Encoding.UTF8.GetBytes(signature));
}
```

Java:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
mac.update((timestamp + ".").getBytes(StandardCharsets.UTF_8));
String expected = "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
boolean ok = MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), signature.getBytes(StandardCharsets.UTF_8));
```

HTTP header names are case-insensitive; read them case-insensitively the way your framework does.

## 4. Responses, retries and deduplication

- Return **2xx** to acknowledge receipt. Any other status code, a timeout or a connection failure counts as a failure and is retried.
- Retry intervals: 30 seconds, 2 minutes, 10 minutes, 30 minutes, 1 hour, 2 hours, 4 hours, and so on. After the maximum number of attempts the delivery is marked failed; once the cause is fixed, a WMS administrator can "Resend" it in the UI.
- **You may receive the same event more than once** (e.g. you processed it but the response timed out). Deduplicate by `X-WMS-Event-Id`: if you have already processed the ID, just return 200.
- Ordering across events is not guaranteed. If you need ordering, use `occurred_at` and the document status.
- We recommend storing the payload, returning 2xx immediately, and processing asynchronously, so slow processing does not cause timeouts and retries.
- The first 2,000 characters of your response body are stored in the WMS push log to help both sides troubleshoot (you can return an error reason).

## 5. Events

| Event | Description |
|---|---|
| `purchase_order.confirmed` | Purchase order confirmed |
| `purchase_order.received` | Purchase order fully received |
| `purchase_order.closed` | Purchase order closed (the remainder will not be received) |
| `purchase_order.cancelled` | Purchase order cancelled |
| `grn.posted` | Goods receipt posted (stock increased) |
| `putaway.posted` | Putaway posted |
| `move.posted` | Move posted |
| `adjustment.posted` | Stock adjustment posted (with reason code) |
| `cycle_count.posted` | Cycle count posted (gains and losses recorded) |
| `sales_order.confirmed` | Sales order confirmed |
| `sales_order.shipped` | Sales order fully shipped |
| `sales_order.closed` | Sales order closed |
| `sales_order.cancelled` | Sales order cancelled |
| `pick.posted` | Pick list posted |
| `shipment.posted` | Shipment posted (goods have left the warehouse) |
| `return_in.posted` | Customer return posted |
| `return_out.posted` | Return to supplier posted |
| `repack.posted` | Repack posted |
| `test.ping` | Test push (triggered manually in the UI) |

Typical ERP subscriptions:
- `grn.posted`: purchase receipts
- `shipment.posted`: sales issues
- `adjustment.posted` + `cycle_count.posted`: stock differences
- `return_in.posted` / `return_out.posted`: returns

## 6. Troubleshooting

In **Integrations → Push log**, WMS administrators can find every push by document no. or status. For each push they can see the payload, and for every call the status code, duration, error and the response body.

The top of the page shows whether the push worker is running. Events created while the worker is stopped are not lost; they are sent once it recovers.
