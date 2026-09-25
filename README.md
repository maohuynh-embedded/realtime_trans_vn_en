# Realtime Translator VN ⇄ EN

**Phiên dịch cuộc họp trực tuyến theo thời gian thực, chạy hoàn toàn offline trên máy cá nhân.**

> Real-time meeting interpreter (English ⇄ Vietnamese) that runs fully offline on
> your own machine (Windows and macOS). Captures meeting audio via WASAPI loopback
> (Windows) or a Core Audio tap (macOS) — no virtual audio driver for listening, no
> admin rights, no cloud API calls at runtime.

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
| **Windows và macOS** | Cùng một lõi, mỗi nền tảng có gói riêng (`windows/`, `macos/`); Mac Apple Silicon dùng GPU qua MLX |
| **Tắt tiếng gốc (macOS)** | Chỉ nghe bản dịch, tiếng video gốc bị tắt trong lúc dịch (đang kiểm chứng) |
| **Giữ giọng người nói (macOS, dịch sang tiếng Anh)** | Đọc bản dịch bằng giọng của chính người nói (Chatterbox, sao chép giọng); trễ cao hơn Piper, xem mục Hiệu năng |

---

## Yêu cầu

**Windows**

- Windows 10/11, Python 3.10–3.12 (64-bit)
- Tối thiểu 8GB RAM (khuyến nghị 16GB)
- GPU NVIDIA là **tuỳ chọn** — có thì nhanh và chính xác hơn đáng kể

**macOS**

- Apple Silicon (M1 trở lên), **macOS 14.4 trở lên** (Core Audio tap); đã thử trên macOS 26
- Python 3.11 hoặc 3.12 từ Homebrew (`brew install python@3.12 python-tk@3.12`), Xcode Command Line Tools (`xcode-select --install`)
- 16GB RAM trở lên khuyến nghị (model `large-v3-turbo` và sao chép giọng)
- Quyền **Ghi âm thanh hệ thống** cho Terminal (hộp thoại tự hiện lần đầu chạy)

Ứng dụng tự dò phần cứng và chọn cấu hình:

| Phần cứng | STT | Dịch |
|---|---|---|
| GPU NVIDIA (≥5GB VRAM) | Whisper `medium`, CUDA float16 | NLLB-600M trên GPU |
| CPU only | Whisper `small`/`base`, int8 | NLLB-600M trên CPU |

---

## Cài đặt

### Cách 1 — Người dùng cuối (khuyến nghị)

Tải mã nguồn về, rồi **nhấp đúp vào `windows/CHAY_APP.bat`**.

Lần đầu chạy, nó tự tạo môi trường, cài thư viện, dò phần cứng và tải giọng đọc —
mất vài phút và chỉ làm một lần. Các lần sau mở thẳng giao diện.

Yêu cầu duy nhất: máy đã cài **Python 3.10–3.12**. Nếu chưa có, script sẽ báo và
chỉ chỗ tải. Lúc cài Python nhớ tích ô **"Add Python to PATH"**.

Người dùng không cần chạm tới dòng lệnh, cũng không cần chọn thiết bị âm thanh —
app mặc định **tự dò thiết bị đang phát tiếng**. Chỉ khi máy có nhiều tai nghe và
muốn đổi thì mới bỏ tích *"Tự động chọn thiết bị"* để chọn tay.

### Cách 2 — Lập trình viên

```bash
python setup_env.py
```

Làm cùng các bước trên nhưng hiện chi tiết, kèm tự kiểm tra ở cuối. Tuỳ chọn:
`--full` tải sẵn toàn bộ mô hình để sau đó chạy offline hoàn toàn, `--cpu` ép
dùng bản CPU, `--skip-test` bỏ bước kiểm tra.

### Cách 3 — Thủ công

```bash
git clone git@github.com:maohuynh-embedded/realtime_trans_vn_en.git
```

```bash
cd realtime_trans_vn_en && python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r windows/requirements.txt
```

### macOS

Chạy trong **Terminal.app** (không chạy qua công cụ khác: macOS gắn quyền ghi âm với ứng dụng khởi chạy).

```bash
macos/setup_mac.sh
```

Script build helper bắt âm thanh (Swift), tạo `.venv`, cài thư viện, tải giọng Piper và mô hình dịch. Tuỳ chọn `--full` tải sẵn mọi mô hình để chạy offline. Sau đó:

```bash
macos/run.command
```

(hoặc nhấp đúp `macos/run.command`). Muốn đối tác nghe tiếng Anh trong Zoom/Teams cần mic ảo: `brew install blackhole-2ch`.

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

> Các lệnh dưới đây viết cho Windows (`.venv\Scripts\python.exe`). Trên macOS dùng `.venv/bin/python`.

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

### macOS

Không cần driver ảo để **nghe**: app bắt âm thanh hệ thống bằng Core Audio tap qua helper Swift (`macos/sysaudio-capture`), loại trừ chính tiến trình Python khỏi tap nên bản dịch phát ra không bị bắt lại (tính năng này chưa được kiểm chứng ngoài thực tế).

- **Quyền:** lần đầu macOS hỏi "Ghi âm thanh hệ thống" cho Terminal. Từ chối không báo lỗi mà chỉ ra toàn số 0; khi đó app cảnh báo sau vài giây. Bật lại ở System Settings → Privacy & Security → Screen & System Audio Recording.
- **Chỉ nghe bản dịch:** tích "Tat tieng goc (chi nghe ban dich)" cùng "Doc thanh tieng", rồi bấm Bat. Tiếng gốc chỉ tắt trong lúc helper chạy. Kiểm tra bằng `macos/sysaudio-capture/test_mute.sh`.
- **Đưa tiếng Anh vào Zoom/Teams (Việt→Anh):** cần BlackHole (`brew install blackhole-2ch`), đặt mic của Zoom là BlackHole 2ch. Kiểm tra bằng `main.py --check-route`. macOS không có Stereo Mix.

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

### Apple Silicon (M2 Pro 32GB)

STT `large-v3-turbo` qua MLX (GPU): trung vị **1,2s/câu ~7,7s** khi giọng thật và tự nhận diện ngôn ngữ (gồm ~0,55s đoán ngôn ngữ); dịch NLLB trên CPU 0,3–0,9s tuỳ độ dài câu. Trên video mẫu, gần một nửa câu bị cắt cưỡng bức ở 8s vì lời nói liên tục, và độ trễ từ lúc dứt lời đến bản dịch trung vị ~2s (p95 ~6s khi gom câu). Đọc bằng **giọng người nói** (Chatterbox) cần ~0,85s cho mỗi giây âm thanh nên câu đầu ra tiếng sau khoảng 6–8s (Piper: 1,5s); tụt trễ quá 5s app tự dùng Piper. Chi tiết và số đo: [`docs/architecture-windows-vs-macos.md`](docs/architecture-windows-vs-macos.md).

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

`app/` là lõi dùng chung; `windows/` và `macos/` ngang hàng, mỗi bên cung cấp phần bắt âm thanh, dò phần cứng và cài đặt
riêng. Lõi chỉ đi qua `app/platform_impl.py` (xem [`docs/architecture-windows-vs-macos.md`](docs/architecture-windows-vs-macos.md)).

```
main.py                 Điểm vào chương trình
setup_env.py            Cài đặt tự động (nhận biết nền tảng)
requirements-common.txt Thư viện dùng chung
app/                    Lõi dùng chung
  config.py             Cấu hình tập trung, định nghĩa các chiều dịch
  platform_impl.py      Chọn windows/ hoặc macos/ theo hệ điều hành
  accel.py, hardware.py Dò phần cứng, chọn backend và model theo phần cứng
  audio_devices.py      Mic và thiết bị phát; loopback ủy quyền cho nền tảng
  capture.py            Mic thật + nguồn loopback của nền tảng
  resample.py           Chuyển 48/192kHz stereo về 16kHz mono
  vad_segmenter.py      Cắt luồng audio thành từng câu (webrtcvad)
  speaker.py            Nhận diện người nói (ECAPA) và giới tính (F0)
  stt.py, stt_backends/ Nhận dạng giọng nói: faster-whisper (CUDA/CPU), MLX (GPU Apple)
  mt.py                 Dịch máy (NLLB / MarianMT)
  tts.py                Tổng hợp giọng nói (Piper)
  tts_clone.py          Đọc bằng giọng người nói (Chatterbox, macOS)
  voice_bank.py         Kho mẫu giọng theo từng người nói
  playback.py           Phát audio ra thiết bị chỉ định
  models.py             Quản lý mô hình dùng chung giữa các chiều
  pipeline.py           Ghép toàn bộ bằng thread và queue
  gui.py                Giao diện Tkinter
  watch.py, console_run.py, selftest.py, route_check.py, diagnose.py   Các chế độ chạy và công cụ chẩn đoán
windows/                WASAPI loopback, CUDA, CHAY_APP.bat, requirements.txt
macos/                  Core Audio tap (Swift), setup_mac.sh, run.command, requirements.txt, bench/
evals/                  Bộ đo độ trễ, độ chính xác, sao chép giọng
docs/                   Tài liệu kiến trúc
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

- [`docs/architecture-windows-vs-macos.md`](docs/architecture-windows-vs-macos.md) — kiến trúc hiện tại, so sánh Windows/macOS, số đo thật và những gì chưa kiểm chứng.
- [`evals/README.md`](evals/README.md) — cách chạy các bài đo.
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
| STT trên Apple Silicon | [MLX-Whisper](https://github.com/ml-explore/mlx-examples) |
| Sao chép giọng (macOS) | [mlx-audio](https://github.com/Blaizzy/mlx-audio) + Chatterbox multilingual |

---

## Hướng phát triển

- [x] Chạy trên macOS Apple Silicon (bắt âm thanh hệ thống, STT trên GPU)
- [x] Giữ giọng người nói khi dịch sang tiếng Anh (Chatterbox, macOS; còn chậm, đang cải thiện)
- [ ] Kiểm chứng tắt tiếng gốc và loại trừ tiến trình ngoài thực tế trên macOS
- [ ] Cắt câu tốt hơn và nhận diện dạng luồng để giảm độ trễ (số đo trong tài liệu kiến trúc)
- [ ] Nhận diện tiếng Việt bằng Zipformer (nhanh ~9 lần, ngang Whisper turbo về WER trên giọng đọc sạch)
- [ ] Dịch bằng Apple Translation trên macOS 26
- [ ] Chạy lại và kiểm chứng trên Windows sau khi tách `windows/`; Intel NPU và CUDA cho sao chép giọng
- [ ] Ô "tên riêng giữ nguyên" (tên kênh, tên người) cho nhận diện và dịch
- [ ] Từ điển thuật ngữ riêng theo lĩnh vực để tăng độ chính xác
- [ ] Xuất biên bản cuộc họp ra tệp

---

## Giấy phép

Mã nguồn dự án phát hành theo giấy phép MIT. Các mô hình sử dụng có giấy phép
riêng — lưu ý NLLB-200 dùng giấy phép CC-BY-NC (phi thương mại) và Piper dùng
GPL, cần kiểm tra trước khi dùng cho mục đích thương mại. Chatterbox và mlx-audio dùng giấy phép MIT. Tính năng giữ giọng người nói tạo giọng nói mô phỏng người thật: chỉ nên dùng cho mục đích cá nhân, và cần sự đồng ý của người nói nếu chia sẻ âm thanh tạo ra.
