@echo off
chcp 65001 >nul
title TurboTranslator Web Edition | المترجم فائق السرعة

cd /d "%~dp0"

:: التحقق من مسار بايثون
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo =========================================================
echo    ⚡ تشغيل TurboTranslator Web (المترجم المحلي الأوفلاين)
echo =========================================================
echo.

"%PYTHON_EXE%" "fast_translator_web\server.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] حدث خطأ أثناء تشغيل الخادم.
    echo إذا لم تكن قمت بالتثبيت بعد، يرجى تشغيل install_windows.bat أولاً.
    echo.
    pause
)
