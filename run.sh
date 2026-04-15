#!/bin/bash

# CloudSense Launcher
# Usage: ./run.sh

cleanup() {
    echo ""
    echo "🛑 Stopping CloudSense services..."
    kill 0
    exit
}

trap cleanup SIGINT SIGTERM EXIT

echo "=================================="
echo "🚀 Starting CloudSense System..."
echo "=================================="

# 1. Start Backend (FastAPI)
echo ""
echo "🔹 Starting Backend on port 8000..."
cd backend

if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠ venv not found. Using system python."
fi

# Use new modular entry point
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# 2. Start Frontend (React/Vite)
echo ""
echo "🔹 Starting Frontend on port 5173..."
cd frontend
npm run dev -- --host &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ CloudSense is running!"
echo "   Backend API: http://localhost:8000/docs"
echo "   Dashboard:   http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services."

wait $BACKEND_PID $FRONTEND_PID
