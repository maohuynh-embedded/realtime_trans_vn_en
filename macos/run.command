#!/bin/bash
# Nhap dup file nay (hoac chay tu Terminal) de mo ung dung. Lan dau se tu cai dat.
# Chay tu Terminal: macOS gan quyen "Ghi am thanh he thong" cho Terminal.
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    macos/setup_mac.sh || { echo; read -n 1 -s -r -p "Cai dat that bai. Bam phim bat ky de dong."; exit 1; }
fi
exec .venv/bin/python main.py "$@"
