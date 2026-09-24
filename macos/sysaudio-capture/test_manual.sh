#!/bin/bash
# Chay tay trong Terminal cua ban (KHONG qua Claude Code) de xin quyen dung.
set -e
cd "$(dirname "$0")"
APP=.build/sysaudio-capture.app
echo "Bat am thanh he thong 5 giay - phat mot video/nhac gi do trong luc nay..."
"$APP/Contents/MacOS/sysaudio-capture" --seconds 5 > /tmp/tap_manual.raw 2> /tmp/tap_manual.err
cat /tmp/tap_manual.err
python3 - <<'PY'
import array, math
d = open('/tmp/tap_manual.raw','rb').read()
a = array.array('f'); a.frombytes(d[:len(d)//4*4])
n=len(a)
rms = math.sqrt(sum(x*x for x in a)/n) if n else 0
print(f"samples={n} rms={rms:.5f} peak={max((abs(x) for x in a), default=0):.4f}")
print("KET QUA:", "CO BAT DUOC AM THANH" if rms>0.0001 else "VAN IM LANG - kiem tra da cho phep quyen chua")
PY
