#!/bin/bash
# Cai dat lan dau tren macOS (Apple Silicon): venv, thu vien, helper, giong doc, model dich.
# Chay: macos/setup_mac.sh [--full]     (--full: tai truoc moi model de sau do chay offline)
set -euo pipefail
cd "$(dirname "$0")/.."

# Python 3.12 (hoac 3.11) - Python 3.13+ chua du wheel cho mot so thu vien.
PY=""
for cand in python3.12 python3.11; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "Khong tim thay Python 3.11/3.12. Cai bang: brew install python@3.12 python-tk@3.12"
    exit 1
fi

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "Python nay thieu Tkinter (giao dien). Cai bang: brew install python-tk@3.12"
    exit 1
fi

macos/build_helper.sh
exec "$PY" setup_env.py --skip-test "$@"
