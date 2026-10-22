@echo off
chcp 65001 >nul
title Offline English to Arabic Translator GUI

cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo =========================================================
echo    🚀 تشغيل الواجهة المكتبية لمترجم الإنجليزية إلى العربية
echo =========================================================

"%PYTHON_EXE%" "gui.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] حدث خطأ أثناء تشغيل الواجهة.
    echo تأكد من تشغيل install_windows.bat أولاً.
    echo.
    pause
)
