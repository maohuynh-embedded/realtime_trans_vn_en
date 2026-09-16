"""Tat cac canh bao vo hai lam roi console.

Chi tat nhung canh bao da xac minh la KHONG anh huong den hoat dong. Loi that
va canh bao chua ro nguyen nhan van hien binh thuong - khong bao gio nuot het
moi canh bao, vi nhu vay se giau mat van de thuc su.

Goi setup_quiet() mot lan o dau chuong trinh (main.py).
"""
import logging
import os
import warnings


def setup_quiet() -> None:
    # 1. "You are sending unauthenticated requests to the HF Hub"
    #    Chi la goi y dung HF_TOKEN de tai nhanh hon. Model da nam trong cache
    #    nen khong lien quan luc chay.
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

    # 2. "Both `max_new_tokens` (=256) and `max_length` (=200) seem to have been set"
    #    generation_config cua NLLB co san max_length=200, ta truyen max_new_tokens=256.
    #    transformers bao de phong nguoi dung nham, nhung o day la co y:
    #    max_new_tokens thang the va dung la cai ta muon.
    logging.getLogger("transformers.generation.utils").setLevel(logging.ERROR)
    logging.getLogger("transformers.generation.configuration_utils").setLevel(logging.ERROR)

    # 3. Canh bao symlink cua speechbrain tren Windows.
    #    Da xu ly that bang local_strategy=COPY trong app/speaker.py, dong nay chi
    #    de chan phan con lai neu thu vien van bao.
    warnings.filterwarnings(
        "ignore", message=".*symlink.*", category=UserWarning, module="speechbrain.*"
    )
    logging.getLogger("speechbrain.utils.parameter_transfer").setLevel(logging.ERROR)

    # 4. "incorrect regex pattern" khi nap tokenizer tu thu muc CTranslate2 da
    #    xuat (models/bundled/nllb-*-ct2). Loi cua chinh thu vien tokenizers khi
    #    doc file config xuat boi ctranslate2-converter, khong anh huong ket qua
    #    dich - da so sanh dau ra voi ban transformers goc, giong het.
    warnings.filterwarnings("ignore", message=".*incorrect regex pattern.*")

    # 5. KHONG tat thanh tien trinh tai model.
    #    Da thu tat (HF_HUB_DISABLE_PROGRESS_BARS) va do la mot sai lam: lan dau
    #    tai model co the mat vai phut, khong co thanh tien trinh thi nguoi dung
    #    thay app dung im va tuong bi TREO. Thanh tien trinh o day la thong tin
    #    can thiet, khong phai nhieu.
