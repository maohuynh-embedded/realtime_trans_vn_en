#!/bin/bash
# Kiem tra tat tieng goc. Chay trong Terminal.app CUA BAN (khong qua Claude Code) vi quyen am thanh.
# Phat mot am thanh he thong lap lai, roi bat 2 lan: co / khong tat tieng goc.
cd "$(dirname "$0")"
B=.build/sysaudio-capture.app/Contents/MacOS/sysaudio-capture

rms() { python3 - "$1" <<'PY'
import array, math, sys
d = open(sys.argv[1], "rb").read()
a = array.array("f"); a.frombytes(d[: len(d) // 4 * 4])
r = math.sqrt(sum(x * x for x in a) / len(a)) if a else 0
print(f"  am thanh bat duoc: rms={r:.4f}  ->", "CO tin hieu" if r > 0.0001 else "IM LANG (chua cap quyen?)")
PY
}

( while true; do afplay /System/Library/Sounds/Submarine.aiff; done ) &
TONE=$!
trap 'kill $TONE 2>/dev/null; pkill -f "afplay /System/Library/Sounds" 2>/dev/null' EXIT
sleep 2

echo "GIAI DOAN 1 (6s): CO tat tieng goc  -> ban KHONG duoc nghe tieng chuong"
$B --mute-original --seconds 6 > /tmp/mute_on.raw 2>/dev/null
rms /tmp/mute_on.raw
sleep 1
echo "GIAI DOAN 2 (6s): KHONG tat tieng   -> ban PHAI nghe tieng chuong"
$B --seconds 6 > /tmp/mute_off.raw 2>/dev/null
rms /tmp/mute_off.raw
echo "Xong. Neu giai doan 1 van nghe chuong: bao lai cho toi (kem tai nghe dang dung)."
