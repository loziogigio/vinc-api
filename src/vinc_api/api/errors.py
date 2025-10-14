from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_, exc: RequestValidationError):  # type: ignore[override]
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

