@echo off
cd /d "%~dp0"
set "PYTHONUTF8=1"
rem First run or broken environment: install uv, Python and dependencies first
"%~dp0.venv\Scripts\python.exe" -c "import selenium" >nul 2>nul
if errorlevel 1 call "%~dp0install.cmd" -FromStart
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -u "%~dp0webui.py"
pause
