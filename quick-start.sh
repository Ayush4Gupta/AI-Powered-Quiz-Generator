#!/bin/bash

echo "🚀 FAST LOCAL SETUP (Skip Docker Build)"
echo "========================================="
echo

echo "📦 Step 1: Start only Redis and Weaviate with Docker"
echo
docker-compose up -d redis weaviate
echo

echo "⏳ Waiting for services to start..."
sleep 5

echo "🔍 Step 2: Check if services are running"
echo
echo "Checking Redis..."
if docker exec $(docker-compose ps -q redis) redis-cli ping >/dev/null 2>&1; then
    echo "✅ Redis ready"
else
    echo "❌ Redis not ready"
fi

echo "Checking Weaviate..."
if curl -s http://localhost:8080/v1/meta >/dev/null 2>&1; then
    echo "✅ Weaviate ready"
else
    echo "❌ Weaviate not ready"
fi

echo
echo "🐍 Step 3: Install Python dependencies locally"
echo
pip install -r requirements.txt

echo
echo "🚀 Step 4: Start FastAPI server"
echo
echo "Starting server at http://localhost:8000"
echo "Press Ctrl+C to stop"
echo

export WEAVIATE_URL=http://localhost:8080
export CELERY_BROKER_URL=redis://localhost:6379/0
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
