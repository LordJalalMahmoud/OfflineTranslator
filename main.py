#!/usr/bin/env python3
"""
نقطة الدخول الرئيسية لبرنامج الترجمة المحلي بالكامل (English -> Arabic)
"""

import sys
import argparse


def run():
    parser = argparse.ArgumentParser(
        description="برنامج الترجمة المحلي بالكامل من الإنجليزية إلى العربية (Offline Neural Translator)"
    )
    parser.add_argument(
        "-t", "--text",
        type=str,
        help="ترجمة نص مباشرة من سطر الأوامر دون فتح الواجهة الرسومية"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="عرض حالة تثبيت النموذج المحلي"
    )

    args = parser.parse_args()

    if args.status:
        from install_model import check_status
        check_status()
        return

    if args.text:
        from translator import translate_text, is_model_installed
        if not is_model_installed("en", "ar"):
            print("[خطأ] نموذج الترجمة غير مثبت محلياً.")
            print("لتثبيته شغّل: python3 install_model.py")
            sys.exit(1)
        
        print(f"النص الأصلي:\n{args.text}\n")
        translated = translate_text(args.text)
        print(f"الترجمة العربية:\n{translated}")
        return

    # التشغيل الافتراضي: إطلاق الواجهة الرسومية Tkinter
    from gui import launch_gui
    launch_gui()


if __name__ == "__main__":
    run()
