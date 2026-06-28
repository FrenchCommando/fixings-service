@echo off
rem JAR-free launcher: the native thetadata gRPC client lives inside service.py,
rem so there is no ThetaTerminal.jar to start anymore. Just run the service.
rem
rem Sets the environment contract (see .env.example) — the same single source the
rem container uses, so local and Docker behave identically.
cd /d %~dp0

set PG_HOST=localhost
set PG_PORT=5432
set PG_DATABASE=fixings
set POSTGRES_USER=fixings_user
set POSTGRES_PASSWORD_FILE=%~dp0secrets\db_password
set THETADATA_CREDS_FILE=%~dp0secrets\theta_creds.json

start "fixings-service" .venv\Scripts\python -m service

rem set browser_value=chrome
set browser_value=firefox
start %browser_value% "http://localhost:5000"
