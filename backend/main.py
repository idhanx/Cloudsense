"""
CloudSense API — Application Factory
Production-grade FastAPI application with modular routing.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import init_db

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    logger.info("✅ Database initialized")
    logger.info(f"✅ Model path: {settings.MODEL_PATH}")
    yield


# ── App ──

app = FastAPI(
    title="CloudSense API",
    version="3.0.0",
    description="AI-powered Tropical Cloud Cluster detection system",
    lifespan=lifespan,
)

# ── CORS (restricted — no wildcard) ──

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "x-user-id"],
)


# ── Register Routers ──

from api.auth import router as auth_router
from api.upload import router as upload_router
from api.mosdac import router as mosdac_router
from api.analysis import router as analysis_router
from api.exports import router as exports_router

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(mosdac_router)
app.include_router(analysis_router)
app.include_router(exports_router)


# ── Static files ──

import os
if os.path.exists(settings.OUTPUT_DIR):
    app.mount("/static/output", StaticFiles(directory=settings.OUTPUT_DIR), name="output")


# ── Health (public) ──

@app.get("/health")
async def health():
    return {"status": "ok", "message": "CloudSense API is running", "version": "3.0.0"}


# ── Global error handler ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
