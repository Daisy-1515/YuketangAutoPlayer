@echo off
rem Windows entry for install.ps1. The logic lives in PowerShell because cmd misparses UTF-8 Chinese text.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %errorlevel%
