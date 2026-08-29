"""FastAPI application factory.

Wires middleware (CORS, request-id + logging context), structured exception
handling (every error → the ``{"error": {...}}`` envelope), and startup
(create tables + seed DEMO data). Import-time side effects are avoided: the app
is built by :func:`create_app`.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import bind_context, clear_context, configure_logging, get_logger

logger = get_logger("legalmet.api")

_REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging(settings)

    # Create tables (dev/demo convenience; production uses Alembic migrations).
    from app.db.init_db import create_all
    from app.db.session import SessionLocal, engine

    create_all(engine)

    if settings.seed_demo_data:
        from app.db.seed import seed_demo_data

        db = SessionLocal()
        try:
            seed_demo_data(db, settings)
        finally:
            db.close()

    # Prompt 5: research-grade regulatory intelligence seed (idempotent). Runs
    # independently of the DEMO flag — it is clearly-labelled UNVERIFIED data,
    # never fictional. Failing loudly is deliberate: structurally invalid
    # regulatory data must never land silently.
    if settings.seed_regulatory_data:
        from app.db.regulatory_seed import seed_regulatory_data

        db = SessionLocal()
        try:
            seed_regulatory_data(db)
        finally:
            db.close()

    # Prompt 6: deterministic compliance rules bound to the real regulatory
    # requirements (idempotent — natural key requirement_id + rule_code). Runs
    # only against non-demo requirements; nothing is invented here.
    if settings.seed_compliance_rules:
        from app.services.compliance.seed_rules import seed_compliance_rules

        db = SessionLocal()
        try:
            seed_compliance_rules(db)
        finally:
            db.close()

    if settings.using_insecure_secret and settings.is_production:
        logger.warning("insecure_secret_in_production")

    logger.info(
        "app_startup",
        app=settings.app_name,
        environment=settings.environment,
        database="sqlite" if settings.is_sqlite else "external",
        seeded=settings.seed_demo_data,
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description=(
            "Compliance-checking system for packaged commodities (SIH26034). "
            "All regulatory content in this build is DEMO DATA — NOT LEGAL ADVICE."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[_REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        clear_context()
        bind_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_context()
        response.headers[_REQUEST_ID_HEADER] = request_id
        return response

    _register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "service": settings.app_name,
            "problemStatement": "SIH26034",
            "docs": "/docs",
            "apiPrefix": settings.api_prefix,
            "notice": "DEMO DATA — NOT LEGAL ADVICE",
        }

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        if exc.status_code >= 500:
            logger.error("app_error", code=exc.code.value, message=exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload(request_id))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        details = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        payload = {
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Request validation failed.",
                "details": details,
                "requestId": request_id,
            }
        }
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Never leak internals; log server-side, return a stable envelope.
        logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        payload = {
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected error occurred.",
                "requestId": request_id,
            }
        }
        return JSONResponse(status_code=500, content=payload)


# ASGI entrypoint: `uvicorn app.main:app`
app = create_app()
