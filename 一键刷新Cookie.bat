@echo off
chcp 65001 >nul
title Grok2API Management Tool
echo.
echo  ==========================================
echo   Grok2API Management Tool
echo  ==========================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found!
    echo  Please install Python from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python "%~dp0refresh_cookie.py"
