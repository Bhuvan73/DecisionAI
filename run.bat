@echo off
setlocal
cd /d "%~dp0"
title DecisionAI

where py >nul 2>nul && (set PY=py -3) || (where python >nul 2>nul && (set PY=python) || (
  echo Python 3.10+ was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause & exit /b 1))

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || (echo Failed to create the virtual environment. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat

if not exist .venv\.installed3 (
  echo Installing dependencies - first run only, needs internet...
  python -m pip install --upgrade pip >nul
  pip install -r requirements.txt || (echo Dependency installation failed. See README Troubleshooting. & pause & exit /b 1)
  echo done> .venv\.installed3
)

if not exist .env copy .env.example .env >nul

if /i "%1"=="test" (
  python -m pytest -q
  pause & exit /b
)

start "" http://localhost:8000
python server.py
pause
