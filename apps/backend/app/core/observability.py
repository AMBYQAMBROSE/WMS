"""Logging, request tracking and optional OpenTelemetry export.

- Every request gets a request id (taken from X-Request-ID when a proxy sends one), returned in the X-Request-ID
  response header and written on every log line and audit row of that request, so a user's error report leads straight
  to the logs.
- LOG_FORMAT=json writes one JSON object per line for log collectors (production); text is for development.
- Requests slower than SLOW_REQUEST_MS are logged as warnings.
- OpenTelemetry is off unless OTEL_EXPORTER_OTLP_ENDPOINT is set: then traces (HTTP + SQL) and metrics are pushed over
  OTLP/HTTP to whatever collector the customer runs (Grafana/Tempo, Jaeger, Elastic, Datadog, ...). Nothing is bundled.
"""

import json
import logging
import sys
import time
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.request_context import RequestContext, current_context, end_request, start_request

logger = logging.getLogger("wms.request")


class _ContextFilter(logging.Filter):
    """Adds the current request's id and user to every record"""

    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        record.request_id = context.request_id if context.path else None
        record.user = context.username
        return True


class JsonFormatter(logging.Formatter):
    _STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "request_id", "user"}

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if getattr(record, "request_id", None):
            entry["request_id"] = record.request_id
        if getattr(record, "user", None):
            entry["user"] = record.user
        # Fields passed with logger.info(..., extra={...})
        entry.update({k: v for k, v in vars(record).items() if k not in self._STANDARD and not k.startswith("_")})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        request_id = getattr(record, "request_id", None)
        return f"{line} [{request_id}]" if request_id else line


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(_TextFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    # uvicorn's own access log duplicates ours (which has the user, request id and duration)
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


class RequestContextMiddleware:
    """Pure ASGI middleware (not BaseHTTPMiddleware): the context var it sets is visible to the endpoint and dependencies"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")[:32]
        context = RequestContext(method=scope["method"], path=scope["path"])
        if incoming:
            context.request_id = incoming
        token = start_request(context)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", context.request_id.encode("latin-1")))
            await send(message)

        response_started = False

        async def send_tracked(message: Message) -> None:
            nonlocal response_started
            response_started = response_started or message["type"] == "http.response.start"
            await send_with_id(message)

        try:
            await self.app(scope, receive, send_tracked)
        except Exception:
            # Logged here, while the request id is still known; the client gets the id to quote in a bug report
            logger.exception("Unhandled error in %s %s", scope["method"], scope["path"])
            if response_started:
                raise
            status = 500
            body = json.dumps({"detail": f"Internal server error (request id {context.request_id})"}).encode()
            await send_with_id({
                "type": "http.response.start", "status": 500,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000)
            if not scope["path"].startswith("/api/v1/health"):
                # The live event stream is long by design: not a slow request
                slow = duration_ms >= settings.slow_request_ms and not scope["path"].startswith("/api/v1/events")
                level = logging.ERROR if status >= 500 else logging.WARNING if slow else logging.INFO
                logger.log(
                    level,
                    "%s %s %s %dms%s", scope["method"], scope["path"], status, duration_ms, " SLOW" if slow else "",
                    extra={"status": status, "duration_ms": duration_ms, "method": scope["method"], "path": scope["path"]},
                )
            end_request(token)


def configure_telemetry(app, engines) -> bool:
    """Returns whether OpenTelemetry export was switched on"""
    if not settings.otel_exporter_otlp_endpoint:
        return False

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    base = settings.otel_exporter_otlp_endpoint.rstrip("/")
    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": settings.app_version,
        "deployment.environment": settings.app_env,
    })
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"))],
    ))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/v1/health")
    for engine in engines:
        # The instrumentation declares sqlalchemy < 2.1 but only hooks engine events, which 2.1 keeps (verified)
        SQLAlchemyInstrumentor().instrument(engine=engine, skip_dep_check=True)
    logging.getLogger(__name__).info("OpenTelemetry export to %s", base)
    return True
