"""
CloudSense API - Minimal Pipeline
Upload H5 → Run Inference → Download 3 Outputs (mask.npy, mask.png, output.nc)
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from contextlib import asynccontextmanager
from typing import Optional
import os
import shutil
import uuid
import logging

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from db import (
    init_db, create_user, get_user_by_email, get_user_by_id,
    create_analysis, update_analysis_status, get_analysis, get_recent_analyses,
    save_analysis_results, get_analysis_results,
    get_dashboard_stats, get_all_recent_clusters
)
from auth import hash_password, verify_password, create_jwt_token, verify_jwt_token
import jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===================== APP SETUP =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    init_db()
    logger.info("Database initialized")
    yield

app = FastAPI(title="CloudSense API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== DIRECTORIES =====================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount output directory for static file serving
app.mount("/static/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output_direct")


# ===================== AUTH MODELS =====================

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


# ===================== AUTH DEPENDENCY =====================

async def verify_token(request: Request):
    """Verify JWT token and return user info"""
    authorization = request.headers.get("authorization")
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")

    try:
        payload = verify_jwt_token(token)
        user = get_user_by_id(int(payload["sub"]))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        }
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


# ===================== HEALTH =====================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "CloudSense API is running"}


# ===================== MOSDAC DOWNLOAD (SSE Streaming) =====================

import subprocess
import json
import glob
import math
from datetime import datetime, timedelta
from fastapi.responses import StreamingResponse

class MOSDACDownloadRequest(BaseModel):
    username: str
    password: str
    hours_back: float = 1  # Download data from last N hours (0.5 = 30 min)

MOSDAC_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "MOSDAC_Data")
os.makedirs(MOSDAC_DATA_DIR, exist_ok=True)


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/mosdac/download")
async def download_mosdac_data(request: MOSDACDownloadRequest):
    """
    Download INSAT-3DR data from MOSDAC and run inference.
    Returns an SSE stream with real-time progress events.
    """

    def stream_generator():
        try:
            # 1. Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=request.hours_back)
            max_files = max(2, math.ceil(request.hours_back * 2))

            yield _sse_event("progress", {"step": "config", "message": "Preparing download configuration..."})

            # 2. Create config.json for mdapi
            config = {
                "user_credentials": {
                    "username": request.username,
                    "password": request.password
                },
                "search_parameters": {
                    "datasetId": "3RIMG_L1C_ASIA_MER",
                    "startTime": start_time.strftime("%Y-%m-%d"),
                    "endTime": end_time.strftime("%Y-%m-%d"),
                    "count": str(max_files),
                    "boundingBox": "",
                    "gId": ""
                },
                "download_settings": {
                    "download_path": MOSDAC_DATA_DIR,
                    "organize_by_date": False,
                    "skip_user_prompt": True,
                    "generate_error_log": False,
                    "error_log_path": ""
                }
            }

            project_root = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(project_root, "config.json")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Snapshot existing files BEFORE download
            existing_h5 = set(glob.glob(os.path.join(MOSDAC_DATA_DIR, "**", "*.h5"), recursive=True))
            existing_h5.update(glob.glob(os.path.join(MOSDAC_DATA_DIR, "*.h5")))

            yield _sse_event("progress", {"step": "connect", "message": "Connecting to MOSDAC API..."})

            # 3. Run mdapi.py with Popen for live streaming
            mdapi_path = os.path.join(project_root, "mosdac_engine", "mdapi.py")
            if not os.path.exists(mdapi_path):
                yield _sse_event("error", {"message": "mdapi.py not found"})
                return

            logger.info(f"Running MOSDAC download: {mdapi_path}")

            process = subprocess.Popen(
                ["python", "-u", mdapi_path],  # -u for unbuffered output
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line-buffered
            )

            # Stream stdout lines as progress events
            noise_patterns = ['%|', 'resource_tracker', 'UserWarning', 'warnings.warn']
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line or any(p in line for p in noise_patterns):
                    continue

                # Categorize the line for better frontend display
                if '[ERROR]' in line:
                    yield _sse_event("progress", {"step": "download", "message": f"⚠ {line}"})
                elif '[SKIP]' in line:
                    yield _sse_event("progress", {"step": "download", "message": f"⏭ {line}"})
                elif 'Found' in line and 'files' in line:
                    yield _sse_event("progress", {"step": "search", "message": f"🔍 {line}"})
                elif 'Downloading' in line or 'RETRY' in line:
                    yield _sse_event("progress", {"step": "download", "message": f"📥 {line}"})
                elif 'Logged in' in line:
                    yield _sse_event("progress", {"step": "auth", "message": f"✓ {line}"})
                elif 'Download complete' in line:
                    yield _sse_event("progress", {"step": "download_done", "message": f"✓ {line}"})
                else:
                    yield _sse_event("progress", {"step": "download", "message": line})

            process.stdout.close()
            return_code = process.wait(timeout=600)

            if return_code != 0:
                stderr_output = process.stderr.read()
                error_lines = [
                    l for l in stderr_output.splitlines()
                    if l.strip() and not any(p in l for p in noise_patterns)
                ]
                error_msg = '\n'.join(error_lines[-5:]) if error_lines else f"Process exited with code {return_code}"
                logger.error(f"MOSDAC Error: {error_msg}")
                yield _sse_event("error", {"message": f"Download failed: {error_msg}"})
                return

            process.stderr.close()

            # 4. Find newly downloaded H5 files
            all_h5 = set(glob.glob(os.path.join(MOSDAC_DATA_DIR, "**", "*.h5"), recursive=True))
            all_h5.update(glob.glob(os.path.join(MOSDAC_DATA_DIR, "*.h5")))
            h5_files = sorted(all_h5 - existing_h5)

            if not h5_files:
                yield _sse_event("done", {
                    "status": "no_data",
                    "message": "No new data available for the selected time range",
                    "files_downloaded": 0,
                    "results": []
                })
                return

            # 5. Run inference on each file
            yield _sse_event("progress", {
                "step": "inference",
                "message": f"Running U-Net inference on {len(h5_files)} file(s)..."
            })

            pipeline = get_inference_pipeline()
            results = []

            for i, h5_path in enumerate(h5_files, 1):
                fname = os.path.basename(h5_path)
                yield _sse_event("progress", {
                    "step": "inference",
                    "message": f"🧠 Processing [{i}/{len(h5_files)}]: {fname}..."
                })

                analysis_id = str(uuid.uuid4())

                create_analysis(
                    analysis_id=analysis_id,
                    filename=fname,
                    file_path=h5_path,
                    source="mosdac_download"
                )

                result = pipeline.process_file(h5_path, OUTPUT_DIR, analysis_id)

                if result["success"]:
                    update_analysis_status(analysis_id, "complete")
                    save_analysis_results(analysis_id, result)

                    file_result = {
                        "analysis_id": analysis_id,
                        "file": fname,
                        "tcc_pixels": result.get("tcc_pixels", 0),
                        "tcc_count": result.get("tcc_count", 0),
                        "total_area_km2": result.get("total_area_km2", 0),
                        "detections": result.get("detections", []),
                        "outputs": {
                            "satellite_png": f"/api/download/{analysis_id}/satellite.png",
                            "mask_npy": f"/api/download/{analysis_id}/mask.npy",
                            "mask_png": f"/api/download/{analysis_id}/mask.png",
                            "overlay_png": f"/api/download/{analysis_id}/overlay.png",
                            "netcdf": f"/api/download/{analysis_id}/output.nc"
                        }
                    }
                    results.append(file_result)

                    tcc_count = result.get("tcc_count", 0)
                    tcc_pixels = result.get("tcc_pixels", 0)
                    area = result.get("total_area_km2", 0)
                    yield _sse_event("progress", {
                        "step": "inference",
                        "message": f"✓ {fname} — {tcc_count} TCCs detected, {tcc_pixels} TCC pixels"
                    })
                    if area:
                        yield _sse_event("progress", {
                            "step": "inference",
                            "message": f"   Total area: {area / 1000:.0f}k km²"
                        })
                else:
                    update_analysis_status(analysis_id, "failed")
                    yield _sse_event("progress", {
                        "step": "inference",
                        "message": f"⚠ Failed to process {fname}"
                    })

            # 6. Final done event with all results
            yield _sse_event("done", {
                "status": "success",
                "message": f"Downloaded and processed {len(h5_files)} files",
                "files_downloaded": len(h5_files),
                "results": results
            })

        except Exception as e:
            logger.error(f"MOSDAC stream error: {e}")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
        }
    )


# ===================== AUTH ENDPOINTS =====================

@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """Register a new user"""
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )
    
    user = get_user_by_email(request.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    password_hash = hash_password(request.password)
    user_id = create_user(request.username, request.email, password_hash)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    new_user = get_user_by_id(user_id)
    token_response = create_jwt_token(user_id, request.email)
    
    return AuthResponse(
        access_token=token_response["access_token"],
        token_type=token_response["token_type"],
        expires_in=token_response["expires_in"],
        user={
            "id": new_user["id"],
            "username": new_user["username"],
            "email": new_user["email"]
        }
    )

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login user with email and password"""
    user = get_user_by_email(request.email)
    
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    token_response = create_jwt_token(user["id"], user["email"])
    
    return AuthResponse(
        access_token=token_response["access_token"],
        token_type=token_response["token_type"],
        expires_in=token_response["expires_in"],
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        }
    )

@app.get("/api/auth/verify")
async def verify_token_endpoint(request: Request):
    """Verify JWT token and return user info"""
    return await verify_token(request)


# ===================== GOOGLE SIGN-IN =====================

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

class GoogleAuthRequest(BaseModel):
    credential: str  # Google ID token

@app.post("/api/auth/google", response_model=AuthResponse)
async def google_auth(request: GoogleAuthRequest):
    """Authenticate with Google Sign-In"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not configured. Set GOOGLE_CLIENT_ID in .env"
        )
    
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        # Verify the Google ID token
        idinfo = id_token.verify_oauth2_token(
            request.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        email = idinfo.get("email")
        name = idinfo.get("name", email.split("@")[0])
        
        if not email:
            raise HTTPException(status_code=400, detail="No email in Google token")
        
        # Find or create user
        user = get_user_by_email(email)
        
        if not user:
            # Auto-create account for Google users (random password hash since they won't use it)
            import secrets
            random_hash = hash_password(secrets.token_urlsafe(32))
            user_id = create_user(name, email, random_hash)
            if not user_id:
                # Username might conflict, add random suffix
                user_id = create_user(f"{name}_{secrets.token_urlsafe(4)}", email, random_hash)
            user = get_user_by_id(user_id)
        
        token_response = create_jwt_token(user["id"], user["email"])
        
        return AuthResponse(
            access_token=token_response["access_token"],
            token_type=token_response["token_type"],
            expires_in=token_response["expires_in"],
            user={
                "id": user["id"],
                "username": user["username"],
                "email": user["email"]
            }
        )
        
    except ValueError as e:
        logger.error(f"Google token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

@app.get("/api/auth/google/client-id")
async def get_google_client_id():
    """Return the Google Client ID for the frontend"""
    return {"client_id": GOOGLE_CLIENT_ID}

# ===================== UPLOAD & INFERENCE =====================

import asyncio

# Lazy load inference pipeline
_inference_pipeline = None

def get_inference_pipeline():
    """Lazy load the inference pipeline to avoid startup delays"""
    global _inference_pipeline
    if _inference_pipeline is None:
        from inference_engine import InferencePipeline
        _inference_pipeline = InferencePipeline()
        logger.info("Inference pipeline loaded")
    return _inference_pipeline


def _run_inference_sync(file_path: str, file_ext: str, output_dir: str, analysis_id: str):
    """Run inference synchronously (called from thread pool)."""
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
    pipeline = get_inference_pipeline()

    if file_ext in IMAGE_EXTENSIONS:
        return pipeline.process_image(file_path, output_dir, analysis_id)
    else:
        return pipeline.process_file(file_path, output_dir, analysis_id)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload H5 or image file and run inference.
    Returns analysis_id with paths to outputs: satellite.png, mask.npy, mask.png, and output.nc (H5 only)
    """
    try:
        # 1. Validate file type
        ALLOWED_EXTENSIONS = {'.h5', '.hdf5', '.png', '.jpg', '.jpeg'}
        IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only HDF5 (.h5, .hdf5) or image (.png, .jpg, .jpeg) files are allowed. Got: {file_ext}"
            )
        
        # 2. Validate file size (max 500MB)
        MAX_FILE_SIZE_MB = 500
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max: {MAX_FILE_SIZE_MB}MB"
            )
        
        # 3. Generate unique analysis ID
        analysis_id = str(uuid.uuid4())
        
        # 4. Save uploaded file
        storage_filename = f"{analysis_id}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, storage_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"File uploaded: {file.filename} -> {analysis_id}")
        
        # 5. Create analysis record
        create_analysis(
            analysis_id=analysis_id,
            filename=file.filename,
            file_path=file_path,
            source="manual_upload"
        )
        
        # 6. Run inference in thread pool (prevents blocking the event loop)
        logger.info(f"Running inference on {file.filename}...")
        result = await asyncio.to_thread(
            _run_inference_sync, file_path, file_ext, OUTPUT_DIR, analysis_id
        )
        
        if result["success"]:
            update_analysis_status(analysis_id, "complete")
            save_analysis_results(analysis_id, result)
            
            # Build response with outputs
            outputs = {
                "satellite_png": f"/api/download/{analysis_id}/satellite.png",
                "mask_npy": f"/api/download/{analysis_id}/mask.npy",
                "mask_png": f"/api/download/{analysis_id}/mask.png",
                "overlay_png": f"/api/download/{analysis_id}/overlay.png",
                "netcdf": f"/api/download/{analysis_id}/output.nc" if file_ext not in IMAGE_EXTENSIONS else None
            }
            
            return {
                "analysis_id": analysis_id,
                "status": "complete",
                "message": f"Processed {file.filename}",
                "input_type": "image" if file_ext in IMAGE_EXTENSIONS else "h5",
                "outputs": outputs,
                "tcc_pixels": result.get("tcc_pixels", 0),
                "tcc_count": result.get("tcc_count", 0),
                "total_area_km2": result.get("total_area_km2", 0),
                "detections": result.get("detections", [])
            }
        else:
            update_analysis_status(analysis_id, "failed")
            raise HTTPException(status_code=500, detail=result.get("error", "Inference failed"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===================== DOWNLOAD OUTPUTS =====================

@app.get("/api/download/{analysis_id}/{filename}")
async def download_output(analysis_id: str, filename: str):
    """
    Download output files: satellite.png, mask.npy, mask.png, overlay.png, output.nc
    """
    # Validate filename
    ALLOWED_FILES = {"satellite.png", "mask.npy", "mask.png", "overlay.png", "output.nc"}
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file. Options: {ALLOWED_FILES}")
    
    # Build file path
    file_path = os.path.join(OUTPUT_DIR, analysis_id, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Set media type
    media_types = {
        "satellite.png": "image/png",
        "mask.npy": "application/octet-stream",
        "mask.png": "image/png",
        "overlay.png": "image/png",
        "output.nc": "application/x-netcdf"
    }
    
    return FileResponse(
        file_path,
        media_type=media_types.get(filename, "application/octet-stream"),
        filename=f"{analysis_id}_{filename}"
    )


# ===================== EXPORTS LIST =====================

@app.get("/api/exports")
async def list_exports():
    """List all available exports"""
    exports = []
    
    if os.path.exists(OUTPUT_DIR):
        for analysis_id in os.listdir(OUTPUT_DIR):
            analysis_dir = os.path.join(OUTPUT_DIR, analysis_id)
            if os.path.isdir(analysis_dir):
                files = os.listdir(analysis_dir)
                exports.append({
                    "analysis_id": analysis_id,
                    "files": files,
                    "download_urls": {
                        "satellite_png": f"/api/download/{analysis_id}/satellite.png" if "satellite.png" in files else None,
                        "mask_npy": f"/api/download/{analysis_id}/mask.npy" if "mask.npy" in files else None,
                        "mask_png": f"/api/download/{analysis_id}/mask.png" if "mask.png" in files else None,
                        "netcdf": f"/api/download/{analysis_id}/output.nc" if "output.nc" in files else None
                    }
                })
    
    return exports


# ===================== RECENT ANALYSES =====================

@app.get("/api/analyses/recent")
async def list_recent_analyses(limit: int = 10):
    """Get list of recent analyses with parsed results"""
    analyses = get_recent_analyses(limit)
    
    # Parse results JSON for each analysis
    for analysis in analyses:
        if analysis.get('results'):
            try:
                if isinstance(analysis['results'], str):
                    analysis['results'] = json.loads(analysis['results'])
            except json.JSONDecodeError:
                analysis['results'] = {}
    
    return analyses


# ===================== DASHBOARD ENDPOINTS =====================

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    """Get aggregated stats for the dashboard."""
    return get_dashboard_stats()


@app.get("/api/analysis/clusters")
async def analysis_clusters(limit: int = 50):
    """Get all recent clusters for the map/table."""
    return get_all_recent_clusters(limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
