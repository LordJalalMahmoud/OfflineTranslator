"""
وحدة الترجمة المحلية - Local Translation Engine
تعتمد على مكتبة Argos Translate للترجمة بدون اتصال بالإنترنت بالكامل.
"""

import re
from typing import Callable, Optional, List

# استيراد argostranslate بحذر لتجنب الانهيار في حال عدم التثبيت
try:
    import argostranslate.package
    import argostranslate.translate
    ARGOS_AVAILABLE = True
except ImportError:
    ARGOS_AVAILABLE = False


class ModelNotFoundError(Exception):
    """يتم رمي هذا الاستثناء إذا لم يكن نموذج الترجمة مثبتاً محلياً."""
    pass


class ArgosNotInstalledError(Exception):
    """يتم رمي هذا الاستثناء إذا لم تكن مكتبة argostranslate مثبتة."""
    pass


def get_installed_languages_codes() -> List[str]:
    """إرجاع قائمة برموز اللغات المثبتة محلياً."""
    if not ARGOS_AVAILABLE:
        return []
    try:
        langs = argostranslate.translate.get_installed_languages()
        return [lang.code for lang in langs]
    except Exception:
        return []


def is_model_installed(from_code: str = "en", to_code: str = "ar") -> bool:
    """التحقق مما إذا كان نموذج الترجمة بين اللغتين متوفراً ومثبتاً محلياً."""
    if not ARGOS_AVAILABLE:
        return False
    try:
        installed_languages = argostranslate.translate.get_installed_languages()
        from_lang = next((lang for lang in installed_languages if lang.code == from_code), None)
        to_lang = next((lang for lang in installed_languages if lang.code == to_code), None)
        if from_lang and to_lang:
            translation = from_lang.get_translation(to_lang)
            return translation is not None
        return False
    except Exception:
        return False


def get_model_info(from_code: str = "en", to_code: str = "ar") -> Optional[dict]:
    """الحصول على معلومات النموذج المثبت إن وجد."""
    if not ARGOS_AVAILABLE:
        return None
    try:
        packages = argostranslate.package.get_installed_packages()
        for pkg in packages:
            if pkg.from_code == from_code and pkg.to_code == to_code:
                return {
                    "package_name": getattr(pkg, "package_name", f"{from_code}_{to_code}"),
                    "from_name": getattr(pkg, "from_name", from_code),
                    "to_name": getattr(pkg, "to_name", to_code),
                    "package_version": getattr(pkg, "package_version", "unknown"),
                    "description": getattr(pkg, "description", "")
                }
    except Exception:
        pass
    return None


def split_into_paragraphs_and_sentences(text: str, max_chunk_chars: int = 800) -> List[str]:
    """
    تقسيم النص الطويل إلى أجزاء ذكية تحافظ على الفقرات وعلامات الترقيم والجمل،
    مما يضمن عدم تجاوز الحد الأقصى لطول الجملة في نموذج الترجمة.
    """
    if not text:
        return []

    # التقسيم أولاً حسب الأسطر الفارغة (الفقرات)
    raw_paragraphs = text.split("\n")
    chunks: List[str] = []

    for para in raw_paragraphs:
        stripped = para.strip()
        if not stripped:
            # الحفاظ على السطر الفارغ
            chunks.append("")
            continue

        if len(stripped) <= max_chunk_chars:
            chunks.append(stripped)
        else:
            # إذا كانت الفقرة طويلة جداً، نقسمها حسب نهايات الجمل (نقطة، استفهام، تعجب)
            # مع الاحتفاظ بعلامات الترقيم
            sentence_splits = re.split(r'([.?!;:]\s+)', stripped)
            current_chunk = ""
            for i in range(0, len(sentence_splits), 2):
                sent = sentence_splits[i]
                delimiter = sentence_splits[i + 1] if i + 1 < len(sentence_splits) else ""
                combined = sent + delimiter

                if len(current_chunk) + len(combined) <= max_chunk_chars:
                    current_chunk += combined
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = combined

            if current_chunk.strip():
                chunks.append(current_chunk.strip())

    return chunks


def translate_text(
    text: str,
    from_code: str = "en",
    to_code: str = "ar",
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> str:
    """
    ترجمة النص محلياً بالكامل.
    
    المعطيات:
        text: النص الإنجليزي المراد ترجمته.
        from_code: لغة المصدر (الافتراضية: en).
        to_code: لغة الهدف (الافتراضية: ar).
        progress_callback: دالة اختيارية لإشعار الواجهة بالتقدم (current, total, status_message).
        
    المخرجات:
        النص العربي المترجم.
    """
    if not ARGOS_AVAILABLE:
        raise ArgosNotInstalledError("مكتبة argostranslate غير مثبتة في بيئة بايثون.")

    if not text or not text.strip():
        return ""

    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed_languages if lang.code == from_code), None)
    to_lang = next((lang for lang in installed_languages if lang.code == to_code), None)

    if not from_lang or not to_lang:
        raise ModelNotFoundError(
            f"نموذج الترجمة من ({from_code}) إلى ({to_code}) غير مثبت محلياً.\n"
            f"يرجى تشغيل أداة تثبيت النموذج: python3 install_model.py"
        )

    translation = from_lang.get_translation(to_lang)
    if not translation:
        raise ModelNotFoundError(
            f"لم يتم العثور على مسار ترجمة مباشر من ({from_code}) إلى ({to_code}).\n"
            f"يرجى التأكد من تثبيت النموذج المطلوب عبر: python3 install_model.py"
        )

    # تقسيم النص إلى أجزاء مناسبة للتعامل مع النصوص الطويلة
    chunks = split_into_paragraphs_and_sentences(text)
    total_chunks = len([c for c in chunks if c.strip()])
    translated_pieces: List[str] = []
    processed_count = 0

    if total_chunks == 0:
        return ""

    if progress_callback:
        progress_callback(0, total_chunks, "بدء الترجمة المحلية...")

    for chunk in chunks:
        if not chunk.strip():
            translated_pieces.append("")
            continue

        processed_count += 1
        if progress_callback:
            progress_callback(
                processed_count,
                total_chunks,
                f"ترجمة الجزء {processed_count} من {total_chunks}..."
            )

        # تنفيذ الترجمة بواسطة النموذج المحلي (CTranslate2 خلف الكواليس)
        chunk_translation = translation.translate(chunk)
        translated_pieces.append(chunk_translation)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "اكتملت الترجمة بنجاح.")

    # إعادة تجميع النص الناتج مع مراعاة فواصل الأسطر الأصلية
    return "\n".join(translated_pieces)
