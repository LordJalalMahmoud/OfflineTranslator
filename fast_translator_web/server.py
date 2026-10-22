#!/usr/bin/env python3
"""
خادم الويب المحلي فائق السرعة للترجمة بدون إنترنت (Offline Web Server)
- يعتمد على مكتبة بايثون القياسية http.server مع دعم الخيوط المتزامنة Threading
- يقدم واجهة HTML تفاعلية عصرية جداً تعمل بدون اتصال بالإنترنت بنسبة 100%
- يوفر واجهات برمجة تطبيقات (REST APIs) للترجمة الفورية وترجمة الملفات وإدارة الكاش
"""

import os
import sys
import json
import time
import uuid
import signal
import socket
import threading
import webbrowser
import urllib.parse
from pathlib import Path
from http import HTTPStatus
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler

# إضافة المسار الحالي للمكتبة
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from arabizi import arabic_to_arabizi, get_arabizi_dictionary
from engine import WebTranslationEngine

STATIC_DIR = CURRENT_DIR / "static"


class TranslatorRequestHandler(SimpleHTTPRequestHandler):
    """معالج طلبات HTTP المخصص للترجمة."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CURRENT_DIR), **kwargs)

    def _serve_file(self, file_path: Path, content_type: str):
        """خدمة ملف ثابت مباشرة مع ترويسات الأمان ونوع المحتوى."""
        if not file_path.exists():
            self.send_error(404, "File not found")
            return
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def _send_json_response(self, data: dict, status_code: int = 200):
        """إرسال رد بصيغة JSON مع الترويسات الصحيحة وترميز UTF-8."""
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> dict:
        """قراءة وتحليل محتوى الطلب المرسل بصيغة JSON."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body)

    def do_OPTIONS(self):
        """معالجة استعلامات CORS Preflight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """معالجة طلبات GET."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. الصفحة الرئيسية والملفات الثابتة
        if path in ("/", "/index.html"):
            return self._serve_index_html()

        if path in ("/static/style.css", "/style.css"):
            return self._serve_file(STATIC_DIR / "style.css", "text/css")

        if path in ("/static/app.js", "/app.js"):
            return self._serve_file(STATIC_DIR / "app.js", "application/javascript")

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # 2. فحص حالة الخادم والنموذج
        if path == "/api/status":
            engine = WebTranslationEngine.get_instance()
            return self._send_json_response({
                "status": "online",
                "mode": "100% Offline (بدون إنترنت)",
                "stats": engine.get_stats(),
            })

        # 3. جدول تحويل الفرانكو (Cheat-sheet)
        if path == "/api/arabizi_dictionary":
            return self._send_json_response({
                "dictionary": get_arabizi_dictionary()
            })

        # 4. البحث في الكاش
        if path == "/api/cache/search":
            q = query.get("q", [""])[0]
            limit = int(query.get("limit", [50])[0])
            engine = WebTranslationEngine.get_instance()
            results = engine.search_cache(q, limit=limit)
            return self._send_json_response({"query": q, "results": results, "count": len(results)})

        # 5. عرض الملفات المحلية القابلة للترجمة في المجلد
        if path == "/api/local_files":
            return self._handle_list_local_files()

        # 6. متابعة حالة تقدم ملف قيد الترجمة
        if path == "/api/file/progress":
            task_id = query.get("task_id", [""])[0]
            engine = WebTranslationEngine.get_instance()
            progress = engine.get_task_progress(task_id)
            if not progress:
                return self._send_json_response({"error": "Task not found"}, 404)
            # تجنب إرسال المحتوى الكامل في الاستعلام الدوري
            clean_progress = {k: v for k, v in progress.items() if k != "output_content"}
            return self._send_json_response(clean_progress)

        # 7. تحميل الملف الناتج
        if path == "/api/file/download":
            task_id = query.get("task_id", [""])[0]
            engine = WebTranslationEngine.get_instance()
            task = engine.get_task_progress(task_id)
            if not task or not task.get("output_content"):
                return self._send_json_response({"error": "No output available"}, 404)

            filename = f"translated_{task_id[:8]}.json"
            content = task["output_content"].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 8. خدمة الملفات الثابتة (CSS, JS, إلخ)
        return super().do_GET()

    def do_POST(self):
        """معالجة طلبات POST."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            # 1. ترجمة نص فوري
            if path == "/api/translate":
                data = self._read_json_body()
                text = data.get("text", "")
                mode = data.get("mode", "dual")  # 'arabic', 'arabizi', or 'dual'
                engine_type = data.get("engine", "nllb")  # 'nllb' or 'argos'
                dialect = data.get("dialect", "arb_Arab")  # 'arb_Arab' or 'arz_Arab'
                engine = WebTranslationEngine.get_instance()
                result = engine.translate_single(
                    text,
                    mode=mode,
                    engine_type=engine_type,
                    dialect=dialect
                )
                return self._send_json_response(result)

            # 2. تحويل عربي إلى فرانكو مباشر بدون نموذج ذكاء اصطناعي
            if path == "/api/arabizi_direct":
                data = self._read_json_body()
                text = data.get("text", "")
                result = arabic_to_arabizi(text)
                return self._send_json_response({"original": text, "arabizi": result})

            # 3. بدء ترجمة ملف
            if path == "/api/file/start":
                data = self._read_json_body()
                file_type = data.get("type", "path")
                mode = data.get("mode", "arabic")
                engine_type = data.get("engine", "nllb")
                dialect = data.get("dialect", "arb_Arab")
                batch_size = int(data.get("batch_size", 64 if engine_type == "nllb" else 128))
                task_id = str(uuid.uuid4())
                engine = WebTranslationEngine.get_instance()

                dialect_suffix = "_egypt" if dialect == "arz_Arab" else ""

                if file_type == "path":
                    input_path = data.get("path")
                    # إذا كان مساراً نسبياً، ابدأ من مجلد المشروع
                    abs_path = (engine.project_root / input_path).resolve()
                    if not abs_path.exists():
                        abs_path = Path(input_path).resolve()
                    
                    if not abs_path.exists():
                        return self._send_json_response({"error": f"الملف {input_path} غير موجود على الخادم."}, 400)

                    out_name = f"{abs_path.stem}_{mode}_{engine_type}{dialect_suffix}{abs_path.suffix}"
                    output_path = abs_path.parent / out_name

                    engine.start_file_translation(
                        task_id=task_id,
                        input_path=str(abs_path),
                        output_path=str(output_path),
                        mode=mode,
                        engine_type=engine_type,
                        dialect=dialect,
                        batch_size=batch_size,
                    )
                else:
                    # محتوى مرسل مباشرة من المتصفح
                    content = data.get("content", "")
                    filename = data.get("filename", "dialog.json")
                    out_path = engine.project_root / f"translated_{mode}_{engine_type}{dialect_suffix}_{filename}"

                    engine.start_file_translation(
                        task_id=task_id,
                        input_content=content,
                        output_path=str(out_path),
                        mode=mode,
                        engine_type=engine_type,
                        dialect=dialect,
                        batch_size=batch_size,
                    )

                return self._send_json_response({"task_id": task_id, "status": "started"})

            # 4. إلغاء ترجمة ملف قيد التنفيذ
            if path == "/api/file/cancel":
                data = self._read_json_body()
                task_id = data.get("task_id", "")
                engine = WebTranslationEngine.get_instance()
                engine.cancel_task(task_id)
                return self._send_json_response({"status": "cancelling", "task_id": task_id})

            # 5. حفظ الكاش يدوياً
            if path == "/api/cache/save":
                engine = WebTranslationEngine.get_instance()
                engine.save_caches()
                return self._send_json_response({"status": "saved", "stats": engine.get_stats()})

            self._send_json_response({"error": "Not Found"}, 404)

        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)

    def _serve_index_html(self):
        """عرض ملف index.html الرئيسي."""
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            self.send_error(404, "index.html not found")
            return
        with open(index_file, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_list_local_files(self):
        """استكشاف ملفات الـ JSON والألعاب المتوفرة محلياً للاختيار السريع."""
        engine = WebTranslationEngine.get_instance()
        project_root = engine.project_root
        files = []

        patterns = ["*.json", "fast_translator*/*.json"]
        for p in patterns:
            for f in project_root.glob(p):
                if f.is_file() and not f.name.endswith(".tmp"):
                    size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                    files.append({
                        "name": f.name,
                        "rel_path": str(f.relative_to(project_root)),
                        "size_mb": size_mb,
                    })

        files.sort(key=lambda x: x["name"])
        return self._send_json_response({"files": files})


def find_free_port(start_port: int = 8765, max_attempts: int = 20) -> int:
    """البحث عن منفذ متاح للتشغيل."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def main():
    import argparse

    parser = argparse.ArgumentParser(description="TurboTranslator Offline Web Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    # تهيئة محرك الترجمة قبل بدء الخادم لضمان الجاهزية الفورية
    print("==================================================================")
    print(" 🚀 TurboTranslator Web Edition | المترجم فائق السرعة بدون إنترنت")
    print("==================================================================")
    print("[INIT] جاري تحميل محرك CTranslate2 ونماذج الذكاء الاصطناعي والكاش...")
    
    t0 = time.time()
    engine = WebTranslationEngine.get_instance()
    stats = engine.get_stats()
    print(f"[INIT] تم تحميل النموذج وقاموس الكاش ({stats['arabic_cached_entries']:,} ترجمة) في {time.time() - t0:.2f} ثانية!")

    port = find_free_port(args.port)
    server_address = (args.host, port)
    
    try:
        httpd = ThreadingHTTPServer(server_address, TranslatorRequestHandler)
    except Exception as e:
        print(f"[ERROR] فشل ربط المنفذ {port}: {e}")
        sys.exit(1)

    url = f"http://{args.host}:{port}"
    print(f"✨ الخادم يعمل الآن بدون إنترنت 100% على الرابط:")
    print(f"👉 \033[1;32m{url}\033[0m")
    print("------------------------------------------------------------------")
    print("اضغط Ctrl+C في أي وقت لإيقاف الخادم وحفظ الكاش بأمان.")

    # فتح المتصفح تلقائياً
    if not args.no_browser:
        def open_browser():
            time.sleep(0.6)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    # التقاط إشارات الإغلاق لحفظ الكاش بأمان
    def shutdown_handler(signum, frame):
        print("\n[SHUTDOWN] جاري إيقاف الخادم وحفظ الكاش على القرص...")
        engine.save_caches()
        httpd.server_close()
        print("✅ تم الإغلاق بنجاح. إلى اللقاء!")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        shutdown_handler(None, None)


if __name__ == "__main__":
    main()
