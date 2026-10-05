from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.security import decode_token

# Routes that do not require a token.
_AUTH_ALLOWLIST = {("/health", "GET"), ("/auth/login", "POST")}


def create_app() -> FastAPI:
    from app.auth import router as auth_router, users_router
    from app.agents import router as agents_router

    app = FastAPI(title="Seyarkai Backend")

    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def require_auth(request: Request, call_next):
        # CORS preflight — let the CORSMiddleware handle it
        if request.method == "OPTIONS":
            return await call_next(request)
        if (request.url.path, request.method) in _AUTH_ALLOWLIST:
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "not authenticated"})
        try:
            decode_token(auth_header[7:])
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "not authenticated"})
        return await call_next(request)

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(users_router, tags=["users"])
    app.include_router(agents_router, tags=["agents"])

    @app.get("/health")
    async def health():
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            return JSONResponse(status_code=503, content={"detail": "database unavailable"})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        import json as _json
        errors = exc.errors()
        # Pydantic v2 may embed raw Exception objects in ctx — make them serializable
        safe = _json.loads(_json.dumps(errors, default=str))
        return JSONResponse(status_code=422, content={"detail": safe})

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    return app


app = create_app()
