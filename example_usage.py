#!/usr/bin/env python3
"""
مثال عملي يوضح كيفية استدعاء دالة الترجمة من أي برنامج بايثون خارجي
"""

# استدعاء دالة الترجمة المباشرة
from simple_translator import translate, OfflineTranslator

# 1. الاستخدام المباشر والأبسط:
english_text = "Python is a powerful programming language."
arabic_text = translate(english_text)

print("--- [الطريقة 1: استدعاء الدالة المباشرة] ---")
print(f"النص الإنجليزي: {english_text}")
print(f"النص العربي:    {arabic_text}\n")


# 2. ترجمة نص طويل متعدد الفقرات:
long_paragraph = """Machine learning models can run directly on edge devices.
This ensures user privacy and eliminates the need for an internet connection.

Offline translation provides speed, security, and full autonomy."""

translated_paragraph = translate(long_paragraph)

print("--- [الطريقة 2: ترجمة نصوص متعددة الفقرات] ---")
print(translated_paragraph)
print()


# 3. استخدام الفئة (Class) في حال الرغبة في الاحتفاظ بنسخة مخصصة:
print("--- [الطريقة 3: استخدام فئة OfflineTranslator] ---")
translator = OfflineTranslator(from_lang="en", to_lang="ar")
custom_result = translator.translate("Welcome to Linux world.")
print(f"النتيجة: {custom_result}")
