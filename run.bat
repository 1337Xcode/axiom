@echo off
REM AXIOM A2A Banking Agents - Windows Run Script
REM Requires: Docker Desktop running

echo [AXIOM] Checking Docker...
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    exit /b 1
)

echo [AXIOM] Checking .env file...
if not exist .env (
    echo [WARN] No .env file found. Copying env.local to .env
    copy env.local .env
    echo [INFO] Edit .env with your GOOGLE_API_KEY before running.
    exit /b 1
)

echo [AXIOM] Building containers...
docker-compose build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    exit /b 1
)

echo [AXIOM] Starting services (redis, personal-agent:9001, cs-agent:9002)...
docker-compose up -d
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start services.
    exit /b 1
)

echo.
echo [AXIOM] Services running:
echo   Personal Agent: http://localhost:9001
echo   CS Agent:       http://localhost:9002
echo   Redis:          localhost:6379
echo.
echo [AXIOM] Waiting for agents to be ready...
timeout /t 10 /nobreak >nul

echo [AXIOM] Checking agent health...
curl -s http://localhost:9001/.well-known/agent.json >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Personal Agent not responding yet. Check logs: docker-compose logs personal-agent
) else (
    echo [OK] Personal Agent is serving.
)

curl -s http://localhost:9002/.well-known/agent.json >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] CS Agent not responding yet (indexing KB). Check logs: docker-compose logs cs-agent
) else (
    echo [OK] CS Agent is serving.
)

echo.
echo [AXIOM] To stop: docker-compose down
echo [AXIOM] To view logs: docker-compose logs -f
