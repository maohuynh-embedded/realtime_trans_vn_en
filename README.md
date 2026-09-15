# Realtime Translator VN ⇄ EN

**Phiên dịch cuộc họp trực tuyến theo thời gian thực, chạy hoàn toàn offline trên máy cá nhân.**

> Real-time meeting interpreter (English ⇄ Vietnamese) that runs fully offline on
> your own machine. Captures meeting audio via WASAPI loopback — no virtual audio
> driver, no admin rights, no cloud API calls at runtime.

---

## Giới thiệu

Khi họp với đối tác nước ngoài qua Zoom/Teams/Meet, công cụ này nghe âm thanh
cuộc họp đang phát ra loa, nhận dạng tiếng Anh, dịch sang tiếng Việt và hiển thị
phụ đề (hoặc đọc thành tiếng) gần như tức thì. Chiều ngược lại cho phép bạn nói
tiếng Việt và đối tác nghe được tiếng Anh.

Điểm khác biệt chính:

- **Chạy 100% offline.** Không gọi API đám mây nào lúc runtime — phù hợp với nội
  dung họp nhạy cảm và môi trường doanh nghiệp hạn chế mạng.
- **Không cần quyền admin.** Dùng WASAPI loopback có sẵn trong Windows thay vì
  cài driver âm thanh ảo như VB-CABLE.
- **Tự thích nghi phần cứng.** Cùng một bộ mã chạy tối ưu trên máy có GPU NVIDIA
  lẫn laptop chỉ có CPU — tự dò và chọn cấu hình phù hợp, không phải sửa gì.
- **Phân biệt người nói.** Gán nhãn `Người 1 (nam)` / `Người 2 (nữ)` cho từng
  câu, hữu ích khi theo dõi phỏng vấn hoặc họp nhiều người.

```
[Zoom/Teams/Meet phát ra loa]
        │  WASAPI loopback
        ▼
  Capture → VAD → Nhận diện người nói → STT → Dịch → TTS → Phát ra tai nghe
        │
        ▼
  Giao diện: 2 khung song song (nguyên văn / bản dịch)
```

---

## Tính năng

| | |
|---|---|
| **Hai chiều độc lập** | Anh→Việt (nghe đối tác) và Việt→Anh (đối tác nghe bạn), bật/tắt riêng |
| **Hai chế độ** | Xem video một chiều, hoặc họp hai chiều |
| **Phụ đề hoặc đọc thành tiếng** | Chế độ phụ đề không có độ trễ phát, phù hợp xem video |
| **Nhận diện người nói + giới tính** | ECAPA-TDNN cho danh tính, cao độ giọng (F0) cho giới tính |
| **Tự dò thiết bị âm thanh** | Một nút bấm tìm ra thiết bị nào đang phát tiếng |
| **Chống độ trễ dồn** | Tự bỏ câu cũ khi xử lý không kịp, tránh trễ tăng vô hạn |
| **Chống vòng lặp âm thanh** | Tự tắt thu khi đang đọc — máy chỉ có 1 loa vẫn dùng được |
| **Tự kiểm tra** | Một lệnh kiểm tra toàn bộ và báo việc cần làm tiếp |

---

## Yêu cầu

- **Windows 10/11**, Python 3.10–3.12 (64-bit)
- Tối thiểu 8GB RAM (khuyến nghị 16GB)
- GPU NVIDIA là **tuỳ chọn** — có thì nhanh và chính xác hơn đáng kể

Ứng dụng tự dò phần cứng và chọn cấu hình:

| Phần cứng | STT | Dịch |
|---|---|---|
| GPU NVIDIA (≥5GB VRAM) | Whisper `medium`, CUDA float16 | NLLB-600M trên GPU |
| CPU only | Whisper `small`/`base`, int8 | NLLB-600M trên CPU |

---

## Cài đặt

```bash
git clone git@github.com:maohuynh-embedded/realtime_trans_vn_en.git
```

```bash
cd realtime_trans_vn_en && python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Tăng tốc bằng GPU NVIDIA (tuỳ chọn, khuyến nghị)

```bash
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu126 --force-reinstall
```

```bash
.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

> `--force-reinstall` là bắt buộc — nếu thiếu, pip sẽ báo "Requirement already
> satisfied" và giữ nguyên bản CPU.

### Tải giọng đọc Piper

Tải 4 tệp từ [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
và đặt vào `models/piper/`:

| Tệp | Đường dẫn trên Hugging Face |
|---|---|
| `vi_VN-vais1000-medium.onnx` + `.onnx.json` | `vi/vi_VN/vais1000/medium/` |
| `en_US-lessac-medium.onnx` + `.onnx.json` | `en/en_US/lessac/medium/` |

Các mô hình còn lại (Whisper, NLLB, ECAPA-TDNN) tự tải về cache khi chạy lần đầu.

---

## Sử dụng

### Kiểm tra trước khi dùng

```bash
.venv\Scripts\python.exe main.py --test
```

Kiểm tra thiết bị, mô hình, cắt câu và cả hai chiều dịch, in bảng đạt/không đạt
kèm danh sách việc cần làm tiếp. Không hỏi gì, không phải chọn gì.

### Dịch video đang xem (đơn giản nhất)

```bash
.venv\Scripts\python.exe main.py --watch
```

Tự dò thiết bị đang phát tiếng rồi in phụ đề tiếng Việt. Thêm `--speak` nếu muốn
nghe đọc thành tiếng.

### Giao diện đầy đủ

```bash
.venv\Scripts\python.exe main.py
```

### Tất cả các lệnh

| Lệnh | Chức năng |
|---|---|
| `main.py` | Giao diện đầy đủ, hai chiều |
| `main.py --watch` | Dịch video đang xem, chế độ phụ đề |
| `main.py --watch --speak` | Như trên, có đọc thành tiếng |
| `main.py --test` | Tự kiểm tra toàn bộ hệ thống |
| `main.py --devices` | Liệt kê thiết bị âm thanh |
| `main.py --levels` | Đo xem thiết bị nào đang có tiếng |
| `main.py --check-route` | Kiểm tra đối tác có nghe được tiếng Anh không |
| `main.py --console` | Chạy console, chiều Anh→Việt |
| `main.py --console --both` | Chạy console, cả hai chiều |

> Windows PowerShell 5.1 không hỗ trợ `&&` — chạy từng lệnh riêng hoặc nối bằng `;`.

---

## Định tuyến âm thanh

Phần dễ sai nhất khi thiết lập. WASAPI loopback chỉ **bắt** được âm thanh ra, nó
**không bơm được** audio vào Zoom làm micro — nên chiều Việt→Anh cần một đường
dẫn riêng.

### Bật Stereo Mix (không cần quyền admin)

1. `Win + R` → gõ `mmsys.cpl` → Enter → tab **Recording**
2. Chuột phải vùng trống → tích **Show Disabled Devices**
3. Chuột phải **Stereo Mix** → **Enable**
4. Trong Zoom/Teams: đặt **Microphone = Stereo Mix**

Kiểm chứng bằng `main.py --check-route` — script phát một câu tiếng Anh, ghi lại
từ mic ảo rồi cho Whisper đọc lại, in ra đúng những gì đối tác sẽ nghe thấy.

> **Lưu ý:** Stereo Mix chỉ nghe được âm thanh phát ra **chính card nó thuộc
> về**. `Stereo Mix (Realtek)` không nghe được tiếng phát ra sound card USB khác.
> Ứng dụng tự ghép đúng cặp, nhưng nếu chọn tay thì cần để ý điểm này.

Nếu máy bị khoá không bật được Stereo Mix, dùng cáp 3.5mm nối lỗ tai nghe vào lỗ
mic (hoặc một USB audio adapter rẻ tiền) — bản chất là "VB-CABLE bằng phần cứng".

### Tránh vòng lặp dịch chồng dịch

Nếu bản dịch phát ra chính thiết bị đang bị loopback bắt, nó sẽ bị bắt lại rồi
dịch tiếp. Ứng dụng phát hiện và cảnh báo, đồng thời có cơ chế tự tắt thu trong
lúc đang đọc nên máy chỉ có một loa vẫn dùng được. Cách gọn nhất khi thiếu thiết
bị: bỏ tích **Đọc thành tiếng** và đọc phụ đề trên màn hình.

---

## Hiệu năng

Đo thực tế trên cùng một đoạn audio tiếng Anh dài 9.6 giây:

| Cấu hình | Thời gian STT | Ghi chú |
|---|---|---|
| CPU, `small`, int8 | 1.68s | |
| CPU, `base`, int8 | 0.52s | kém chính xác hơn |
| **GPU RTX 2060, `medium`, float16** | **0.40s** | nhanh hơn **và** chính xác hơn |

Phân tích độ trễ đầy đủ một câu:

| Bước | Thời gian |
|---|---|
| Chờ im lặng để cắt câu | 0.7s |
| Nhận diện người nói (ECAPA) | 0.06s |
| STT | 0.4–1.7s |
| Dịch (NLLB-600M) | 0.45s |
| **Đọc bản dịch thành tiếng** | **~6.6s** |

Bước phát mới là bước tốn thời gian nhất — đọc tiếng Việt mất gần bằng độ dài câu
gốc. Vì vậy **chế độ đọc thành tiếng không thể theo kịp người nói liên tục**; đây
là giới hạn bản chất. Chế độ phụ đề không có độ trễ này và là lựa chọn đúng cho
việc xem video hoặc theo dõi họp một chiều.

### Chất lượng dịch

Dự án dùng **NLLB-200-distilled-600M** thay vì MarianMT. So sánh trên các câu
công việc thực tế:

| Câu gốc | MarianMT | NLLB-600M |
|---|---|---|
| quarterly results | kết quả *phần trăm* ✗ | kết quả **quý** ✓ |
| revenue numbers for Q3 | *số nhân* với Q3 ✗ | **doanh thu** cho quý 3 ✓ |
| the integration | sự *liên kết* ✗ | việc **tích hợp** ✓ |
| dependency issue in staging | mất nghĩa ✗ | vấn đề **phụ thuộc** ✓ |

---

## Cấu trúc dự án

```
app/
  config.py             Cấu hình tập trung, định nghĩa hai chiều dịch
  hardware.py           Tự dò GPU/CPU và chọn cấu hình phù hợp
  cuda_setup.py         Nạp DLL cuBLAS/cuDNN cài qua pip
  audio_devices.py      Liệt kê, lọc và ghép cặp thiết bị âm thanh
  capture.py            Thu âm: WASAPI loopback và mic thật
  resample.py           Chuyển 48/192kHz stereo về 16kHz mono
  vad_segmenter.py      Cắt luồng audio thành từng câu (webrtcvad)
  speaker.py            Nhận diện người nói (ECAPA) và giới tính (F0)
  stt.py                Nhận dạng giọng nói (faster-whisper)
  mt.py                 Dịch máy (NLLB / MarianMT)
  tts.py                Tổng hợp giọng nói (Piper)
  playback.py           Phát audio ra thiết bị chỉ định
  models.py             Quản lý mô hình dùng chung giữa hai chiều
  pipeline.py           Ghép toàn bộ bằng thread và queue
  gui.py                Giao diện Tkinter
  watch.py              Chế độ dịch video đang xem
  levels.py             Đo mức tín hiệu các thiết bị
  selftest.py           Tự kiểm tra toàn bộ
  route_check.py        Kiểm tra đường dẫn âm thanh tới Zoom
  console_run.py        Chạy ở chế độ console
main.py                 Điểm vào chương trình
```

---

## Tinh chỉnh

Toàn bộ tham số nằm trong [`app/config.py`](app/config.py):

| Vấn đề | Cách xử lý |
|---|---|
| Độ trễ tăng dần | Hạ `model_size`, hoặc rút ngắn `max_segment_s` |
| Câu bị cắt vụn | Tăng `end_ring_ms` (mặc định 700ms) |
| Phản hồi chậm | Giảm `end_ring_ms`, đổi lại dễ cắt vụn hơn |
| Bắt nhầm tạp âm | Tăng `vad_aggressiveness` (0–3) |
| Đọc quá nhanh/chậm | Chỉnh `tts_length_scale` |

---

## Tài liệu

- [`HUONG_DAN_XAY_DUNG.md`](HUONG_DAN_XAY_DUNG.md) — tài liệu kiến trúc đầy đủ:
  lý do chọn từng thành phần, các phép đo, những cách đã thử và thất bại, danh
  sách lỗi thường gặp, và hướng dẫn chạy trên GPU tích hợp Intel qua OpenVINO.

---

## Công nghệ sử dụng

| Thành phần | Thư viện |
|---|---|
| Thu âm | [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), [sounddevice](https://python-sounddevice.readthedocs.io/) |
| Cắt câu | [webrtcvad](https://github.com/wiseman/py-webrtcvad) |
| Nhận dạng giọng nói | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| Dịch máy | [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) |
| Tổng hợp giọng nói | [Piper](https://github.com/OHF-Voice/piper1-gpl) |
| Nhận diện người nói | [SpeechBrain ECAPA-TDNN](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) |

---

## Hướng phát triển

- [ ] Giữ giọng gốc người nói bằng OpenVoice V2 (thiết kế đã có trong tài liệu, chưa triển khai)
- [ ] Chạy STT qua OpenVINO trên GPU tích hợp Intel cho máy không có GPU rời
- [ ] Từ điển thuật ngữ riêng theo lĩnh vực để tăng độ chính xác
- [ ] Xuất biên bản cuộc họp ra tệp

---

## Giấy phép

Mã nguồn dự án phát hành theo giấy phép MIT. Các mô hình sử dụng có giấy phép
riêng — lưu ý NLLB-200 dùng giấy phép CC-BY-NC (phi thương mại) và Piper dùng
GPL, cần kiểm tra trước khi dùng cho mục đích thương mại.
