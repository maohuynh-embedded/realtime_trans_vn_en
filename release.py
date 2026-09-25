"""Dong goi ban phat hanh (release) tu ma nguon da commit trong git.

Vi sao dung `git archive` thay vi zip thang thu muc lam viec: chi lay dung
nhung file da duoc TRACK trong git (tu dong tuan theo .gitignore), nen khong
bao gio vo tinh dong goi .venv/ hay models/ (vai chuc GB) hay file rac con sot
lai tu luc dev/test - dung chinh xac nhung gi da commit, khong hon khong kem.

Dung khi ban muon dong goi mot ban "san sang dua cho nguoi dung khac": nguoi
nhan chi can giai nen roi nhap dup windows/CHAY_APP.bat, khong can cai Git hay tu tay
lay ma nguon.

  python release.py                 tu tang so phien ban (v1.0.0 -> v1.0.1),
                                     tao git tag, dong goi ra dist/*.zip
  python release.py v1.2.0          dat dich danh so phien ban cu the
  python release.py --minor         tang so GIUA thay vi so cuoi (v1.0.3 -> v1.1.0)
  python release.py --major         tang so DAU (v1.0.3 -> v2.0.0)
  python release.py --no-tag        dong goi tu HEAD, KHONG tao git tag (thu nghiem)
  python release.py --push          sau khi tag xong, day tag do len GitHub

Ban phat hanh la ban CHUA KEM MODEL (models/ nang vai GB, khong hop de dong
goi cung ma nguon). Nguoi dung giai nen xong, windows/CHAY_APP.bat se tu tai model o
lan chay dau tien (can mang). Muon dong goi CA model de chay offline hoan
toan, xem huong dan trong README.md muc "Dong goi offline".
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PROJECT_NAME = "realtime_trans_vn_en"


def sh(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"!! Lenh that bai: {' '.join(args)}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def last_tag() -> str | None:
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def bump(version: str, part: str) -> str:
    """v1.2.3 -> v1.2.4 (patch, mac dinh) / v1.3.0 (minor) / v2.0.0 (major)."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        return "v1.0.0"
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        return f"v{major + 1}.0.0"
    if part == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def working_tree_clean() -> bool:
    return sh("git", "status", "--porcelain") == ""


def changelog_since(prev_tag: str | None) -> str:
    """Danh sach dong dau cua tung commit ke tu tag truoc, cho ghi chu phat hanh."""
    range_spec = f"{prev_tag}..HEAD" if prev_tag else "HEAD"
    log = sh("git", "log", range_spec, "--pretty=format:- %s", check=False)
    return log or "- (khong co thay doi nao ke tu ban truoc)"


def main() -> None:
    args = sys.argv[1:]
    push = "--push" in args
    no_tag = "--no-tag" in args
    part = "minor" if "--minor" in args else ("major" if "--major" in args else "patch")
    explicit = next((a for a in args if re.match(r"^v?\d+\.\d+\.\d+$", a)), None)

    print("=" * 68)
    print("  DONG GOI BAN PHAT HANH")
    print("=" * 68)

    if not no_tag and not working_tree_clean():
        print("\n!! Cay lam viec dang co thay doi CHUA COMMIT:")
        print(sh("git", "status", "--short"))
        print("\n   Commit hoac stash truoc, hoac dung --no-tag de dong goi tam thoi tu HEAD.")
        sys.exit(1)

    prev = last_tag()
    if explicit:
        version = explicit if explicit.startswith("v") else f"v{explicit}"
    else:
        version = bump(prev, part) if prev else "v1.0.0"

    print(f"\n  Ban truoc     : {prev or '(chua co ban nao)'}")
    print(f"  Ban moi        : {version}{'  (khong tao tag - che do thu nghiem)' if no_tag else ''}")

    notes = changelog_since(prev)
    print(f"\n  Thay doi ke tu ban truoc:\n{notes}")

    if not no_tag:
        existing_tags = sh("git", "tag", "-l", version)
        if existing_tags:
            # Tag da co (vd. lan truoc tao tag xong nhung buoc dong goi bi loi)
            # - khong loi cung, chi bo qua buoc tao va dong goi lai tu tag do.
            tagged_commit = sh("git", "rev-list", "-n", "1", version)
            head_commit = sh("git", "rev-parse", "HEAD")
            if tagged_commit != head_commit:
                print(f"\n!! Tag {version} da ton tai nhung TRO TOI COMMIT KHAC voi HEAD hien tai.")
                print(f"   Chon so phien ban khac, hoac xoa tag cu (git tag -d {version}) neu chac chan.")
                sys.exit(1)
            print(f"\n  Tag {version} da co san (tro dung HEAD hien tai) - bo qua buoc tao, dong goi lai.")
        else:
            print(f"\n  Dang tao git tag {version}...")
            tag_msg = f"{PROJECT_NAME} {version}\n\n{notes}"
            sh("git", "tag", "-a", version, "-m", tag_msg)

        if push:
            print(f"  Dang day tag len GitHub...")
            sh("git", "push", "origin", version)

    # ---- Dong goi ----
    DIST.mkdir(exist_ok=True)
    zip_name = f"{PROJECT_NAME}-{version}.zip"
    zip_path = DIST / zip_name

    ref = version if not no_tag else "HEAD"
    print(f"\n  Dang dong goi tu '{ref}' (chi file da commit trong git)...")

    # git archive tao san 1 file zip dung nhung gi da track - dung truc tiep,
    # khong can tu liet ke file.
    tmp_zip = DIST / f"_archive_{version}.zip"
    with open(tmp_zip, "wb") as f:
        result = subprocess.run(["git", "archive", "--format=zip", ref], cwd=ROOT, stdout=f)
    if result.returncode != 0:
        print("!! git archive that bai."); sys.exit(1)

    # Bo vao 1 thu muc goc ben trong zip (vd realtime_trans_vn_en-v1.0.0/...) de
    # giai nen ra khong bi tran file ra ngoai thu muc Downloads cua nguoi dung.
    root_folder = f"{PROJECT_NAME}-{version}"
    with zipfile.ZipFile(tmp_zip, "r") as src, zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(f"{root_folder}/{item.filename}", data)
    tmp_zip.unlink()

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"\n{'=' * 68}\n  XONG: {zip_path}  ({size_mb:.2f} MB)\n{'=' * 68}")
    print(f"\n  Dua file nay cho nguoi dung: ho giai nen roi nhap dup windows/CHAY_APP.bat.")
    print(f"  Lan dau chay se tu cai dat (can mang de tai thu vien + model).")

    if not no_tag and not push:
        print(f"\n  Tag {version} moi chi o may nay. Day len GitHub bang:")
        print(f"      git push origin {version}")


if __name__ == "__main__":
    main()
