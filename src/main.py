import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

from .db import init_db
from .api import router as api_router
from .settings import setup_logging

logger = setup_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("SERVER_ID", "SERVER-1") == "SERVER-1":
        init_db()
    logger.info("Application startup complete")

    yield
    logger.info("Application shutdown complete")


app = FastAPI(title="Cheminformatics API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    from time import time
    start = time()
    response = await call_next(request)
    duration = (time() - start) * 1000
    logging.getLogger("app").info(
        "%s %s -> %s (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


@app.get("/")
def root():
    return {"service": "cheminformatics", "status": "ok"}


app.include_router(api_router)
