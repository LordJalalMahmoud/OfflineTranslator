import stanza

# احتفظ بدالة Pipeline الأصلية
_original_pipeline = stanza.Pipeline

# امنع تنزيل الموارد أثناء تهيئة Pipeline
def offline_pipeline(*args, **kwargs):
    kwargs["download_method"] = None
    return _original_pipeline(*args, **kwargs)

stanza.Pipeline = offline_pipeline

from simple_translator import translate

tests = [
    "Hello, how are you?",
    "The king is waiting for you.",
    "You played Elminster?",
]

for text in tests:
    try:
        print(f"{text} => {translate(text)}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        raise