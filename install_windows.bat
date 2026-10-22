@echo off
chcp 65001 >nul
title تثبيت برنامج المترجم الأوفلاين | Offline Translator Setup

echo =========================================================
echo    🚀 تثبيت برنامج المترجم بدون إنترنت (Windows Setup)
echo =========================================================
echo.

:: 1. التحقق من وجود بايثون
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] بايثون غير مثبت أو غير مضاف لـ PATH!
    echo يرجى تنزيل وتثبيت Python من موقع python.org
    echo وتأكد من تحديد خيار: [Add Python to PATH] أثناء التثبيت.
    echo.
    pause
    exit /b 1
)

echo [*] تم العثور على بايثون في النظام بنجاح.

:: 2. إنشاء البيئة الافتراضية venv إذا لم تكن موجودة
if not exist "venv" (
    echo [*] جاري إنشاء بيئة العمل الافتراضية (venv)...
    python -m venv venv
)

:: 3. تفعيل البيئة وتثبيت المتطلبات
echo [*] جاري تثبيت الحزم المطلوبة (ctranslate2, sentencepiece, argostranslate)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. التحقق من النموذج وتثبيته محلياً
if exist "translate-en_ar-1_0.argosmodel" (
    echo [*] جاري تثبيت نموذج الترجمة المحلي من ملف translate-en_ar-1_0.argosmodel...
    python install_model.py translate-en_ar-1_0.argosmodel
) else (
    echo [*] جاري التحقق من حالة النموذج...
    python install_model.py
)

echo.
echo =========================================================
echo    ✅ اكتمل التثبيت بنجاح وجاهز للاستخدام أوفلاين 100%!
echo =========================================================
echo.
echo لتشغيل واجهة الويب العصرية: انقر نقراً مزدوجاً على [run_web.bat]
echo لتشغيل الواجهة المكتبية:     انقر نقراً مزدوجاً على [run_gui.bat]
echo.
pause
