#!/usr/bin/env bash
# تشغيل برنامج الترجمة المحلي بالكامل
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 main.py "$@"
