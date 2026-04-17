#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────
# CloudSense — Local Development Launcher
# Usage: ./run.sh
# ─────────────────────────────────────────────────────────────────

BACKEND_PORT=8000
FRONTEND_PORT=5173

cleanup() {
    echo ""
    echo "Stopping CloudSense..."
    # Kill all background jobs spawned by this script
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "================================================"
echo "  CloudSense — Local Dev"
echo "================================================"

# ── Backend ──────────────────────────────────────────────────────
echo ""
echo "[1/2] Starting backend on :${BACKEND_PORT}..."
cd backend

# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source ../venv/bin/activate
else
    echo "  ⚠  No venv found — using system Python"
fi

# Create .env if missing
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ⚠  Created .env from .env.example — edit it before use"
fi

uvicorn main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT}" &
BACKEND_PID=$!
cd ..

# ── Frontend ─────────────────────────────────────────────────────
echo "[2/2] Starting frontend on :${FRONTEND_PORT}..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies..."
    npm install
fi

npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}" &
FRONTEND_PID=$!
cd ..

# ── Ready ─────────────────────────────────────────────────────────
echo ""
echo "  Backend  →  http://localhost:${BACKEND_PORT}/docs"
echo "  Frontend →  http://localhost:${FRONTEND_PORT}"
echo ""
echo "  Press Ctrl+C to stop all services."
echo ""

wait "${BACKEND_PID}" "${FRONTEND_PID}"
