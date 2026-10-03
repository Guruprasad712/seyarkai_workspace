from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import AsyncSessionLocal


def create_app() -> FastAPI:
    app = FastAPI(title="Seyarkai Backend")

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
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    return app


app = create_app()
