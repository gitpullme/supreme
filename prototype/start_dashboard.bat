@echo off
REM SAT-SA dev launcher (Option A): rebuilds everything, then serves dashboards.
REM Legacy HTML dashboard : http://127.0.0.1:8000/
REM React SPA             : http://127.0.0.1:8000/app/
REM JSON API              : http://127.0.0.1:8000/api/validate etc.
cd /d "%~dp0"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" run.py --serve
pause
