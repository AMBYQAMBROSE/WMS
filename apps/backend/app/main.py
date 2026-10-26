from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import DomainError

app = FastAPI(title="WMS API", version="0.1.0")


@app.exception_handler(DomainError)
def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

# SQL Server 错误号：2627/2601 唯一约束冲突，547 外键约束冲突
_UNIQUE_VIOLATION_CODES = ("2627", "2601")
_FK_VIOLATION_CODE = "547"


@app.exception_handler(IntegrityError)
def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    message = str(exc.orig)
    if any(f"({code})" in message for code in _UNIQUE_VIOLATION_CODES):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": "编码重复，已存在相同记录"}
        )
    if f"({_FK_VIOLATION_CODE})" in message:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "引用的关联数据不存在"}
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "数据校验失败"}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
