#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# اختيار بايثون من بيئة العمل الافتراضية venv
if [ -f "$DIR/../venv/bin/python3" ]; then
    PYTHON="$DIR/../venv/bin/python3"
elif [ -f "$DIR/venv/bin/python3" ]; then
    PYTHON="$DIR/venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo "Python 3 not found!"
    exit 1
fi

echo "========================================================="
echo "   ⚡ تشغيل TurboTranslator Web (المترجم المحلي الأوفلاين)"
echo "========================================================="

exec "$PYTHON" "$DIR/server.py" "$@"
