from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import engine, numbering_engine
from app.core.errors import DomainError
from app.core.observability import RequestContextMiddleware, configure_logging, configure_telemetry

settings.check_production()
configure_logging()

app = FastAPI(
    title="WMS API",
    version=settings.app_version,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)


@app.exception_handler(DomainError)
def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

# SQL Server error numbers: 2627/2601 unique constraint violation, 547 foreign key violation
_UNIQUE_VIOLATION_CODES = ("2627", "2601")
_FK_VIOLATION_CODE = "547"


@app.exception_handler(IntegrityError)
def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    message = str(exc.orig)
    if any(f"({code})" in message for code in _UNIQUE_VIOLATION_CODES):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": "Duplicate code: a record with the same code already exists"}
        )
    if f"({_FK_VIOLATION_CODE})" in message:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "A referenced record does not exist"}
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Data validation failed"}
    )

# Large JSON (PDA master data, reports) is compressed; nginx also compresses in production, this covers direct access to the backend
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added last so it is the outermost middleware: the request id covers everything, including CORS and gzip
app.add_middleware(RequestContextMiddleware)

app.include_router(api_router, prefix="/api/v1")
app.state.otel_enabled = configure_telemetry(app, [engine, numbering_engine])
