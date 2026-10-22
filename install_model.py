#!/usr/bin/env python3
"""
أداة تثبيت والتحقق من نموذج الترجمة (English -> Arabic) محلياً.
تُستخدم لتنزيل النموذج لمرة واحدة عند توفر اتصال بالإنترنت،
أو لتثبيت ملف النموذج (.argosmodel) المحفوظ مسبقاً دون اتصال.
"""

import os
import sys
import argparse

try:
    import argostranslate.package
    import argostranslate.translate
except ImportError:
    print("[ERROR] مكتبة argostranslate غير مثبتة.")
    print("يرجى تثبيتها أولاً عبر الأمر:")
    print("    pip install -r requirements.txt")
    sys.exit(1)


FROM_CODE = "en"
TO_CODE = "ar"


def check_status():
    """التحقق من حالة تثبيت النموذج وطباعة التفاصيل."""
    print("=" * 60)
    print("فحص نماذج الترجمة المثبتة محلياً (Argos Translate):")
    print("=" * 60)

    installed_packages = argostranslate.package.get_installed_packages()
    target_package = None

    for pkg in installed_packages:
        print(f" - نموذج مثبت: {pkg.from_code} ({pkg.from_name}) -> {pkg.to_code} ({pkg.to_name}) [الإصدار: {pkg.package_version}]")
        if pkg.from_code == FROM_CODE and pkg.to_code == TO_CODE:
            target_package = pkg

    print("-" * 60)
    if target_package:
        print(f"✅ نموذج الترجمة المطلوب (English -> Arabic) مثبت ومتاح محلياً 100%!")
        print(f"اسم الحزمة: {getattr(target_package, 'package_name', 'en_ar')}")
        print(f"الإصدار: {target_package.package_version}")
        return True
    else:
        print(f"❌ نموذج الترجمة من الإنجليزية إلى العربية غير مثبت حالياً.")
        print("يمكنك تثبيته بالطرق التالية:")
        print("1. مع توفر الإنترنت: python3 install_model.py")
        print("2. بدون إنترنت من ملف محلي: python3 install_model.py <path/to/translate-en_ar.argosmodel>")
        return False


def install_from_file(file_path: str):
    """تثبيت النموذج من ملف .argosmodel محلي دون أي اتصال بالإنترنت."""
    if not os.path.exists(file_path):
        print(f"[ERROR] الملف غير موجود: {file_path}")
        sys.exit(1)

    print(f"[*] جارٍ تثبيت النموذج من الملف المحلي: {file_path}")
    try:
        argostranslate.package.install_from_path(file_path)
        print("✅ تم تثبيت النموذج بنجاح!")
        check_status()
    except Exception as e:
        print(f"[ERROR] فشل تثبيت النموذج: {e}")
        sys.exit(1)


def download_and_install():
    """تحديث الفهرس وتنزيل النموذج المطلوب وتثبيته محلياً (يتطلب إنترنت لأول مرة فقط)."""
    print("=" * 60)
    print("بدء تنزيل وتثبيت نموذج الإنجليزية -> العربية لأول مرة...")
    print("ملاحظة: تحتاج اتصالاً بالإنترنت في هذه الخطوة فقط لمرة واحدة.")
    print("=" * 60)

    # التحقق أولاً إذا كان النموذج مثبتاً بالفعل
    installed_packages = argostranslate.package.get_installed_packages()
    already_installed = any(p.from_code == FROM_CODE and p.to_code == TO_CODE for p in installed_packages)
    if already_installed:
        print("✅ النموذج مثبت بالفعل ولا حاجة لتنزيله مرة أخرى.")
        check_status()
        return

    print("[1/3] جارٍ تحديث فهرس الحزم المتاحة من خوادم Argos Translate...")
    try:
        argostranslate.package.update_package_index()
    except Exception as e:
        print(f"[ERROR] تعذر تحديث فهرس الحزم. تأكد من اتصال الإنترنت: {e}")
        sys.exit(1)

    print("[2/3] البحث عن حزمة الترجمة (English -> Arabic)...")
    available_packages = argostranslate.package.get_available_packages()
    package_to_install = next(
        filter(
            lambda x: x.from_code == FROM_CODE and x.to_code == TO_CODE,
            available_packages,
        ),
        None,
    )

    if not package_to_install:
        print("[ERROR] لم يتم العثور على نموذج من English إلى Arabic في الفهرس المتاح.")
        sys.exit(1)

    print(f"[*] تم العثور على النموذج: {package_to_install}")
    print("[3/3] جارٍ تنزيل ملف النموذج وتثبيته في المسار المحلي (~/.local/share/argos-translate)...")
    try:
        download_path = package_to_install.download()
        print(f"[*] تم تنزيل الملف مؤقتاً إلى: {download_path}")
        argostranslate.package.install_from_path(download_path)
        print("✅ اكتمل التثبيت بنجاح! البرنامج الآن جاهز للعمل بدون إنترنت بالكامل.")
    except Exception as e:
        print(f"[ERROR] حدث خطأ أثناء التنزيل والتثبيت: {e}")
        sys.exit(1)

    print("\nنتيجة الفحص:")
    check_status()


def main():
    parser = argparse.ArgumentParser(description="أداة إدارة وتثبيت نموذج الترجمة من الإنجليزية إلى العربية.")
    parser.add_argument(
        "model_file",
        nargs="?",
        default=None,
        help="مسار ملف النموذج المحلي (.argosmodel) للتثبيت دون اتصال بالإنترنت."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="فحص ما إذا كان النموذج مثبتاً محلياً وعرض التفاصيل."
    )

    args = parser.parse_args()

    if args.check:
        check_status()
    elif args.model_file:
        install_from_file(args.model_file)
    else:
        download_and_install()


if __name__ == "__main__":
    main()
