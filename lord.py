
import re
from simple_translator import translate, OfflineTranslator

# إجمالي عدد المعرّفات المتوقع معالجتها
TOTAL_IDS = 103583

pattern = re.compile(r'("text":\s*)"((?:[^"\\]|\\.)*)"')


def arabic_to_arabizi_custom(
    text: str, qaf='q', ain='3', haa='7', jeem='g'
) -> str:
    base = {
        'ا': 'a', 'أ': 'a', 'إ': 'e', 'ب': 'b', 'ت': 't', 'ث': 'th',
        'ج': jeem, 'ح': haa, 'خ': 'kh', 'د': 'd', 'ذ': 'dh', 'ر': 'r',
        'ز': 'z', 'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't',
        'ظ': 'z', 'ع': ain, 'غ': 'gh', 'ف': 'f', 'ق': qaf, 'ك': 'k',
        'ل': 'l', 'م': 'm', 'ن': 'n', 'ه': 'h', 'و': 'w', 'ي': 'y',
        'ى': 'a', 'ة': 'a', 'ء': '2', 'ئ': '2', 'ؤ': '2',
    }
    return ''.join(base.get(c, c) for c in text)


def lordtranslate(text):
    text = translate(text)
    text = arabic_to_arabizi_custom(text)
    return text


def process_file(input_path, output_path, operation):
    processed_ids = 0

    with open(input_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    with open(output_path, "w", encoding="utf-8") as file:
        for line in lines:
            match = pattern.search(line)

            if match:
                processed_ids += 1

                old_text = match.group(2)
                new_text = operation(old_text)

                line = pattern.sub(
                    lambda m: m.group(1) + '"' + new_text + '"',
                    line
                )

                if TOTAL_IDS > 0:
                    percentage = min(
                        processed_ids / TOTAL_IDS * 100, 100
                    )
                    print(
                        f"\rProgress: {percentage:.2f}% "
                        f"({processed_ids}/{TOTAL_IDS})",
                        end="",
                        flush=True
                    )

            file.write(line)

    print(f"\nTranslation finished. Processed IDs: {processed_ids}")


process_file("dialog.json", "test.json", lordtranslate)
