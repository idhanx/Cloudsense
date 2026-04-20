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
import sqlite3

from core.config import settings
from core.database import init_db

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Global state for model (loaded once at startup) ──
_inference_pipeline = None

# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize app resources: config, database, and ML model."""
    global _inference_pipeline
    
    # Validate and initialize configuration
    settings.validate()
    init_db()
    logger.info("✅ Database initialized")
    
    # Load model once at startup (not on first request)
    try:
        from inference_engine import InferencePipeline
        logger.info(f"📦 Loading model from {settings.MODEL_PATH}...")
        _inference_pipeline = InferencePipeline(model_path=settings.MODEL_PATH)
        logger.info("✅ ML Model loaded successfully")
        app.state.inference_pipeline = _inference_pipeline
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}", exc_info=True)
        # Don't fail startup, but flag degraded state
        app.state.model_load_error = str(e)
    
    logger.info(f"✅ Model path: {settings.MODEL_PATH}")
    yield
    
    # Cleanup (if needed)
    logger.info("🛑 Shutting down CloudSense API")


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
    """Comprehensive health check including database and model."""
    health_status = {
        "status": "ok",
        "version": "3.0.0",
        "components": {}
    }
    
    # Check database connectivity
    try:
        if settings.DATABASE_URL.startswith("postgresql"):
            import psycopg2
            conn = psycopg2.connect(settings.DATABASE_URL)
            conn.close()
        else:
            # SQLite
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            conn.close()
        health_status["components"]["database"] = "ok"
    except Exception as e:
        logger.error(f"Health check: database error: {e}")
        health_status["status"] = "degraded"
        health_status["components"]["database"] = f"error: {str(e)[:50]}"
    
    # Check if model is loaded
    model_loaded = getattr(app.state, "inference_pipeline", None) is not None
    if model_loaded:
        health_status["components"]["model"] = "ok"
    else:
        health_status["status"] = "degraded"
        model_error = getattr(app.state, "model_load_error", "model not loaded")
        health_status["components"]["model"] = model_error
    
    # Return appropriate status code
    status_code = 200 if health_status["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=health_status)


# ── Global error handler ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
