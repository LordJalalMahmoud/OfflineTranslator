@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo =========================================================
echo    ⚡ تشغيل TurboTranslator Web (المترجم المحلي الأوفلاين)
echo =========================================================

"%PYTHON_EXE%" "server.py" %*
if %errorlevel% neq 0 pause
