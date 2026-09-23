@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10+ is required. Install Python and run this file again.
    pause
    exit /b 1
  )
  py -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import streamlit, openai, dotenv" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
echo Opening TaskForge at http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1
if errorlevel 1 goto :error
exit /b 0
:error
echo Setup or startup failed. See the error above.
pause
exit /b 1
