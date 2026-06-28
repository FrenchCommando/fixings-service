@echo off
rem JAR-free launcher: the native thetadata gRPC client lives inside service.py,
rem so there is no ThetaTerminal.jar to start anymore. Just run the service.
cd /d %~dp0
start "fixings-service" .venv\Scripts\python -m service

rem set browser_value=chrome
set browser_value=firefox
start %browser_value% "http://localhost:5000"
