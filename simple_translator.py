"""
وحدة ترجمة خفيفة ومباشرة للاستخدام البرمجي في مشاريع بايثون الأخرى.
Simple Offline Translation Library (English -> Arabic)
"""

import logging
import re
import warnings
from typing import List, Optional

# كتم التحذيرات المعتادة لتقليل المخرجات غير الضرورية.
warnings.filterwarnings("ignore")
logging.getLogger("stanza").setLevel(logging.ERROR)

# اجعل Stanza تستخدم الموارد المحلية فقط قبل أن يستدعيها Argos.
# هذا يمنع محاولة تنزيل resources.json أثناء تهيئة Pipeline.
try:
    import stanza

    _original_stanza_pipeline = stanza.Pipeline

    def _offline_stanza_pipeline(*args, **kwargs):
        kwargs["download_method"] = None
        return _original_stanza_pipeline(*args, **kwargs)

    stanza.Pipeline = _offline_stanza_pipeline
except ImportError:
    # سيظهر خطأ واضح عند تهيئة المترجم إذا كانت إحدى المكتبات المطلوبة ناقصة.
    pass

try:
    import argostranslate.translate
    import argostranslate.package

    ARGOS_AVAILABLE = True
except ImportError:
    ARGOS_AVAILABLE = False


class ModelNotInstalledError(Exception):
    """يتم رمي هذا الخطأ إذا لم يكن نموذج الترجمة مثبتاً على الجهاز."""


class OfflineTranslator:
    """
    فئة بسيطة ومستقلة لإدارة الترجمة باستخدام نموذج محلي.

    مثال:
        translator = OfflineTranslator()
        result = translator.translate("Hello, how are you?")
    """

    def __init__(self, from_lang: str = "en", to_lang: str = "ar"):
        if not ARGOS_AVAILABLE:
            raise ImportError(
                "مكتبة argostranslate غير مثبتة.\n"
                "يرجى تثبيتها عبر: pip install argostranslate"
            )

        self.from_lang_code = from_lang
        self.to_lang_code = to_lang
        self._translation = None
        self._load_engine()

    def _load_engine(self):
        """تحميل محرك الترجمة والتأكد من توفر النموذج محلياً."""
        installed_languages = (
            argostranslate.translate.get_installed_languages()
        )
        from_lang = next(
            (lang for lang in installed_languages
             if lang.code == self.from_lang_code),
            None,
        )
        to_lang = next(
            (lang for lang in installed_languages
             if lang.code == self.to_lang_code),
            None,
        )

        if not from_lang or not to_lang:
            raise ModelNotInstalledError(
                f"نموذج الترجمة من ({self.from_lang_code}) إلى "
                f"({self.to_lang_code}) غير مثبت محلياً.\n"
                "يرجى تثبيت النموذج أولاً عبر أداة install_model.py"
            )

        self._translation = from_lang.get_translation(to_lang)
        if not self._translation:
            raise ModelNotInstalledError(
                f"تعذر العثور على مسار ترجمة مباشر من "
                f"({self.from_lang_code}) إلى ({self.to_lang_code})."
            )

    def translate(self, text: str) -> str:
        """ترجمة النص وإرجاع النتيجة كنص، مع الحفاظ على فواصل الأسطر."""
        if not text or not text.strip():
            return ""

        lines = text.split("\n")
        translated_lines: List[str] = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                translated_lines.append("")
                continue

            # تقسيم الفقرات الطويلة إلى أجزاء أصغر.
            if len(line_stripped) > 800:
                sentence_splits = re.split(
                    r"([.?!;:]\s+)",
                    line_stripped,
                )
                parts = []
                current_chunk = ""

                for i in range(0, len(sentence_splits), 2):
                    sentence = sentence_splits[i]
                    delimiter = (
                        sentence_splits[i + 1]
                        if i + 1 < len(sentence_splits)
                        else ""
                    )
                    combined = sentence + delimiter

                    if len(current_chunk) + len(combined) <= 800:
                        current_chunk += combined
                    else:
                        if current_chunk.strip():
                            parts.append(
                                self._translation.translate(
                                    current_chunk.strip()
                                )
                            )
                        current_chunk = combined

                if current_chunk.strip():
                    parts.append(
                        self._translation.translate(current_chunk.strip())
                    )

                translated_lines.append(" ".join(parts))
            else:
                translated_lines.append(
                    self._translation.translate(line_stripped)
                )

        return "\n".join(translated_lines)


# كائن افتراضي يعاد استخدامه لتجنب إعادة تحميل المحرك عند كل استدعاء.
_default_translator: Optional[OfflineTranslator] = None


def translate(text: str, from_lang: str = "en", to_lang: str = "ar") -> str:
    """
    دالة مباشرة للترجمة.

    مثال:
        from simple_translator import translate
        arabic = translate("Good morning")
        print(arabic)
    """
    global _default_translator

    if (
        _default_translator is None
        or _default_translator.from_lang_code != from_lang
        or _default_translator.to_lang_code != to_lang
    ):
        _default_translator = OfflineTranslator(
            from_lang=from_lang,
            to_lang=to_lang,
        )

    return _default_translator.translate(text)
