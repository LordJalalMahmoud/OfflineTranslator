"""
محرك الترجمة الفائق الموحد لصفحة الويب (Offline Web Engine)
- يعتمد على CTranslate2 و SentencePiece بسرعة C++ الفائقة
- يدعم كلا الوضعين: عربي فصحى (Arabic) وفرانكو/عربيزي (Arabizi)
- يستفيد من أكثر من 93,000 ترجمة مخزنة في الكاش محلياً لرد فوري (< 1ms)
- تشغيل خيوط متعددة ومعالجة بالدفعات (Batching) لملفات الألعاب والنصوص
- يعمل بدون إنترنت 100% وبدون أي اعتماديات خارجية
"""

import os
import sys
import re
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

# استيراد محول الفرانكو
from arabizi import arabic_to_arabizi, get_arabizi_dictionary

# استيراد CTranslate2 و SentencePiece
try:
    import ctranslate2
    import sentencepiece as spm
except ImportError as e:
    raise ImportError(f"Missing required library: {e}. Run using the project venv: ../venv/bin/python3")

# الرموز الخاصة في محركات الألعاب التي لا تُترجم
SPECIAL_GAME_TOKENS = {
    "<NO TEXT>", "<CHARNAME>", "<PRO_HESHE>", "<PRO_HIMHER>",
    "<PRO_HISHER>", "<DAYNIGHT>", "<GABBER>", "<PLAYER1>",
    "<PLAYER2>", "<PLAYER3>", "<PLAYER4>", "<PLAYER5>", "<PLAYER6>",
}

# نمط استخراج نصوص JSON
JSON_TEXT_PATTERN = re.compile(r'("text":\s*)"((?:[^"\\]|\\.)*)"')


def find_nllb_model_dir() -> Optional[Path]:
    """البحث التلقائي عن مسار نموذج Meta NLLB-200 المحلي."""
    root_dir = Path(__file__).resolve().parent.parent
    candidates = [
        root_dir / "models" / "nllb-600m-ct2",
        root_dir.parent / "nllb_translator" / "models" / "nllb-600m-ct2",
        Path.home() / "nllb_translator" / "models" / "nllb-600m-ct2",
    ]
    for c in candidates:
        if (c / "model.bin").exists():
            return c
    return None


def find_model_dir() -> Path:
    """البحث التلقائي الذكي عن مسار حزمة النموذج Argos Translate (يدعم Windows و Linux)."""
    # 1. البحث في مجلد المشروع المحلي models/en_ar إن وجد
    root_dir = Path(__file__).resolve().parent.parent
    local_extracted = root_dir / "models" / "en_ar"
    if (local_extracted / "model/model.bin").exists() and (local_extracted / "sentencepiece.model").exists():
        return local_extracted

    # 2. المسار الافتراضي لـ Argos في نظام لينكس
    linux_path = Path.home() / ".local/share/argos-translate/packages/en_ar"
    if (linux_path / "model/model.bin").exists() and (linux_path / "sentencepiece.model").exists():
        return linux_path

    # 3. المسار الافتراضي لـ Argos في نظام ويندوز (Windows APPDATA)
    for env_var in ["LOCALAPPDATA", "APPDATA"]:
        val = os.environ.get(env_var)
        if val:
            win_path = Path(val) / "argos-translate" / "packages" / "en_ar"
            if (win_path / "model/model.bin").exists() and (win_path / "sentencepiece.model").exists():
                return win_path

    # 4. البحث عبر مكتبة argostranslate إن وجدت
    try:
        import argostranslate.package
        packages = argostranslate.package.get_installed_packages()
        for pkg in packages:
            if getattr(pkg, "from_code", None) == "en" and getattr(pkg, "to_code", None) == "ar":
                p = Path(pkg.package_path)
                if (p / "model/model.bin").exists() and (p / "sentencepiece.model").exists():
                    return p
    except Exception:
        pass

    # 5. إذا وجد ملف translate-en_ar-1_0.argosmodel، فك ضغطه تلقائياً في models/en_ar
    model_archive = root_dir / "translate-en_ar-1_0.argosmodel"
    if model_archive.exists():
        try:
            import zipfile
            print(f"[INFO] جاري فك ضغط حزمة النموذج {model_archive.name} محلياً لأول مرة...")
            extract_dest = root_dir / "models"
            extract_dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(model_archive), "r") as z:
                z.extractall(str(extract_dest))
            if (local_extracted / "model/model.bin").exists():
                print(f"[INFO] تم استخراج النموذج بنجاح في: {local_extracted}")
                return local_extracted
        except Exception as e:
            print(f"[WARNING] فشل فك الضغط التلقائي: {e}")

    raise FileNotFoundError("لم يتم العثور على نموذج الترجمة (en_ar).")


def is_trivial_text(text: str) -> bool:
    """التحقق مما إذا كان النص رمزاً أو خالياً من الحروف."""
    stripped = text.strip()
    if not stripped or stripped in SPECIAL_GAME_TOKENS:
        return True
    if not any(c.isalpha() for c in stripped):
        return True
    return False


def chunk_text(text: str, max_chars: int = 400) -> List[str]:
    """تقسيم النصوص الطويلة لتفادي تجاوز سعة النموذج العصبي مع الحفاظ على الترقيم."""
    if len(text) <= max_chars:
        return [text]

    splits = re.split(r'([.?!;:]\s+)', text)
    chunks = []
    curr = ""
    for i in range(0, len(splits), 2):
        s = splits[i]
        delim = splits[i + 1] if i + 1 < len(splits) else ""
        part = s + delim
        if len(curr) + len(part) <= max_chars:
            curr += part
        else:
            if curr.strip():
                chunks.append(curr.strip())
            curr = part
    if curr.strip():
        chunks.append(curr.strip())

    return chunks if chunks else [text]


class WebTranslationEngine:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.model_dir = find_model_dir()
        
        # مسارات الكاش
        self.arabic_cache_path = self.project_root / "fast_translator_arabic" / "translation_cache.json"
        self.arabizi_cache_path = self.project_root / "fast_translator" / "translation_cache.json"
        self.nllb_arabic_cache_path = self.project_root / "fast_translator_arabic" / "translation_cache_nllb.json"
        self.nllb_arabizi_cache_path = self.project_root / "fast_translator" / "translation_cache_nllb.json"
        self.nllb_egypt_cache_path = self.project_root / "fast_translator_arabic" / "translation_cache_nllb_egypt.json"
        self.nllb_egypt_arabizi_cache_path = self.project_root / "fast_translator" / "translation_cache_nllb_egypt.json"

        # القواميس المحملة في الذاكرة
        self.arabic_cache: Dict[str, str] = {}
        self.arabizi_cache: Dict[str, str] = {}
        self.nllb_arb_cache: Dict[str, str] = {}
        self.nllb_arb_franco_cache: Dict[str, str] = {}
        self.nllb_arz_cache: Dict[str, str] = {}
        self.nllb_arz_franco_cache: Dict[str, str] = {}
        self.cache_lock = threading.Lock()
        
        # مؤشرات المهام الجارية
        self.active_tasks: Dict[str, dict] = {}
        self.task_lock = threading.Lock()

        # 1. تهيئة SentencePiece
        sp_model_path = self.model_dir / "sentencepiece.model"
        if not sp_model_path.exists():
            raise FileNotFoundError(f"SentencePiece model not found at {sp_model_path}")
        self.sp = spm.SentencePieceProcessor(model_file=str(sp_model_path))

        # 2. تهيئة محرك CTranslate2 C++
        ct_model_dir = self.model_dir / "model"
        if not ct_model_dir.exists():
            raise FileNotFoundError(f"CTranslate2 model dir not found at {ct_model_dir}")

        self.translator = ctranslate2.Translator(
            str(ct_model_dir),
            device="cpu",
            inter_threads=2,
            intra_threads=2,
            compute_type="int8",
        )
        self.translator_lock = threading.Lock()

        # 3. تهيئة Meta NLLB-200 إن كان متوفراً
        self.nllb_dir = find_nllb_model_dir()
        self.nllb_tokenizer = None
        self.nllb_translator = None
        self._init_nllb()

        # 4. تحميل الكاش
        self.load_caches()

    def _init_nllb(self):
        """تهيئة معالج ونموذج Meta NLLB-200 في خلفية المحرك."""
        if self.nllb_dir and (self.nllb_dir / "model.bin").exists():
            try:
                from transformers import AutoTokenizer
                print(f"[NLLB] تهيئة نموذج Meta NLLB-200 من: {self.nllb_dir}")
                self.nllb_tokenizer = AutoTokenizer.from_pretrained(str(self.nllb_dir), src_lang="eng_Latn")
                self.nllb_translator = ctranslate2.Translator(
                    str(self.nllb_dir),
                    device="cpu",
                    inter_threads=2,
                    intra_threads=2,
                    compute_type="int8",
                )
                print("[NLLB] تم دمج نموذج Meta NLLB-200 بنجاح في محرك الويب!")
            except Exception as e:
                print(f"[NLLB WARNING] فشل تحميل NLLB: {e}")

    def _load_single_cache(self, path: Path) -> Dict[str, str]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[CACHE WARNING] Error reading {path.name}: {e}")
        return {}

    def _save_single_cache(self, path: Path, data: Dict[str, str]):
        if not data:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            tmp.replace(path)
        except Exception as e:
            print(f"[CACHE SAVE ERROR] {path.name}: {e}")

    def load_caches(self):
        """تحميل الكاش الخاص بالعربية والفرانكو ونماذج NLLB من الأقراص إلى الذاكرة."""
        with self.cache_lock:
            self.arabic_cache = self._load_single_cache(self.arabic_cache_path)
            self.arabizi_cache = self._load_single_cache(self.arabizi_cache_path)
            self.nllb_arb_cache = self._load_single_cache(self.nllb_arabic_cache_path)
            self.nllb_arb_franco_cache = self._load_single_cache(self.nllb_arabizi_cache_path)
            self.nllb_arz_cache = self._load_single_cache(self.nllb_egypt_cache_path)
            self.nllb_arz_franco_cache = self._load_single_cache(self.nllb_egypt_arabizi_cache_path)

    def save_caches(self):
        """حفظ الكاش على القرص بأمان."""
        with self.cache_lock:
            self._save_single_cache(self.arabic_cache_path, self.arabic_cache)
            self._save_single_cache(self.arabizi_cache_path, self.arabizi_cache)
            self._save_single_cache(self.nllb_arabic_cache_path, self.nllb_arb_cache)
            self._save_single_cache(self.nllb_arabizi_cache_path, self.nllb_arb_franco_cache)
            self._save_single_cache(self.nllb_egypt_cache_path, self.nllb_arz_cache)
            self._save_single_cache(self.nllb_egypt_arabizi_cache_path, self.nllb_arz_franco_cache)

    def get_cache_pair(self, engine_type: str = "nllb", dialect: str = "arb_Arab") -> Tuple[Dict[str, str], Dict[str, str]]:
        """الحصول على زوج الكاش المناسب (عربي، فرانكو) بحسب المحرك واللهجة."""
        if engine_type == "nllb" and self.nllb_translator:
            if dialect == "arz_Arab":
                return self.nllb_arz_cache, self.nllb_arz_franco_cache
            return self.nllb_arb_cache, self.nllb_arb_franco_cache
        return self.arabic_cache, self.arabizi_cache

    def translate_raw_batch_model(
        self,
        texts: List[str],
        engine_type: str = "nllb",
        dialect: str = "arb_Arab"
    ) -> List[str]:
        """ترجمة دفعة من النصوص عبر محرك الذكاء الاصطناعي المحدد وتوليد النص العربي."""
        if not texts:
            return []

        # 1. إذا كان المحرك NLLB ونموذجه متوفر
        if engine_type == "nllb" and self.nllb_translator and self.nllb_tokenizer:
            flat_subtexts = []
            chunk_counts = []
            for t in texts:
                chunks = chunk_text(t, max_chars=350)
                flat_subtexts.extend(chunks)
                chunk_counts.append(len(chunks))

            tokens_batch = [
                self.nllb_tokenizer.convert_ids_to_tokens(self.nllb_tokenizer.encode(st))
                for st in flat_subtexts
            ]
            target_prefix = [[dialect]] * len(flat_subtexts)

            with self.translator_lock:
                results = self.nllb_translator.translate_batch(
                    tokens_batch,
                    target_prefix=target_prefix,
                    beam_size=1,
                    max_batch_size=64,
                    batch_type="examples",
                    replace_unknowns=True,
                )

            sub_translations = []
            for r in results:
                tokens = r.hypotheses[0]
                if tokens and tokens[0] == dialect:
                    tokens = tokens[1:]
                token_ids = self.nllb_tokenizer.convert_tokens_to_ids(tokens)
                ar_text = self.nllb_tokenizer.decode(token_ids, skip_special_tokens=True).strip()
                sub_translations.append(ar_text)

            translations = []
            idx = 0
            for count in chunk_counts:
                joined = " ".join(sub_translations[idx : idx + count])
                translations.append(joined.strip())
                idx += count

            return translations

        # 2. المحرك الكلاسيكي Argos Translate
        tokens_batch = [self.sp.encode(t, out_type=str) for t in texts]

        with self.translator_lock:
            results = self.translator.translate_batch(
                tokens_batch,
                beam_size=1,
                max_batch_size=128,
                batch_type="examples",
                replace_unknowns=True,
            )

        translations = []
        for r in results:
            ar_text = self.sp.decode_pieces(r.hypotheses[0]).replace("▁", " ").strip()
            translations.append(ar_text)

        return translations

    def translate_single(
        self,
        text: str,
        mode: str = "dual",
        engine_type: str = "nllb",
        dialect: str = "arb_Arab"
    ) -> dict:
        """
        ترجمة نص واحد فوري (سواء جملة واحدة أو نص متعدد الأسطر).
        الأنماط:
        - "arabic": عربي فقط
        - "arabizi": فرانكو/عربيزي فقط
        - "dual": يعيد العربي والفرانكو معاً
        المحركات:
        - "nllb": نموذج Meta NLLB-200 عالي الجودة
        - "argos": نموذج Argos Translate فائق السرعة
        اللهجة:
        - "arb_Arab": فصحى
        - "arz_Arab": مصري عامية
        """
        start_time = time.perf_counter()
        clean_text = text.strip()

        # ضبط المحرك الفعلي
        if engine_type == "nllb" and not self.nllb_translator:
            engine_type = "argos"

        active_ar_cache, active_fr_cache = self.get_cache_pair(engine_type, dialect)

        if not clean_text:
            return {
                "text": text,
                "arabic": "",
                "arabizi": "",
                "source": "empty",
                "engine": engine_type,
                "dialect": dialect,
                "elapsed_ms": 0.0,
            }

        if is_trivial_text(clean_text):
            return {
                "text": text,
                "arabic": clean_text,
                "arabizi": clean_text,
                "source": "passthrough",
                "engine": engine_type,
                "dialect": dialect,
                "elapsed_ms": 0.1,
            }

        # فحص وجود النص بالكامل في الكاش مباشرة
        with self.cache_lock:
            cached_ar = active_ar_cache.get(clean_text)
            cached_fr = active_fr_cache.get(clean_text)

        if cached_ar and cached_fr:
            elapsed = (time.perf_counter() - start_time) * 1000
            return {
                "text": text,
                "arabic": cached_ar,
                "arabizi": cached_fr,
                "source": "cache",
                "engine": engine_type,
                "dialect": dialect,
                "elapsed_ms": round(elapsed, 2),
            }

        if cached_ar and not cached_fr:
            fr_val = arabic_to_arabizi(cached_ar)
            with self.cache_lock:
                active_fr_cache[clean_text] = fr_val
            elapsed = (time.perf_counter() - start_time) * 1000
            return {
                "text": text,
                "arabic": cached_ar,
                "arabizi": fr_val,
                "source": "cache",
                "engine": engine_type,
                "dialect": dialect,
                "elapsed_ms": round(elapsed, 2),
            }

        # في حال كان نصاً طويلاً أو يحتوي على أسطر متعددة، نقسمه لأسطر
        lines = text.split("\n")
        translated_ar_lines = []
        source_type = "model"

        # تجميع الأسطر غير الموجودة في الكاش للترجمة بالدفعة
        missing_to_translate = []
        line_map = []  # يحفظ نوع كل سطر (مترجم مسبقاً أو يحتاج ترجمة)

        with self.cache_lock:
            for l in lines:
                l_strip = l.strip()
                if not l_strip or is_trivial_text(l_strip):
                    line_map.append(("trivial", l_strip))
                elif l_strip in active_ar_cache:
                    line_map.append(("cache", active_ar_cache[l_strip]))
                else:
                    line_map.append(("need_translation", l_strip))
                    missing_to_translate.append(l_strip)

        # ترجمة الأسطر الناقصة بالدفعة
        new_translations = {}
        if missing_to_translate:
            unique_missing = list(dict.fromkeys(missing_to_translate))
            results = self.translate_raw_batch_model(
                unique_missing,
                engine_type=engine_type,
                dialect=dialect
            )
            for orig, ar_res in zip(unique_missing, results):
                new_translations[orig] = ar_res
                # إضافة للكاش
                with self.cache_lock:
                    active_ar_cache[orig] = ar_res
                    active_fr_cache[orig] = arabic_to_arabizi(ar_res)
        else:
            source_type = "cache"

        # تجميع الناتج النهائي
        final_ar_lines = []
        for kind, val in line_map:
            if kind == "trivial":
                final_ar_lines.append(val)
            elif kind == "cache":
                final_ar_lines.append(val)
            elif kind == "need_translation":
                final_ar_lines.append(new_translations.get(val, val))

        final_ar = "\n".join(final_ar_lines)
        final_fr = arabic_to_arabizi(final_ar)

        # إذا كانت جملة واحدة نقوم بتخزينها بالكامل
        if len(lines) == 1 and clean_text not in active_ar_cache:
            with self.cache_lock:
                active_ar_cache[clean_text] = final_ar
                active_fr_cache[clean_text] = final_fr

        elapsed = (time.perf_counter() - start_time) * 1000
        return {
            "text": text,
            "arabic": final_ar,
            "arabizi": final_fr,
            "source": source_type,
            "engine": engine_type,
            "dialect": dialect,
            "elapsed_ms": round(elapsed, 2),
        }

    def search_cache(self, query: str, limit: int = 50) -> List[dict]:
        """البحث في الكاش المخزن لعرض النتائج الفورية للمستخدم عبر كل النماذج."""
        q = query.strip().lower()
        if not q:
            return []

        results = []
        with self.cache_lock:
            count = 0
            seen_en = set()

            # فحص كاش Argos وكاش NLLB معاً
            cache_sources = [
                ("Argos", self.arabic_cache, self.arabizi_cache),
                ("NLLB-Fusha", self.nllb_arb_cache, self.nllb_arb_franco_cache),
                ("NLLB-Egypt", self.nllb_arz_cache, self.nllb_arz_franco_cache),
            ]

            for tag, ar_dict, fr_dict in cache_sources:
                for en, ar in ar_dict.items():
                    if en in seen_en:
                        continue
                    if q in en.lower() or q in ar:
                        fr = fr_dict.get(en, arabic_to_arabizi(ar))
                        results.append({"en": en, "ar": ar, "fr": fr, "model": tag})
                        seen_en.add(en)
                        count += 1
                        if count >= limit:
                            return results

        return results

    def get_stats(self) -> dict:
        """إرجاع إحصائيات المحرك والكاش."""
        with self.cache_lock:
            ar_count = len(self.arabic_cache)
            fr_count = len(self.arabizi_cache)
            nllb_count = len(self.nllb_arb_cache) + len(self.nllb_arz_cache)

        return {
            "arabic_cached_entries": ar_count,
            "arabizi_cached_entries": fr_count,
            "nllb_cached_entries": nllb_count,
            "argos_available": self.translator is not None,
            "nllb_available": self.nllb_translator is not None,
            "default_engine": "nllb" if self.nllb_translator is not None else "argos",
            "model_path": str(self.model_dir),
            "nllb_model_path": str(self.nllb_dir) if self.nllb_dir else None,
            "device": "CPU (int8 quantized)",
            "batch_support": True,
            "offline_ready": True,
            "model_engine": "Meta NLLB-200 & Argos (CTranslate2 C++)",
        }

    def start_file_translation(
        self,
        task_id: str,
        input_content: Optional[str] = None,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
        mode: str = "arabic",
        engine_type: str = "nllb",
        dialect: str = "arb_Arab",
        batch_size: int = 64,
    ):
        """بدء عملية ترجمة ملف ضخم في خلفية النظام مع تحديث حالة التقدم المباشر."""
        with self.task_lock:
            self.active_tasks[task_id] = {
                "task_id": task_id,
                "status": "running",
                "engine": engine_type,
                "dialect": dialect,
                "mode": mode,
                "progress_percent": 0.0,
                "total_lines": 0,
                "processed_lines": 0,
                "cache_hits": 0,
                "newly_translated": 0,
                "speed_lps": 0.0,
                "eta_seconds": 0,
                "current_snippet": "بدء قراءة الملف...",
                "output_path": output_path or "",
                "output_content": None,
                "error": None,
                "stop_requested": False,
            }

        thread = threading.Thread(
            target=self._run_file_translation_thread,
            args=(task_id, input_content, input_path, output_path, mode, engine_type, dialect, batch_size),
            daemon=True,
        )
        thread.start()

    def get_task_progress(self, task_id: str) -> Optional[dict]:
        with self.task_lock:
            return self.active_tasks.get(task_id)

    def cancel_task(self, task_id: str):
        with self.task_lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["stop_requested"] = True

    def _run_file_translation_thread(
        self,
        task_id: str,
        input_content: Optional[str],
        input_path: Optional[str],
        output_path: Optional[str],
        mode: str,
        engine_type: str,
        dialect: str,
        batch_size: int,
    ):
        task = self.active_tasks[task_id]
        start_time = time.time()

        try:
            # التحقق من توفر NLLB
            if engine_type == "nllb" and not self.nllb_translator:
                engine_type = "argos"
                task["engine"] = "argos"

            active_ar_cache, active_fr_cache = self.get_cache_pair(engine_type, dialect)

            # 1. قراءة أسطر الملف
            if input_content is not None:
                lines = input_content.splitlines(keepends=True)
            elif input_path and os.path.exists(input_path):
                with open(input_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            else:
                raise ValueError("الملف المحدد غير موجود أو غير صالح.")

            total_lines = len(lines)
            task["total_lines"] = total_lines

            # 2. فحص الأسطر واستخراج ما يحتاج لترجمة
            needed_texts = []
            line_records = []

            for i, line in enumerate(lines):
                if task["stop_requested"]:
                    task["status"] = "cancelled"
                    return

                m = JSON_TEXT_PATTERN.search(line)
                if m:
                    text_content = m.group(2)
                    clean_text = text_content.replace('\\"', '"').replace('\\\\', '\\')
                    
                    if is_trivial_text(clean_text):
                        line_records.append((i, "trivial", line, text_content))
                    else:
                        with self.cache_lock:
                            cached = active_ar_cache.get(clean_text) if mode == "arabic" else active_fr_cache.get(clean_text)
                        
                        if cached:
                            task["cache_hits"] += 1
                            line_records.append((i, "cached", line, cached))
                        else:
                            line_records.append((i, "need", line, clean_text))
                            needed_texts.append(clean_text)
                else:
                    line_records.append((i, "passthrough", line, None))

            # 3. ترجمة النصوص الناقصة عبر CTranslate2 بالدفعات
            unique_needed = list(dict.fromkeys(needed_texts))
            translated_dict = {}

            # ضبط حجم الدفعة المناسب
            if not batch_size or batch_size <= 0:
                batch_size = 64 if engine_type == "nllb" else 128

            total_needed = len(unique_needed)
            for b_idx in range(0, total_needed, batch_size):
                if task["stop_requested"]:
                    task["status"] = "cancelled"
                    return

                batch = unique_needed[b_idx : b_idx + batch_size]
                results = self.translate_raw_batch_model(
                    batch,
                    engine_type=engine_type,
                    dialect=dialect
                )

                for orig, ar_res in zip(batch, results):
                    if mode == "arabic":
                        final_res = ar_res
                    else:
                        final_res = arabic_to_arabizi(ar_res)

                    translated_dict[orig] = final_res
                    with self.cache_lock:
                        active_ar_cache[orig] = ar_res
                        active_fr_cache[orig] = arabic_to_arabizi(ar_res)

                task["newly_translated"] += len(batch)
                processed = task["cache_hits"] + task["newly_translated"]
                now = time.time()
                elapsed = max(now - start_time, 0.001)
                task["speed_lps"] = round(processed / elapsed, 1)
                
                # حساب النسبة
                pct = (processed / max(len(needed_texts) + task["cache_hits"], 1)) * 95
                task["progress_percent"] = round(min(pct, 95.0), 1)
                if batch:
                    task["current_snippet"] = f"{batch[-1][:35]}... -> {results[-1][:35]}..."

            # 4. بناء الأسطر الناتجة مع حماية علامات التنصيص
            task["current_snippet"] = "جاري تجميع الملف وحفظه..."
            output_lines = []

            for i, kind, original_line, data in line_records:
                if kind in ("trivial", "passthrough"):
                    output_lines.append(original_line)
                elif kind == "cached":
                    esc = data.replace('\\', '\\\\').replace('"', '\\"')
                    new_line = JSON_TEXT_PATTERN.sub(r'\1"' + esc + r'"', original_line)
                    output_lines.append(new_line)
                elif kind == "need":
                    res = translated_dict.get(data, data)
                    esc = res.replace('\\', '\\\\').replace('"', '\\"')
                    new_line = JSON_TEXT_PATTERN.sub(r'\1"' + esc + r'"', original_line)
                    output_lines.append(new_line)

            output_text = "".join(output_lines)

            # إذا كان هناك مسار حفظ، احفظه على القرص
            if output_path:
                out_p = Path(output_path)
                out_p.parent.mkdir(parents=True, exist_ok=True)
                with open(out_p, "w", encoding="utf-8") as f:
                    f.write(output_text)

            task["output_content"] = output_text
            task["progress_percent"] = 100.0
            task["status"] = "completed"
            task["current_snippet"] = "اكتملت الترجمة بنجاح!"

            # حفظ الكاش
            self.save_caches()

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            print(f"[TASK ERROR] {e}")
