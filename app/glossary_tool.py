"""Cong cu tu phuc vu de MO RONG glossary (app/glossary.py) - tra loi cau hoi
"lam sao de tim kiem va them thuat ngu moi de dich chinh xac hon".

BA CACH DUNG:

1) KIEM TRA 1 CAU - xem NLLB dich the nao, CO va KHONG co glossary:

     python -m app.glossary_tool check "The I2C bus uses a pull-up resistor."

2) DO HANG LOAT tu 1 file (moi dong 1 cau) - quet nhanh xem cau nao co the
   dang bi dich sai thuat ngu, ĐE Y "co glossary" khac "khong glossary" o cau nao:

     python -m app.glossary_tool batch cau_can_kiem_tra.txt

3) THEM THUAT NGU MOI - kiem tra AN TOAN truoc khi tu tay sua glossary.py:
   dua tu/cum can them + ban dich Viet mong muon, cong cu se:
     - Bao xem no la CUM hay TU DON (quyet dinh dua vao PHRASES hay WORDS)
     - Test thu cau vi du VOI tu do o VI TRI DAU CAU (rui ro sup cau cao nhat,
       xem app/glossary.py phan "LUU Y" ve loi "rebase") de canh bao neu co
       nguy co
     - In ra dong code san sang dan vao glossary.py

     python -m app.glossary_tool add "watchdog reset" "reset watchdog"

Day la cach TRA LOI CAU HOI "lam sao tim kiem thuat ngu": khong phai tai mot
kho tu dien co san (Microsoft Language Portal da ngung hoat dong tu 2023, cac
tu dien GitHub tim duoc deu la tu dien TONG QUAT khong phan biet nghia ky
thuat - xem lich su chat), ma la QUY TRINH: nghe/doc thay thuat ngu dich sai
-> dan vao day de KIEM CHUNG THAT (khong doan) truoc khi them vao glossary.
"""
import re
import sys

# Chay doc lap qua "python -m app.glossary_tool" nen KHONG di qua buoc ep
# UTF-8 cua main.py - phai tu lam o day, neu khong console Windows (cp1252)
# se bao loi khi in ky tu tieng Viet (vd. UnicodeEncodeError voi "đ").
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _load_translator():
    from app.mt import Translator
    return Translator("en", "vi", backend="nllb")


def cmd_check(text: str) -> None:
    from app.glossary import protect_terms, restore_terms

    tr = _load_translator()
    protected, restore = protect_terms(text)
    without = tr._translate_raw(text)
    with_g = restore_terms(tr._translate_raw(protected), restore)

    print(f"Cau goc        : {text}")
    if protected != text:
        print(f"Da bao ve      : {protected}")
        print(f"  (cac thuat ngu duoc bao ve: {restore})")
    else:
        print("Da bao ve      : (khong co thuat ngu nao trong glossary khop cau nay)")
    print(f"\nKHONG glossary : {without}")
    print(f"CO glossary    : {with_g}")

    if protected == text:
        print("\n-> Cau nay chua co thuat ngu nao trong glossary. Neu ban dich VAN SAI,")
        print("   dung 'python -m app.glossary_tool add \"tu/cum\" \"ban dich Viet\"' de kiem tra")
        print("   va them tu con thieu.")
    elif without == with_g:
        print("\n-> Glossary khong doi ket qua o cau nay (NLLB da dich dung san).")
    else:
        print("\n-> Glossary CO thay doi ket qua - kiem tra xem ban 'CO glossary' co dung hon khong.")


def cmd_batch(path: str) -> None:
    from app.glossary import protect_terms, restore_terms

    try:
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        print(f"Khong tim thay file: {path}")
        return

    if not lines:
        print("File rong.")
        return

    print(f"Dang do {len(lines)} cau tu {path}...\n")
    tr = _load_translator()
    changed, unchanged, no_terms = [], [], []

    for i, text in enumerate(lines, 1):
        protected, restore = protect_terms(text)
        if protected == text:
            no_terms.append(text)
            continue
        without = tr._translate_raw(text)
        with_g = restore_terms(tr._translate_raw(protected), restore)
        if without != with_g:
            changed.append((text, without, with_g))
        else:
            unchanged.append(text)
        print(f"  [{i}/{len(lines)}] xong")

    print(f"\n{'=' * 70}")
    print(f"KET QUA: {len(changed)} cau glossary lam thay doi, {len(unchanged)} khong doi, "
          f"{len(no_terms)} khong co thuat ngu")
    print("=" * 70)

    if changed:
        print("\n--- Cac cau glossary da thay doi ban dich (kiem tra xem co dung hon khong) ---")
        for text, without, with_g in changed:
            print(f"\nEN            : {text}")
            print(f"KHONG glossary: {without}")
            print(f"CO glossary   : {with_g}")

    if no_terms:
        print(f"\n--- {len(no_terms)} cau KHONG co thuat ngu nao trong glossary ---")
        print("(neu nghi ngo ban dich sai o day, dung 'add' de kiem tra tung tu)")
        for text in no_terms[:10]:
            print(f"  - {text}")
        if len(no_terms) > 10:
            print(f"  ... va {len(no_terms) - 10} cau khac")


def cmd_add(term: str, viet: str) -> None:
    from app.glossary import _PHRASES, _WORDS  # noqa - chi doc de kiem tra trung

    tr = _load_translator()
    is_phrase = " " in term.strip()
    table_name = "_PHRASES" if is_phrase else "_WORDS"
    existing = _PHRASES if is_phrase else _WORDS
    key = term.strip().lower()

    print(f"Thuat ngu      : {term!r}  ({'CUM' if is_phrase else 'TU DON'} -> them vao {table_name})")
    if key in existing:
        print(f"!! DA CO SAN trong {table_name}: {key!r} -> {existing[key]!r}")
        print("   (neu muon doi gia tri, sua truc tiep trong app/glossary.py)")

    # Canh bao rui ro trung voi tu tieng Anh thong dung (vd "can", "it", "as")
    COMMON_WORDS = {"can", "it", "as", "may", "will", "is", "are", "was", "were",
                    "has", "have", "had", "do", "does", "did", "if", "so", "to",
                    "in", "on", "at", "by", "of", "or", "and", "the", "a", "an"}
    if not is_phrase and key in COMMON_WORDS:
        print(f"\n!! CANH BAO: {key!r} TRUNG voi tu tieng Anh RAT thong dung.")
        print("   Da gap loi that: bao ve 'can' (giao thuc CAN bus) trung voi dong")
        print("   tu 'can' ('Can you...') lam sup ca cau. Can nhac dung dang CUM")
        print(f"   thay vi tu don (vd. '{key} bus' thay vi '{key}' mot minh).")

    # Test cau vi du - QUAN TRONG: phai co it nhat 1 cau dat thuat ngu O VI TRI
    # DONG TU MENH LENH ("Please {term} your...") - day CHINH XAC la vi tri da
    # lam sup cau voi "rebase" ("Please rebase your..." -> sinh dau "..." thay
    # vi noi dung). Cau dang "{term} is..." hay "check the {term}" (danh tu)
    # KHONG bat duoc loi nay - da tung kiem chung nham nhu vay.
    test_sentences = [
        f"Please {term} your project before continuing.",   # RUI RO NHAT: vi tri dong tu
        f"{term.capitalize()} is important for this project.",
        f"Please check the {term} before continuing.",
    ]
    print(f"\nDang test voi ban dich de xuat: {viet!r}")
    print("(cau dau dat o VI TRI DONG TU MENH LENH - rui ro sup cau cao nhat,")
    print(" dung nguyen mau loi 'rebase' da gap thuc te)\n")

    risky = False
    placeholder_survives = re.compile(r"_{1,3}0_{1,3}")
    for sent in test_sentences:
        placeholder_sent = re.sub(re.escape(term), "__0__", sent, flags=re.IGNORECASE)
        out = tr._translate_raw(placeholder_sent)
        survived = bool(placeholder_survives.search(out))
        out_final = placeholder_survives.sub(viet, out) if survived else out

        print(f"  IN : {sent}")
        print(f"  OUT: {out_final}")

        if not survived:
            # Placeholder BIEN MAT khoi output - co the la sup cau kieu "..."
            # (loi "rebase") HOAC bi thay bang mot tu KHAC lay bua tu cau (da
            # gap: "flash" -> model tu y dung "tiếp tục" muon tu chu "continuing"
            # o cuoi cau, khong lien quan gi den "flash"). CA HAI deu nguy hiem
            # nhu nhau: noi dung that su bi mat, khong the phuc hoi lai duoc.
            print("  !! CANH BAO: placeholder BIEN MAT khoi ket qua (khong con dau vet '_0_').")
            print("     Model co the da sup cau hoac tu y thay bang tu khac khong lien quan.")
            risky = True
        print()

    print("=" * 70)
    if risky:
        print("!! CAU DAU TIEN (vi tri dong tu menh lenh) that bai.")
        print()
        print("   LUU Y QUAN TRONG: day la phep thu NANG (ep tu vao vi tri dong tu),")
        print("   NLLB-600M hau nhu LUON that bai voi phep thu nay bat ke tu gi - kha")
        print("   nang cao day la BAO DONG GIA neu tu cua ban la DANH TU THUAN TUY")
        print("   khong bao gio dung o vi tri dong tu trong loi noi that (vd. mot")
        print("   thuat ngu phan cung nhu 'brownout' khong ai noi 'Please brownout...').")
        print()
        print("   Tu quyet dinh dua vao NGU CANH THAT: neu tu nay CO THE xuat hien o")
        print("   VI TRI DONG TU trong cau thuc te (vd. 'rebase', 'flash the firmware',")
        print("   'merge the branch') -> KHONG nen them o dang tu don, chi bao ve trong")
        print("   CUM co san. Neu tu CHI la danh tu thuan tuy (khong ai dung no lam dong")
        print("   tu) -> co the van an toan de them, du phep thu nang nay 'canh bao'.")
    else:
        print(f"An toan de them. Dan dong nay vao {table_name} trong app/glossary.py:\n")
        quoted_viet = "None" if viet.strip().lower() in ("none", "-", "") else repr(viet)
        print(f'    "{key}": {quoted_viet},')


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "check" and len(args) >= 2:
        cmd_check(" ".join(args[1:]))
    elif cmd == "batch" and len(args) >= 2:
        cmd_batch(args[1])
    elif cmd == "add" and len(args) >= 3:
        cmd_add(args[1], args[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
