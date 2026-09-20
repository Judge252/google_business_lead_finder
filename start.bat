@echo off
setlocal
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env
  echo.
  echo Created .env. Put your GOOGLE_MAPS_API_KEY inside it, then run this file again.
  pause
  exit /b 0
)
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
