"""
واجهة المستخدم الرسومية لبرنامج الترجمة المحلي بالكامل (Tkinter)
Offline English -> Arabic Translator GUI
"""

import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    BIDI_SUPPORT = True
except ImportError:
    BIDI_SUPPORT = False

from translator import (
    is_model_installed,
    get_model_info,
    translate_text,
    ModelNotFoundError,
    ArgosNotInstalledError,
)


class OfflineTranslatorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("مترجم بدون إنترنت | English → Arabic Offline Translator")
        self.root.geometry("860x720")
        self.root.minsize(680, 560)

        # طابور الرسائل لتواصل آمن 100% بين خيوط المعالجة وTkinter (Thread-Safe Queue)
        self.msg_queue = queue.Queue()

        # المتغيرات وحالة البرنامج
        self.is_translating = False
        self.raw_arabic_text = ""  # النص العربي الأصلي غير المعدل للنسخ النظيف
        self.model_ready = False

        # إعداد النمط والمظهر
        self._setup_styles()

        # بناء عناصر الواجهة
        self._build_header()
        self._build_input_section()
        self._build_controls_section()
        self._build_output_section()
        self._build_footer_status()

        # اختصارات لوحة المفاتيح
        self.root.bind("<Control-Return>", lambda event: self.start_translation())
        self.root.bind("<Control-KP_Enter>", lambda event: self.start_translation())

        # ربط الحدث المخصص لمعالجة الرسائل فور وصولها
        self.root.bind("<<MessageReceived>>", lambda event: self._process_queue())

        # جدولة فحص دوري للطابور أيضاً لضمان التقاط الرسائل
        self.root.after(50, self._poll_queue_timer)

        # التحقق من حالة النموذج بعد ظهور الواجهة
        self.root.after(100, self.check_model_status)

    def _setup_styles(self):
        """تهيئة الألوان والخطوط وأنماط ttk."""
        self.bg_color = "#f4f6f8"
        self.card_bg = "#ffffff"
        self.border_color = "#e2e8f0"
        self.text_color = "#1e293b"
        self.primary_color = "#2563eb"
        self.primary_hover = "#1d4ed8"
        self.success_color = "#059669"
        self.danger_color = "#dc2626"
        self.warning_bg = "#fef3c7"
        self.warning_text = "#92400e"

        self.root.configure(bg=self.bg_color)

        style = ttk.Style()
        style.theme_use("clam")

        # تخصيص أزرار ttk
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 11, "bold"),
            background=self.primary_color,
            foreground="#ffffff",
            padding=8,
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", self.primary_hover), ("disabled", "#94a3b8")],
            foreground=[("disabled", "#f1f5f9")],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            background="#64748b",
            foreground="#ffffff",
            padding=6,
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#475569"), ("disabled", "#cbd5e1")],
        )

        style.configure(
            "Success.TButton",
            font=("Segoe UI", 10),
            background=self.success_color,
            foreground="#ffffff",
            padding=6,
            borderwidth=0,
        )
        style.map(
            "Success.TButton",
            background=[("active", "#047857"), ("disabled", "#cbd5e1")],
        )

        style.configure("TProgressbar", thickness=6)

    def _build_header(self):
        """شريط العنوان وحالة النموذج في الأعلى."""
        header_frame = tk.Frame(self.root, bg=self.card_bg, padx=16, pady=12, bd=1, relief="solid")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        title_label = tk.Label(
            header_frame,
            text="🌐 المترجم المحلي | Offline Neural Translator",
            font=("Segoe UI", 13, "bold"),
            bg=self.card_bg,
            fg="#0f172a",
        )
        title_label.pack(side="left")

        self.status_badge = tk.Label(
            header_frame,
            text="⏳ جارٍ فحص النموذج...",
            font=("Segoe UI", 10, "bold"),
            bg="#f1f5f9",
            fg="#64748b",
            padx=10,
            pady=4,
        )
        self.status_badge.pack(side="right")

        # إطار رسالة التحذير في حال عدم تثبيت النموذج
        self.warning_banner = tk.Frame(
            self.root,
            bg=self.warning_bg,
            padx=14,
            pady=10,
            highlightbackground="#f59e0b",
            highlightthickness=1,
        )
        self.warning_label = tk.Label(
            self.warning_banner,
            text="",
            font=("Segoe UI", 10),
            bg=self.warning_bg,
            fg=self.warning_text,
            justify="right",
            wraplength=780,
        )
        self.warning_label.pack(side="right", fill="x", expand=True)

    def _build_input_section(self):
        """قسم إدخال النص الإنجليزي."""
        input_container = tk.Frame(self.root, bg=self.bg_color)
        input_container.pack(fill="both", expand=True, padx=16, pady=6)

        header_row = tk.Frame(input_container, bg=self.bg_color)
        header_row.pack(fill="x", pady=(0, 4))

        lbl = tk.Label(
            header_row,
            text="النص الإنجليزي (English Input):",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_color,
            fg="#334155",
        )
        lbl.pack(side="left")

        self.input_count_label = tk.Label(
            header_row,
            text="0 أحرف",
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#64748b",
        )
        self.input_count_label.pack(side="right")

        # مربع النص وشريط التمرير
        box_frame = tk.Frame(input_container, bg=self.card_bg, bd=1, relief="solid")
        box_frame.pack(fill="both", expand=True)

        self.input_scroll = tk.Scrollbar(box_frame)
        self.input_scroll.pack(side="right", fill="y")

        self.input_text = tk.Text(
            box_frame,
            wrap="word",
            font=("DejaVu Sans", 11),
            bg=self.card_bg,
            fg=self.text_color,
            bd=0,
            padx=10,
            pady=10,
            yscrollcommand=self.input_scroll.set,
            undo=True,
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        self.input_scroll.config(command=self.input_text.yview)

        self.input_text.bind("<KeyRelease>", self._on_input_changed)

    def _build_controls_section(self):
        """شريط الأزرار ومؤشر التقدم."""
        controls_frame = tk.Frame(self.root, bg=self.bg_color, padx=16, pady=6)
        controls_frame.pack(fill="x")

        # زر الترجمة الرئيسي
        self.translate_btn = ttk.Button(
            controls_frame,
            text="ترجمة ➔ Translate",
            style="Primary.TButton",
            command=self.start_translation,
            cursor="hand2",
        )
        self.translate_btn.pack(side="left", padx=(0, 8))

        # زر مسح النصوص
        self.clear_btn = ttk.Button(
            controls_frame,
            text="مسح ✕ Clear",
            style="Secondary.TButton",
            command=self.clear_all,
            cursor="hand2",
        )
        self.clear_btn.pack(side="left", padx=(0, 8))

        # زر نسخ الترجمة
        self.copy_btn = ttk.Button(
            controls_frame,
            text="نسخ الترجمة 📋 Copy",
            style="Success.TButton",
            command=self.copy_translation,
            cursor="hand2",
        )
        self.copy_btn.pack(side="left", padx=(0, 8))

        # تلميح الاختصار
        hint_label = tk.Label(
            controls_frame,
            text="(اختصار: Ctrl + Enter)",
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#64748b",
        )
        hint_label.pack(side="right")

        # شريط التقدم الدقيق
        self.progress_bar = ttk.Progressbar(
            self.root,
            style="TProgressbar",
            mode="determinate",
        )

    def _build_output_section(self):
        """قسم عرض النص العربي المترجم."""
        output_container = tk.Frame(self.root, bg=self.bg_color)
        output_container.pack(fill="both", expand=True, padx=16, pady=6)

        header_row = tk.Frame(output_container, bg=self.bg_color)
        header_row.pack(fill="x", pady=(0, 4))

        lbl = tk.Label(
            header_row,
            text="الترجمة باللغة العربية (Arabic Translation):",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_color,
            fg="#334155",
        )
        lbl.pack(side="right")

        self.output_count_label = tk.Label(
            header_row,
            text="0 أحرف",
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#64748b",
        )
        self.output_count_label.pack(side="left")

        # مربع النص وشريط التمرير
        box_frame = tk.Frame(output_container, bg=self.card_bg, bd=1, relief="solid")
        box_frame.pack(fill="both", expand=True)

        self.output_scroll = tk.Scrollbar(box_frame)
        self.output_scroll.pack(side="left", fill="y")

        self.output_text = tk.Text(
            box_frame,
            wrap="word",
            font=("DejaVu Sans", 11),
            bg=self.card_bg,
            fg=self.text_color,
            bd=0,
            padx=10,
            pady=10,
            yscrollcommand=self.output_scroll.set,
        )
        self.output_text.pack(side="right", fill="both", expand=True)
        self.output_scroll.config(command=self.output_text.yview)

        # دعم محاذاة النص لليمين (RTL alignment)
        self.output_text.tag_configure("rtl", justify="right")

    def _build_footer_status(self):
        """شريط الحالة السفلي."""
        footer_frame = tk.Frame(self.root, bg="#e2e8f0", padx=16, pady=6)
        footer_frame.pack(fill="x", side="bottom")

        self.footer_status = tk.Label(
            footer_frame,
            text="جاهز",
            font=("Segoe UI", 9),
            bg="#e2e8f0",
            fg="#475569",
        )
        self.footer_status.pack(side="right")

        self.offline_mode_label = tk.Label(
            footer_frame,
            text="🔒 ترجمة محلية بالكامل (بدون إنترنت)",
            font=("Segoe UI", 9),
            bg="#e2e8f0",
            fg="#059669",
        )
        self.offline_mode_label.pack(side="left")

    def _send_to_queue(self, item: tuple):
        """إرسال رسالة بأمان إلى طابور الرسائل وتنبيه حلقة الأحداث فوراً."""
        self.msg_queue.put(item)
        try:
            self.root.event_generate("<<MessageReceived>>", when="tail")
        except Exception:
            pass

    def _poll_queue_timer(self):
        """فحص دوري لطابور الرسائل."""
        self._process_queue()
        self.root.after(50, self._poll_queue_timer)

    def _process_queue(self):
        """معالجة كافة الرسائل المنتظرة في الطابور."""
        try:
            while True:
                item = self.msg_queue.get_nowait()
                msg_type = item[0]

                if msg_type == "progress":
                    _, percent, message = item
                    self._update_progress_ui(percent, message)
                elif msg_type == "success":
                    _, translated = item
                    self._on_translation_success(translated)
                elif msg_type == "error":
                    _, error_msg, is_model_err = item
                    self._on_translation_error(error_msg, is_model_err)

                self.msg_queue.task_done()
        except queue.Empty:
            pass

    def check_model_status(self):
        """التحقق من جاهزية نموذج الترجمة وعرض الرسائل المناسبة."""
        installed = is_model_installed("en", "ar")
        self.model_ready = installed

        if installed:
            info = get_model_info("en", "ar")
            version_str = f" v{info['package_version']}" if info else ""
            self.status_badge.config(
                text=f"🟢 النموذج مثبت محلياً{version_str}",
                bg="#dcfce7",
                fg="#15803d",
            )
            self.warning_banner.pack_forget()
            self.footer_status.config(text="النموذج جاهز للترجمة الفورية محلياً.")
        else:
            self.status_badge.config(
                text="❌ النموذج غير مثبت",
                bg="#fee2e2",
                fg="#b91c1c",
            )
            msg = (
                "⚠️ نموذج الترجمة (English → Arabic) غير مثبت محلياً!\n"
                "لتنزيل وتثبيت النموذج لمرة واحدة أثناء توفر الإنترنت، شغّل في موجه الأوامر:\n"
                "    python3 install_model.py\n"
                "أو لتثبيت ملف محلي مسبق التنزيل: python3 install_model.py <path/to/model.argosmodel>\n"
                "لن يحاول البرنامج الاتصال بالإنترنت تلقائياً لحماية الخصوصية وضمان العمل دون اتصال."
            )
            self.warning_label.config(text=msg)
            self.warning_banner.pack(fill="x", padx=16, pady=(0, 6), before=self.root.pack_slaves()[1])
            self.footer_status.config(text="تنبيه: يلزم تثبيت نموذج الترجمة للبدء.")

    def _on_input_changed(self, event=None):
        """تحديث عداد الأحرف عند الكتابة."""
        content = self.input_text.get("1.0", "end-1c")
        chars = len(content)
        words = len(content.split()) if content.strip() else 0
        self.input_count_label.config(text=f"{chars} حرف | {words} كلمة")

    def format_arabic_for_display(self, text: str) -> str:
        """
        تهيئة النص العربي للعرض السليم في Tkinter على لينكس
        مع ربط الحروف والاتجاه من اليمين لليسار.
        """
        if not text or not BIDI_SUPPORT:
            return text
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except Exception:
            return text

    def start_translation(self):
        """بدء عملية الترجمة في خيط خلفي لمنع تجمّد الواجهة."""
        if self.is_translating:
            return

        input_content = self.input_text.get("1.0", "end-1c").strip()
        if not input_content:
            messagebox.showinfo("تنبيه", "يرجى كتابة نص باللغة الإنجليزية في المربع العلوي أولاً.")
            return

        if not self.model_ready:
            messagebox.showwarning(
                "النموذج غير مثبت",
                "نموذج الترجمة (English -> Arabic) غير مثبت على جهازك حالياً.\n\n"
                "لتثبيته، افتح الطرفية وشغّل:\n"
                "python3 install_model.py\n\n"
                "البرنامج يعمل محلياً ولا يتصل بالإنترنت تلقائياً."
            )
            return

        # تعطيل الأزرار وتحديث مؤشرات الحالة
        self.is_translating = True
        self.translate_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self.footer_status.config(text="جارٍ الترجمة بواسطة النموذج المحلي...")
        self.root.config(cursor="watch")

        # إظهار شريط التقدم
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4), before=self.root.pack_slaves()[-1])
        self.progress_bar.config(value=0, maximum=100)

        # تشغيل الترجمة في Thread منفصل
        worker = threading.Thread(
            target=self._translation_worker,
            args=(input_content,),
            daemon=True,
        )
        worker.start()

    def _progress_callback(self, current: int, total: int, status_message: str):
        """استقبال تحديثات التقدم وتمريرها عبر الطابور الآمن."""
        percent = int((current / total) * 100) if total > 0 else 0
        self._send_to_queue(("progress", percent, status_message))

    def _update_progress_ui(self, percent: int, message: str):
        """تحديث شريط التقدم وشريط الحالة في الخيط الرئيسي."""
        self.progress_bar.config(value=percent)
        self.footer_status.config(text=f"{message} ({percent}%)")

    def _translation_worker(self, text: str):
        """الدالة التي تنفذ في خيط خلفي للترجمة دون تجميد الواجهة."""
        try:
            translated = translate_text(
                text=text,
                from_code="en",
                to_code="ar",
                progress_callback=self._progress_callback,
            )
            self._send_to_queue(("success", translated))
        except (ModelNotFoundError, ArgosNotInstalledError) as e:
            self._send_to_queue(("error", str(e), True))
        except Exception as e:
            self._send_to_queue(("error", f"حدث خطأ غير متوقع: {e}", False))

    def _on_translation_success(self, translated_text: str):
        """معالجة نجاح الترجمة وعرض النص في الواجهة."""
        self.raw_arabic_text = translated_text

        # تهيئة النص للعرض في مربع النص
        display_text = self.format_arabic_for_display(translated_text)

        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", display_text)
        self.output_text.tag_add("rtl", "1.0", "end")

        # تحديث عداد الحروف والكلمات
        chars = len(translated_text)
        words = len(translated_text.split()) if translated_text.strip() else 0
        self.output_count_label.config(text=f"{chars} حرف | {words} كلمة")

        self._reset_ui_state()
        self.footer_status.config(text="✅ اكتملت الترجمة بنجاح محلياً.")

    def _on_translation_error(self, error_message: str, is_model_error: bool):
        """معالجة الخطأ عند الترجمة."""
        self._reset_ui_state()
        self.footer_status.config(text="❌ فشلت الترجمة.")
        if is_model_error:
            self.check_model_status()
            messagebox.showwarning("تنبيه النموذج", error_message)
        else:
            messagebox.showerror("خطأ في الترجمة", error_message)

    def _reset_ui_state(self):
        """إعادة تفعيل الأزرار وتصحيح مؤشر الماوس وإخفاء شريط التقدم."""
        self.is_translating = False
        self.translate_btn.config(state="normal")
        self.clear_btn.config(state="normal")
        self.copy_btn.config(state="normal")
        self.root.config(cursor="")
        self.progress_bar.pack_forget()

    def copy_translation(self):
        """نسخ الترجمة العربية الأصلية إلى الحافظة."""
        text_to_copy = self.raw_arabic_text
        if not text_to_copy.strip():
            text_to_copy = self.output_text.get("1.0", "end-1c").strip()

        if not text_to_copy:
            messagebox.showinfo("تنبيه", "لا توجد ترجمة لنسخها حالياً.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(text_to_copy)
        self.root.update()

        prev_text = self.footer_status.cget("text")
        self.footer_status.config(text="📋 تم نسخ الترجمة إلى الحافظة!")
        self.root.after(2500, lambda: self.footer_status.config(text=prev_text))

    def clear_all(self):
        """مسح نصوص الإدخال والإخراج وتصفير العدادات."""
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.raw_arabic_text = ""
        self.input_count_label.config(text="0 أحرف")
        self.output_count_label.config(text="0 أحرف")
        self.footer_status.config(text="تم مسح النصوص.")


def launch_gui():
    """تشغيل التطبيق الرسومي."""
    root = tk.Tk()
    app = OfflineTranslatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
