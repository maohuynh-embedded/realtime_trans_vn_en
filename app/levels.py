"""Do muc tin hieu / tu tim nguon dang phat tieng.

Cai dat phu thuoc he dieu hanh nen nam trong windows/levels.py va
macos/levels.py; file nay chi la cong vao chung.

Chay: python main.py --levels
"""
from app.platform_impl import levels as _platform

find_active_loopback = _platform.find_active_loopback
main = _platform.main
