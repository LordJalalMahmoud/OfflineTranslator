#!/usr/bin/env python3
"""
TurboTranslator: محرك ترجمة وتحويل إلى الفرانكو/العربيزي عالي الأداء.
- يعتمد على محرك CTranslate2 و SentencePiece المكتوبين بلغة C++ مباشرة.
- تجميع النصوص في دفعات (Dynamic Batching) وترتيبها حسب الطول (Length Bucketing).
- كاش ذكي (Deduplication & Caching) لتخطي تكرار الترجمة لآلاف النصوص المتشابهة.
- حفظ تلقائي للتقدم (Auto-checkpoint) مع إمكانية استئناف العمل فوراً عند التوقف.
- ضمان سلامة بنية ملف الـ JSON بدون إفساد علامات التنصيص (Valid JSON Escaping).
"""

import os
import sys
import re
import json
import time
import signal
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

# إضافة المسار الحالي للمكتبة
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from arabizi import arabic_to_arabizi

# محاولة استيراد CTranslate2 و SentencePiece
try:
    import ctranslate2
    import sentencepiece as spm
except ImportError:
    print("[ERROR] ctranslate2 or sentencepiece is not installed.")
    print("Please install them or run with the project venv:")
    print("  ../venv/bin/python3 turbo_translator.py")
    sys.exit(1)


# نمط استخراج نصوص JSON
JSON_TEXT_PATTERN = re.compile(r'("text":\s*)"((?:[^"\\]|\\.)*)"')

# الرموز الخاصة في محرك اللعبة التي لا يجوز ترجمتها
SPECIAL_GAME_TOKENS = {
    "<NO TEXT>", "<CHARNAME>", "<PRO_HESHE>", "<PRO_HIMHER>",
    "<PRO_HISHER>", "<DAYNIGHT>", "<GABBER>", "<PLAYER1>",
    "<PLAYER2>", "<PLAYER3>", "<PLAYER4>", "<PLAYER5>", "<PLAYER6>",
}


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
    """البحث التلقائي الذكي عن مسار نموذج Argos Translate المحلي (يدعم Windows و Linux)."""
    root_dir = Path(__file__).resolve().parent.parent
    local_extracted = root_dir / "models" / "en_ar"
    if (local_extracted / "model/model.bin").exists() and (local_extracted / "sentencepiece.model").exists():
        return local_extracted

    linux_path = Path.home() / ".local/share/argos-translate/packages/en_ar"
    if (linux_path / "model/model.bin").exists():
        return linux_path

    for env_var in ["LOCALAPPDATA", "APPDATA"]:
        val = os.environ.get(env_var)
        if val:
            win_path = Path(val) / "argos-translate" / "packages" / "en_ar"
            if (win_path / "model/model.bin").exists():
                return win_path

    try:
        import argostranslate.package
        packages = argostranslate.package.get_installed_packages()
        for pkg in packages:
            if getattr(pkg, "from_code", None) == "en" and getattr(pkg, "to_code", None) == "ar":
                p = Path(pkg.package_path)
                if (p / "model/model.bin").exists():
                    return p
    except Exception:
        pass

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

    raise FileNotFoundError(
        "لم يتم العثور على نموذج الترجمة (en_ar). يرجى التأكد من مسار النموذج أو وجود translate-en_ar-1_0.argosmodel"
    )


def chunk_text(text: str, max_chars: int = 400) -> List[str]:
    """تقسيم النصوص الطويلة جداً إلى جمل أصغر لتفادي تجاوز حد الـ Transformer."""
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
                chunks.append(curr)
            curr = part
    if curr.strip():
        chunks.append(curr)

    return chunks if chunks else [text]


def is_trivial_text(text: str) -> bool:
    """التحقق مما إذا كان النص فارغاً أو رمزاً لا يحتاج ترجمة عصبية."""
    stripped = text.strip()
    if not stripped or stripped in SPECIAL_GAME_TOKENS:
        return True
    # إذا كان النص لا يحتوي على أي حروف أبجدية إنجليزية (مجرد أرقام أو رموز مثل 18/00 أو ---)
    if not any(c.isalpha() for c in stripped):
        return True
    return False


class TurboTranslator:
    def __init__(
        self,
        model_dir: Path,
        engine_type: str = "nllb",
        dialect: str = "arb_Arab",
        batch_size: int = 64,
        inter_threads: int = 2,
        intra_threads: int = 2,
        cache_path: Path = None,
        mode: str = "arabizi",
    ):
        self.model_dir = model_dir
        self.engine_type = engine_type
        self.dialect = dialect
        self.batch_size = batch_size
        self.cache_path = cache_path
        self.mode = mode
        self.cache: Dict[str, str] = {}

        if self.engine_type == "nllb":
            print(f"[ENGINE] استخدام محرك الذكاء الاصطناعي Meta NLLB-200 (اللهجة: {self.dialect})...")
            from transformers import AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), src_lang="eng_Latn")
            self.translator = ctranslate2.Translator(
                str(model_dir),
                device="cpu",
                inter_threads=inter_threads,
                intra_threads=intra_threads,
                compute_type="int8",
            )
        else:
            print("[ENGINE] استخدام محرك Argos Translate الكلاسيكي السريع...")
            sp_model_path = model_dir / "sentencepiece.model"
            if not sp_model_path.exists():
                raise FileNotFoundError(f"SentencePiece model not found at {sp_model_path}")
            self.sp = spm.SentencePieceProcessor(model_file=str(sp_model_path))

            ct_model_dir = model_dir / "model" if (model_dir / "model").exists() else model_dir
            self.translator = ctranslate2.Translator(
                str(ct_model_dir),
                device="cpu",
                inter_threads=inter_threads,
                intra_threads=intra_threads,
                compute_type="int8",
            )

        # تحميل الكاش القديم إن وجد
        self.load_cache()

    def load_cache(self):
        if self.cache_path and self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                print(f"[CACHE] تم تحميل {len(self.cache):,} ترجمة جاهزة من الكاش.")
            except Exception as e:
                print(f"[CACHE WARNING] فشل تحميل الكاش ({e})، سيتم البدء من جديد.")
                self.cache = {}

    def save_cache(self):
        if self.cache_path:
            temp_cache = self.cache_path.with_suffix(".tmp")
            try:
                with open(temp_cache, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, ensure_ascii=False)
                temp_cache.replace(self.cache_path)
            except Exception as e:
                print(f"[CACHE ERROR] فشل حفظ الكاش: {e}")

    def import_from_file(self, import_path: Path, input_path: Path):
        """استيراد الترجمات السابقة من ملف مثل test.json للاستفادة منها."""
        if not import_path.exists():
            print(f"[IMPORT] الملف {import_path} غير موجود لتجاوزه.")
            return

        print(f"[IMPORT] جاري استيراد الترجمات السابقة من {import_path.name}...")
        imported_count = 0
        try:
            with open(input_path, "r", encoding="utf-8") as f_in, \
                 open(import_path, "r", encoding="utf-8") as f_imp:
                for line_in, line_imp in zip(f_in, f_imp):
                    m_in = JSON_TEXT_PATTERN.search(line_in)
                    m_imp = JSON_TEXT_PATTERN.search(line_imp)
                    if m_in and m_imp:
                        orig = m_in.group(2)
                        trans = m_imp.group(2)
                        if orig and trans and orig != trans and orig != "<NO TEXT>":
                            # فك الأسطر الجزئية إن تطابقت
                            orig_parts = orig.split("\\n")
                            trans_parts = trans.split("\\n")
                            if len(orig_parts) == len(trans_parts):
                                for o, t in zip(orig_parts, trans_parts):
                                    o_clean = o.replace('\\"', '"').replace('\\\\', '\\')
                                    t_clean = t.replace('\\"', '"').replace('\\\\', '\\')
                                    if o_clean and o_clean not in self.cache:
                                        self.cache[o_clean] = t_clean
                                        imported_count += 1
            print(f"[IMPORT] تم استيراد {imported_count:,} نص بنجاح ودمجه في الكاش!")
            self.save_cache()
        except Exception as e:
            print(f"[IMPORT WARNING] حدث خطأ أثناء الاستيراد: {e}")

    def translate_batch(self, texts: List[str]) -> List[str]:
        """ترجمة دفعة من النصوص العربية دفعة واحدة في CTranslate2."""
        if not texts:
            return []

        if self.engine_type == "nllb":
            tokens_batch = [self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(t)) for t in texts]
            results = self.translator.translate_batch(
                tokens_batch,
                target_prefix=[[self.dialect]] * len(texts),
                beam_size=1,
                max_batch_size=self.batch_size,
                batch_type="examples",
            )
            translations = []
            for r in results:
                hyp = r.hypotheses[0]
                if hyp and hyp[0] == self.dialect:
                    hyp = hyp[1:]
                sub_ids = self.tokenizer.convert_tokens_to_ids(hyp)
                arabic_str = self.tokenizer.decode(sub_ids, skip_special_tokens=True).strip()
                if self.mode == "arabic":
                    translations.append(arabic_str)
                else:
                    translations.append(arabic_to_arabizi(arabic_str))
            return translations
        else:
            # 1. ترميز بالـ SentencePiece
            tokens_batch = [self.sp.encode(t, out_type=str) for t in texts]

            # 2. الترجمة في محرك C++ CTranslate2 مع greedy search (beam_size=1) لأقصى سرعة
            results = self.translator.translate_batch(
                tokens_batch,
                beam_size=1,
                max_batch_size=self.batch_size,
                batch_type="examples",
                replace_unknowns=True,
            )

            # 3. فك الترميز والتحويل حسب النمط المطلوب (عربيزي أو عربي عادي)
            translations = []
            for r in results:
                arabic_str = self.sp.decode_pieces(r.hypotheses[0]).replace("▁", " ").strip()
                if self.mode == "arabic":
                    translations.append(arabic_str)
                else:
                    arabizi_str = arabic_to_arabizi(arabic_str)
                    translations.append(arabizi_str)

            return translations


def process_file(
    input_path: Path,
    output_path: Path,
    translator: TurboTranslator,
    batch_size: int = 128,
):
    print("=" * 65)
    print(f"🚀 بدء الترجمة الفائقة: {input_path.name} -> {output_path.name}")
    print("=" * 65)

    start_total_time = time.time()

    # خطوة 1: قراءة الملف وتحليل النصوص
    print("[1/4] قراءة الملف وتحليل النصوص المطلوبة...")
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total_lines = len(lines)
    entries_found = 0
    all_chunks_to_translate: Set[str] = set()

    for line in lines:
        match = JSON_TEXT_PATTERN.search(line)
        if match:
            entries_found += 1
            raw_text = match.group(2)
            parts = raw_text.split("\\n")
            for part in parts:
                part_clean = part.replace('\\"', '"').replace('\\\\', '\\')
                if not is_trivial_text(part_clean):
                    sub_chunks = chunk_text(part_clean)
                    for sc in sub_chunks:
                        if not is_trivial_text(sc) and sc not in translator.cache:
                            all_chunks_to_translate.add(sc)

    pending_list = list(all_chunks_to_translate)
    print(f"  • إجمالي الأسطر في الملف: {total_lines:,}")
    print(f"  • إجمالي خانات النصوص: {entries_found:,}")
    print(f"  • نصوص فريدة متبقية للترجمة: {len(pending_list):,}")
    print(f"  • نصوص متوفرة مسبقاً في الكاش: {len(translator.cache):,}")

    # خطوة 2: ترتيب النصوص حسب الطول لتحسين كفاءة المعالج (Bucketing)
    print("\n[2/4] جدولة الدفعات وترتيبها حسب الطول (Length Bucketing)...")
    pending_list.sort(key=lambda s: len(s))

    # خطوة 3: ترجمة الدفعات مع مؤشر تقدم فائق الدقة
    total_to_translate = len(pending_list)
    if total_to_translate > 0:
        print(f"\n[3/4] جاري ترجمة {total_to_translate:,} نص بدفعات سعتها {batch_size}...")

        t_start = time.time()
        last_save_time = time.time()
        processed_count = 0

        for i in range(0, total_to_translate, batch_size):
            batch = pending_list[i : i + batch_size]
            results = translator.translate_batch(batch)

            for original_str, translated_str in zip(batch, results):
                translator.cache[original_str] = translated_str

            processed_count += len(batch)
            elapsed = time.time() - t_start
            speed = processed_count / elapsed if elapsed > 0 else 0
            remaining = total_to_translate - processed_count
            eta_seconds = remaining / speed if speed > 0 else 0

            # شريط تقدم أنيق
            pct = (processed_count / total_to_translate) * 100
            eta_m, eta_s = divmod(int(eta_seconds), 60)
            elapsed_m, elapsed_s = divmod(int(elapsed), 60)

            bar_len = 25
            filled_len = int(bar_len * processed_count // total_to_translate)
            bar = "█" * filled_len + "░" * (bar_len - filled_len)

            sys.stdout.write(
                f"\r  [{bar}] {pct:5.1f}% | {processed_count:,}/{total_to_translate:,} "
                f"| {speed:4.1f} نصوص/ث | مضى: {elapsed_m:02d}:{elapsed_s:02d} | متبقي: {eta_m:02d}:{eta_s:02d}"
            )
            sys.stdout.flush()

            # حفظ الكاش دورياً كل دقيقة لضمان عدم ضياع أي تقدم
            if time.time() - last_save_time > 60:
                translator.save_cache()
                last_save_time = time.time()

        print("\n  ✓ اكتملت ترجمة جميع النصوص المطلوبة!")
        translator.save_cache()
    else:
        print("\n[3/4] جميع النصوص مترجمة مسبقاً في الكاش! تخطي مرحلة الترجمة.")

    # خطوة 4: كتابة ملف المخرجات مع الحفاظ على JSON صالح 100%
    print("\n[4/4] كتابة الملف النهائي وتنسيق JSON بشكل آمن...")
    with open(output_path, "w", encoding="utf-8") as out_f:
        for line in lines:
            match = JSON_TEXT_PATTERN.search(line)
            if match:
                raw_text = match.group(2)
                parts = raw_text.split("\\n")
                translated_parts = []

                for part in parts:
                    part_clean = part.replace('\\"', '"').replace('\\\\', '\\')
                    if is_trivial_text(part_clean):
                        translated_parts.append(part_clean)
                    else:
                        sub_chunks = chunk_text(part_clean)
                        translated_sub_chunks = []
                        for sc in sub_chunks:
                            if is_trivial_text(sc):
                                translated_sub_chunks.append(sc)
                            else:
                                translated_sub_chunks.append(translator.cache.get(sc, sc))
                        translated_parts.append("".join(translated_sub_chunks))

                rejoined = "\n".join(translated_parts)
                # json.dumps يضمن ترميز علامات التنصيص والأسطر المائلة بشكل صالح تماماً
                safe_json_value = json.dumps(rejoined, ensure_ascii=False)[1:-1]
                line = JSON_TEXT_PATTERN.sub(
                    lambda m: m.group(1) + '"' + safe_json_value + '"',
                    line
                )

            out_f.write(line)

    total_duration = time.time() - start_total_time
    m, s = divmod(int(total_duration), 60)
    print("=" * 65)
    print(f"🎉 تم الانتهاء بنجاح في {m} دقيقة و {s} ثانية!")
    print(f"📁 مسار الملف المترجم الجديد: {output_path.resolve()}")
    print("=" * 65)


def main():
    nllb_dir = find_nllb_model_dir()
    default_engine = "nllb" if nllb_dir else "argos"

    parser = argparse.ArgumentParser(description="Turbo Offline Game Translator (EN -> Arabizi or Arabic)")
    parser.add_argument("--input", "-i", type=str, default="../dialog.json", help="مسار ملف الإدخال")
    parser.add_argument("--output", "-o", type=str, default=None, help="مسار ملف الإخراج")
    parser.add_argument("--engine", "-e", type=str, choices=["nllb", "argos"], default=default_engine,
                        help=f"محرك الترجمة: nllb (عالي الجودة) أو argos (خفيف وسريع) - الافتراضي: {default_engine}")
    parser.add_argument("--dialect", "-d", type=str, choices=["arb_Arab", "arz_Arab"], default="arb_Arab",
                        help="اللهجة عند استخدام NLLB: arb_Arab (فصحى) أو arz_Arab (مصري عامية)")
    parser.add_argument("--mode", "-m", choices=["arabizi", "arabic"], default="arabizi", help="نمط الترجمة: عربيزي/فرانكو أو عربي عادي")
    parser.add_argument("--arabic", "-ar", action="store_true", help="تفعيل الترجمة للغة العربية العادية (بدون فرانكو)")
    parser.add_argument("--batch-size", "-b", type=int, default=None, help="حجم الدفعة (افتراضي: 64 لـ NLLB، و128 لـ Argos)")
    parser.add_argument("--inter-threads", type=int, default=2, help="عدد مسارات المعالجة المتزامنة (افتراضي: 2)")
    parser.add_argument("--intra-threads", type=int, default=2, help="عدد خيوط العمل للعملية الواحدة (افتراضي: 2)")
    parser.add_argument("--cache", type=str, default=None, help="مسار ملف حفظ الكاش")
    parser.add_argument("--import-from", type=str, default=None, help="استيراد ترجمات سابقة من ملف خارجي (مثل ../test.json)")
    parser.add_argument("--model-dir", type=str, default=None, help="مسار مجلد النموذج إن كان مخصصاً")

    args = parser.parse_args()

    mode = "arabic" if (args.arabic or args.mode == "arabic") else "arabizi"

    # تحديد ملفات الإخراج والكاش تلقائياً حسب النمط والمحرك إن لم يحددها المستخدم يدوياً
    if args.output is None:
        output_file = "dialog_arabic.json" if mode == "arabic" else "dialog_arabizi.json"
    else:
        output_file = args.output

    if args.cache is None:
        if args.engine == "nllb":
            cache_file = f"translation_cache_nllb_{mode}.json"
        else:
            cache_file = "translation_cache_arabic.json" if mode == "arabic" else "translation_cache.json"
    else:
        cache_file = args.cache

    input_path = Path(args.input)
    if not input_path.exists():
        # محاولة البحث في المجلد الحالي
        alt_input = Path(input_path.name)
        if alt_input.exists():
            input_path = alt_input
        else:
            print(f"[ERROR] الملف {args.input} غير موجود!")
            sys.exit(1)

    output_path = Path(output_file)
    cache_path = Path(cache_file)

    if args.engine == "nllb":
        if args.model_dir:
            model_dir = Path(args.model_dir)
        elif nllb_dir:
            model_dir = nllb_dir
        else:
            print("[ERROR] لم يتم العثور على نموذج Meta NLLB-200. يرجى تنزيله أو تحديد مساره عبر --model-dir")
            sys.exit(1)
        batch_size = args.batch_size if args.batch_size else 64
    else:
        model_dir = Path(args.model_dir) if args.model_dir else find_model_dir()
        batch_size = args.batch_size if args.batch_size else 128

    print("=" * 65)
    print(f"• المحرك المستخدم: {args.engine.upper()} {'(Meta NLLB-200)' if args.engine == 'nllb' else '(Argos Translate)'}")
    print(f"• نمط الإخراج: {'عربي عادي (Arabic)' if mode == 'arabic' else 'فرانكو / عربيزي (Arabizi)'}")
    if args.engine == "nllb":
        print(f"• اللهجة المستهدفة: {'عربي فصحى (arb_Arab)' if args.dialect == 'arb_Arab' else 'لهجة مصرية عامية (arz_Arab)'}")
    print(f"• مجلد النموذج: {model_dir}")
    print(f"• حجم الدفعة: {batch_size}")
    print(f"• ملف الإدخال: {input_path}")
    print(f"• ملف الإخراج: {output_path}")
    print(f"• ملف الكاش: {cache_path}")
    print("=" * 65)

    translator = TurboTranslator(
        model_dir=model_dir,
        engine_type=args.engine,
        dialect=args.dialect,
        batch_size=batch_size,
        inter_threads=args.inter_threads,
        intra_threads=args.intra_threads,
        cache_path=cache_path,
        mode=mode,
    )

    # معالجة إشارة الإيقاف (Ctrl+C) لحفظ الكاش بأمان
    def sigint_handler(sig, frame):
        print("\n\n[!] تم إيقاف البرنامج مؤقتاً. جاري حفظ الكاش...")
        translator.save_cache()
        print("[✓] تم حفظ الكاش بنجاح. يمكنك استئناف التشغيل في أي وقت دون ضياع أي تقدم!")
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    # استيراد ملف خارجي إن طلب المستخدم
    if args.import_from:
        import_path = Path(args.import_from)
        if not import_path.exists():
            alt_imp = Path("../") / args.import_from
            if alt_imp.exists():
                import_path = alt_imp
        translator.import_from_file(import_path, input_path)

    process_file(
        input_path=input_path,
        output_path=output_path,
        translator=translator,
        batch_size=batch_size,
    )


if __name__ == "__main__":
    main()
