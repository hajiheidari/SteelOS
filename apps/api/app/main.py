import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app.config import settings
from app.db import SCHEMA_REVISION, engine
from app.modules.assistant.router import router as assistant
from app.modules.identity import router as identity
from app.modules.inventory.router import router as inventory
from app.modules.resources import router as resources
from app.modules.sales.router import router as sales

logger = logging.getLogger("steelos")
logging.basicConfig(level=logging.INFO, format="%(message)s")
# Internal assistant reads include search terms; HTTP client INFO URLs must not log them.
logging.getLogger("httpx").setLevel(logging.WARNING)
# Structured events below replace raw URL access logs, which include search strings.
logging.getLogger("uvicorn.access").disabled = True
app = FastAPI(title="SteelOS API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(identity, prefix="/api/v1")
app.include_router(inventory, prefix="/api/v1")
app.include_router(resources, prefix="/api/v1")
app.include_router(sales, prefix="/api/v1")
app.include_router(assistant, prefix="/api/v1")


def error(request, status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error(request, exc.status_code, f"http_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo rejected values (passwords, tokens, PII) into responses or logs.
    details = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
    return error(request, 422, "validation_error", "Request validation failed", details)


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return error(
        request, 409, "data_conflict", "Duplicate record or referenced data prevents this operation"
    )


@app.exception_handler(SQLAlchemyError)
async def db_error(request, exc):
    logger.error(
        json.dumps(
            {
                "event": "database_error",
                "request_id": request.state.request_id,
                "type": type(exc).__name__,
            }
        )
    )
    return error(request, 503, "database_unavailable", "Database operation unavailable")


@app.middleware("http")
async def request_log(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "unexpected_error",
                    "type": type(exc).__name__,
                    "request_id": request.state.request_id,
                }
            )
        )
        response = error(request, 500, "internal_error", "Internal server error")
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info(
        json.dumps(
            {
                "event": "http",
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - start) * 1000),
                "request_id": request.state.request_id,
            }
        )
    )
    return response


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "steelos-api"}


@app.get("/api/v1/ready", tags=["system"])
def ready(request: Request):
    try:
        with engine().connect() as conn:
            version = conn.scalar(text("SELECT version_num FROM alembic_version"))
            if version != SCHEMA_REVISION:
                return error(request, 503, "migration_required", "Database migration required")
    except SQLAlchemyError:
        return error(request, 503, "not_ready", "Database unavailable or migrations missing")
    return {"status": "ready"}
