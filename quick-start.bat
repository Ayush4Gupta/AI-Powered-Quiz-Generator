@echo off
echo 🚀 FAST LOCAL SETUP (Skip Docker Build)
echo =========================================
echo.

echo 📦 Step 1: Start only Redis and Weaviate with Docker
echo.
docker-compose up -d redis weaviate
echo.

echo ⏳ Waiting for services to start...
timeout /t 5 /nobreak >nul

echo 🔍 Step 2: Check if services are running
echo.
echo Checking Redis...
docker exec quiz-redis-1 redis-cli ping 2>nul || echo ❌ Redis not ready

echo Checking Weaviate...
curl -s http://localhost:8080/v1/meta >nul 2>&1 && echo ✅ Weaviate ready || echo ❌ Weaviate not ready

echo.
echo 🐍 Step 3: Install Python dependencies locally
echo.
pip install -r requirements.txt

echo.
echo 🌟 Step 4: Start Celery worker
echo.
start cmd /k "set PYTHONPATH=%CD% && set CELERY_BROKER_URL=redis://localhost:6379/0 && set WEAVIATE_URL=http://localhost:8080 && celery -A app.background.tasks worker --loglevel=info -P solo"

echo.
echo 🚀 Step 5: Start FastAPI server
echo.
echo Starting server at http://localhost:8000
echo Press Ctrl+C to stop
echo.
set PYTHONPATH=%CD%
set WEAVIATE_URL=http://localhost:8080
set CELERY_BROKER_URL=redis://localhost:6379/0
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
