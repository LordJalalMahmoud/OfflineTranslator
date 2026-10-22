"""
وحدة تحويل النصوص العربية إلى لغة الفرانكو/العربيزي (Arabizi).
تعتمد على مكتبات C الأساسية في بايثون عبر str.maketrans لتحقيق أقصى سرعة ممكنة.
"""

ARABIZI_MAP = {
    'ا': 'a', 'أ': 'a', 'إ': 'e', 'آ': 'a',
    'ب': 'b',
    'ت': 't',
    'ث': 'th',
    'ج': 'g',
    'ح': '7',
    'خ': 'kh',
    'د': 'd',
    'ذ': 'dh',
    'ر': 'r',
    'ز': 'z',
    'س': 's',
    'ش': 'sh',
    'ص': 's',
    'ض': 'd',
    'ط': 't',
    'ظ': 'z',
    'ع': '3',
    'غ': 'gh',
    'ف': 'f',
    'ق': 'q',
    'ك': 'k',
    'ل': 'l',
    'م': 'm',
    'ن': 'n',
    'ه': 'h',
    'و': 'w',
    'ي': 'y',
    'ى': 'a',
    'ة': 'a',
    'ء': '2', 'ئ': '2', 'ؤ': '2',
    # إزالة التشكيل والتنوين
    'ً': '', 'ٌ': '', 'ٍ': '', 'َ': '', 'ُ': '', 'ِ': '', 'ّ': '', 'ْ': '',
}

_TRANS_TABLE = str.maketrans(ARABIZI_MAP)


def arabic_to_arabizi(text: str) -> str:
    """
    تحويل النص العربي إلى عربيزي في ميكروثوانٍ عبر C-level maketrans.
    """
    if not text:
        return text
    return text.translate(_TRANS_TABLE)


def get_arabizi_dictionary():
    """إرجاع جدول التحويل لعرضه في الواجهة كدليل للمستخدم."""
    return [
        {"ar": "ح", "fr": "7", "example": "7abibi (حبيبي)"},
        {"ar": "ع", "fr": "3", "example": "3arab (عرب)"},
        {"ar": "ء / أ / ئ", "fr": "2", "example": "so2al (سؤال)"},
        {"ar": "خ", "fr": "kh", "example": "khalid (خالد)"},
        {"ar": "غ", "fr": "gh", "example": "ghaly (غالي)"},
        {"ar": "ش", "fr": "sh", "example": "shokran (شكراً)"},
        {"ar": "ث", "fr": "th", "example": "thawra (ثورة)"},
        {"ar": "ذ", "fr": "dh", "example": "dhahab (ذهب)"},
        {"ar": "ق", "fr": "q", "example": "qalb (قلب)"},
        {"ar": "ط", "fr": "t", "example": "tariq (طريق)"},
        {"ar": "ص", "fr": "s", "example": "sabr (صبر)"},
        {"ar": "ض", "fr": "d", "example": "dahr (ظهر/ضهر)"},
        {"ar": "ظ", "fr": "z", "example": "zalem (ظالم)"},
        {"ar": "ج", "fr": "g", "example": "gamed (جامد)"},
    ]
