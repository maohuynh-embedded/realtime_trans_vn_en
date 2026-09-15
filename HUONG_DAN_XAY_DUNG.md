# Hướng dẫn xây dựng App Phiên Dịch Cuộc Họp (Anh ⇄ Việt, chạy offline) — bản cập nhật

> Bản này cập nhật từ tài liệu gốc sau khi đã **triển khai và đo đạc thực tế**.
> Các con số hiệu năng trong đây là đo được trên máy thật, không phải ước lượng.
> Chỗ nào chưa kiểm chứng được đều ghi rõ.

---

## 1. Kiến trúc tổng thể

```
[Zoom/Teams/Meet phát ra loa/tai nghe]
        │  bắt bằng WASAPI loopback (có sẵn trong Windows, không cần driver)
        ▼
[1] Capture → [2] VAD → [2b] Nhận diện người nói → [3] STT → [4] MT → [5] TTS → [5b] Nhuộm giọng → [6] Phát
        │
        ▼
   [7] GUI: 2 khung song song, nhãn "Người 1 (nam)" / "Người 2 (nữ)"
```

Chiều ngược lại (bạn nói → đối tác nghe tiếng Anh) dùng **mic thật** làm nguồn,
và phát kết quả vào một **mic ảo** mà app họp lấy làm micro (xem mục 2b).

### 1b. Hai hồ sơ phần cứng

App tự dò phần cứng (`app/hardware.py`) và tự chọn cấu hình — **cùng một bộ code
chạy tối ưu trên cả hai máy**, không phải sửa gì khi đổi máy:

| | Máy có GPU NVIDIA | Máy công ty (i7-1270P, Intel UHD) |
|---|---|---|
| STT | Whisper `medium`, CUDA, float16 | Whisper `small`/`base`, CPU int8 hoặc OpenVINO |
| MT | NLLB-600M trên GPU | NLLB-600M hoặc MarianMT trên CPU |
| Giữ giọng gốc | Được (mục 3.5b) | Không nên (quá chậm) |
| Quyền admin | Có | Không |

---

## 2. Bắt âm thanh cuộc họp (không cần VB-CABLE)

Dùng **WASAPI loopback** qua **PyAudioWPatch** — một API ghi âm có sẵn trong
Windows Core Audio, cho phép "nghe lại" đúng những gì đang phát ra loa/tai nghe.
Không phải driver, không cần quyền admin, chỉ cần `pip install`.

Loopback device trả về theo định dạng thiết bị phát (thường **48kHz hoặc
192kHz, stereo**), khác với **16kHz mono** mà VAD/Whisper cần → **bắt buộc phải
resample + downmix** trước khi đưa vào VAD. Quên bước này là nguyên nhân phổ
biến nhất khiến Whisper nghe sai hoàn toàn.

### 2b. Đưa tiếng Anh NGƯỢC LẠI vào Zoom (cho chiều Việt→Anh)

Đây là điểm mà tài liệu gốc chưa nói tới: **WASAPI loopback chỉ bắt được âm
thanh ra, nó không bơm được audio vào Zoom làm micro.** Chiều Việt→Anh cần một
đường dẫn riêng. Ba phương án, đã kiểm tra thực tế:

| Phương án | Kết quả kiểm tra |
|---|---|
| VB-CABLE | Cần quyền admin — dùng được ở máy nhà, không dùng được ở máy công ty |
| Loopback phần cứng của sound card USB | **Đã test: không có.** Phát tone 440Hz ra card, mic không nhận lại (chỉ thấy ù 50Hz) |
| **Stereo Mix (Realtek)** | **Hoạt động.** Có sẵn trong driver, thường bị Disabled, bật lên là dùng được |
| Cáp loopback 3.5mm vật lý | Luôn đúng, tốn vài chục nghìn |

**Bật Stereo Mix:** `Win+R` → `mmsys.cpl` → tab **Recording** → chuột phải vùng
trống → tích **Show Disabled Devices** → chuột phải **Stereo Mix** → **Enable**.

**Bẫy quan trọng đã gặp:** Stereo Mix chỉ nghe được âm thanh phát ra **chính
card nó thuộc về**. `Stereo Mix (Realtek)` **không** nghe được tiếng phát ra một
sound card USB khác. Phải ghép đúng cặp cùng card, nếu không sẽ không có tín
hiệu nào đi qua dù cả hai thiết bị đều hoạt động bình thường.
`app/audio_devices.py: suggest_output_for_virtual_mic()` làm việc ghép cặp này.

Kiểm chứng tự động bằng `python main.py --check-route`: script phát một câu
tiếng Anh, ghi lại từ mic ảo, rồi cho Whisper đọc lại — **in ra đúng những gì
đối tác sẽ nghe thấy**.

---

## 3. Các khối xử lý

### 3.1. Audio Capture
- **PyAudioWPatch** cho loopback (âm thanh cuộc họp), **sounddevice** cho mic
  thật và cho phát ra. Dùng song song 2 thư viện là bình thường.
- Chế độ callback/stream liên tục, callback **chỉ đẩy dữ liệu vào queue**,
  không xử lý nặng tại đó.
- **Lọc thiết bị:** Windows liệt kê cả endpoint *không có thiết bị cắm vào*
  (jack tai nghe đang trống) — mở ra sẽ báo `Invalid device [-9996]`. Phải
  **thử mở thật** từng thiết bị mới biết dùng được không. Cũng nên bỏ các alias
  ảo (`Primary Sound Driver`, `Microsoft Sound Mapper`) và host API WDM-KS.

### 3.2. VAD — cắt câu
- **webrtcvad** (Windows dùng `webrtcvad-wheels`), frame 30ms @ 16kHz.
- Thuật toán collector 2 trạng thái: ring buffer ngắn (~300ms) để bắt đầu câu,
  ring buffer dài hơn để kết thúc câu, cộng ngưỡng cắt cưỡng bức.
- **Tham số quan trọng nhất là ngưỡng im lặng kết thúc câu** — đánh đổi trực tiếp:
  - 450ms: trễ thấp nhưng **cắt vụn**, ra các mảnh vô nghĩa kiểu
    "Do you have" / "I also" / "Maybe I can tra-", dịch ra thành rác.
  - **700ms (khuyến nghị)**: khoảng nghỉ giữa 2 câu thường >700ms, còn ngập
    ngừng giữa câu chỉ 200–500ms, nên tách được khá sạch.

### 3.2b. Nhận diện người nói + giới tính (mới)

Trong phỏng vấn/cuộc họp, cần biết **ai đang hỏi, ai đang trả lời**.

- **Giới tính**: ước lượng từ cao độ giọng (F0) bằng tự tương quan — không cần
  model, chạy tức thì. Nam ~85–180Hz, nữ ~165–255Hz. Vùng 155–190Hz là chồng
  lấn, nên trả về `?` thay vì đoán bừa. *Đo thực tế: đúng 4/5 giọng, 1 giọng rơi
  đúng vùng chồng lấn.*
- **Người nói**: gom cụm trực tuyến theo đặc trưng giọng.
  - **Đã thử tự chế đặc trưng (phổ + F0) và THẤT BẠI** — nó gộp cả giọng nam
    96Hz với giọng nữ 195Hz vào cùng một người. Ghi lại ở đây để đừng ai mất
    thời gian làm lại.
  - **Dùng ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`, ~80MB) thay thế:
    *đo thực tế 7/7 đúng, phân biệt được cả 2 giọng nam khác nhau (96Hz vs
    150Hz), chỉ tốn 62ms/câu.*
  - Gom cụm bằng khoảng cách cosine với ngưỡng ~0.45.

### 3.3. Speech-to-Text

- **faster-whisper** (CTranslate2). Cố định `language=` để bỏ bước tự nhận
  diện ngôn ngữ. Tắt `vad_filter` vì đã tự cắt câu ở bước 3.2.
- **Đo thực tế trên cùng một đoạn audio 9.6s:**

| Cấu hình | Thời gian | Ghi chú |
|---|---|---|
| CPU, `small`, int8 | 1.68s | cấu hình mặc định của tài liệu gốc |
| CPU, `base`, int8 | 0.52s | nhanh hơn nhưng kém chính xác |
| **GPU CUDA, `medium`, float16** | **0.40s** | **vừa nhanh hơn vừa chính xác hơn hẳn** |
| OpenVINO CPU, `tiny` | 0.67s | xem 3.3b |

Kết luận quan trọng: nếu có GPU NVIDIA thì `medium` trên GPU **thắng mọi mặt** —
không phải đánh đổi tốc độ lấy độ chính xác nữa.

### 3.3b. Chạy STT/MT qua OpenVINO trên GPU tích hợp Intel (mới)

Dành cho máy công ty (i7-1270P + Intel UHD Graphics, không có GPU rời).
OpenVINO cho phép đẩy tải sang iGPU thay vì chỉ dùng CPU.

**Cài đặt:**

```bash
pip install "openvino>=2024.4" "optimum-intel[openvino]"
```

**Xem OpenVINO nhìn thấy thiết bị nào:**

```python
import openvino as ov
core = ov.Core()
print(core.available_devices)            # ví dụ: ['CPU', 'GPU']
print(core.get_property("GPU", "FULL_DEVICE_NAME"))
```

Trên máy công ty, `GPU` chính là Intel UHD Graphics.

**Whisper qua OpenVINO — đã kiểm chứng chạy được:**

```python
from optimum.intel import OVModelForSpeechSeq2Seq
from transformers import AutoProcessor

model = OVModelForSpeechSeq2Seq.from_pretrained(
    "openai/whisper-small", export=True, compile=False
)
model.to("GPU")        # "GPU" = Intel iGPU trên máy công ty; "CPU" nếu muốn
model.compile()
processor = AutoProcessor.from_pretrained("openai/whisper-small")
```

Export chỉ làm **một lần** (đo: 34s với `whisper-tiny`), sau đó
`model.save_pretrained(...)` để lần sau nạp thẳng IR, không export lại.

**Lưu ý đã gặp — xung đột phiên bản:** export **seq2seq** (MarianMT, NLLB) qua
`optimum-intel` hiện yêu cầu `transformers <= 4.57.6`. Với `transformers` 5.x sẽ
báo:

```
ValueError: The current version of Transformers does not allow for the export
of the model. Maximum required is 4.57.6, got: 5.5.4
```

Cách xử lý: hoặc ghim `transformers==4.57.6` cho môi trường máy công ty, hoặc
**chỉ dùng OpenVINO cho Whisper** và để phần dịch chạy CPU bình thường — bước
dịch vốn chỉ tốn 0.1–0.5s nên lợi ích tăng tốc không đáng kể, còn STT mới là
bước nặng.

> **Chưa kiểm chứng được:** máy dùng để phát triển có CPU i5-13400F (hậu tố "F"
> = không có iGPU), nên đường dẫn *Intel UHD Graphics* cụ thể chưa chạy thử
> được. Phần stack OpenVINO (cài đặt, liệt kê thiết bị, export và suy luận
> Whisper) thì đã chạy thật và cho kết quả đúng.

### 3.4. Machine Translation

Tài liệu gốc khuyến nghị **MarianMT** (`opus-mt-en-vi`). **Sau khi dùng thực tế,
nên đổi sang NLLB.** Đo trên đúng loại câu công việc:

| Câu gốc | MarianMT | NLLB-200-distilled-600M |
|---|---|---|
| quarterly results | kết quả **phần trăm** ✗ | kết quả **quý** ✓ |
| revenue numbers for Q3 | **số nhân** với Q3 ✗ | **doanh thu** cho quý 3 ✓ |
| the integration | sự **liên kết** ✗ | việc **tích hợp** ✓ |
| dependency issue in staging | "Nó bị chặn bởi một vấn đề" (mất sạch nghĩa) ✗ | "vấn đề **phụ thuộc**" ✓ |

Đánh đổi: NLLB chậm hơn (0.45s so với 0.10s) nhưng đáng.

**Bắt buộc chặn lỗi lặp vô hạn.** Model seq2seq nhỏ hay sinh ra chuỗi lặp kiểu
`"Các bạn phong phong phong phong phong..."`. Đặt `no_repeat_ngram_size=4` và
`repetition_penalty=1.15`.

Vẫn **không dùng argos-translate** — gói `en_vi` đã bị gỡ do lỗi Stanza.

### 3.5. Text-to-Speech

**Piper** (`piper-tts`), giọng Việt `vi_VN-vais1000-medium`, giọng Anh
`en_US-lessac-medium`, tải từ `rhasspy/piper-voices`.

API Piper 1.8 nhận tham số qua `SynthesisConfig(length_scale=...)` và trả audio
theo generator các chunk (`audio_int16_bytes`, `sample_rate`, `sample_channels`).

*Đo thực tế: tổng hợp chỉ 0.1–0.2s, nhưng **thời gian PHÁT ra là 6.6s** cho bản
dịch của một câu 9.6s.* Xem mục 4 về hệ quả của con số này.

### 3.5b. Giữ giọng gốc người nói (voice cloning / tone color transfer) — tuỳ chọn nâng cao

- Nếu muốn bản dịch tiếng Việt nghe "giống" giọng đối tác thay vì giọng Piper
  trung tính cố định, thêm 1 bước **Tone Color Converter** giữa TTS và bước phát
  audio. Ý tưởng: tách rời "nội dung nói" khỏi "chất giọng" — Piper vẫn tạo
  audio tiếng Việt như bình thường (nội dung), sau đó một bước riêng "nhuộm" lại
  timbre của audio đó theo giọng đối tác (chất giọng). Bước nhuộm giọng này
  không quan tâm ngôn ngữ, nên hoạt động tốt dù Piper nói tiếng Việt còn giọng
  mẫu là tiếng Anh.
- Thư viện khuyến nghị: **OpenVoice V2** (`myshell-ai/OpenVoice`, MIT license).
  Kiến trúc tách 2 tầng: TTS nền (ở đây thay bằng Piper) tạo audio giọng trung
  tính, sau đó `ToneColorConverter` chuyển timbre của audio đó sang giọng mục tiêu.
- Các bước:
  1. Đầu cuộc họp, ghi lại ~10–20 giây giọng đối tác (qua chính loopback đã có
     sẵn), lưu thành `reference.wav` — càng sạch tiếng ồn càng tốt.
  2. Tính speaker embedding 1 lần bằng
     `se_extractor.get_se(reference.wav, tone_color_converter)` → ra vector
     `target_se`. Chỉ cần làm 1 lần, không tính lại mỗi câu.
  3. Với mỗi câu: sau khi Piper xuất audio, gọi
     `tone_color_converter.convert(audio_src_path=..., src_se=..., tgt_se=target_se)`
     trước khi đẩy sang bước phát (mục 3.6).
- Cài đặt: `git clone` repo `myshell-ai/OpenVoice`, `pip install -e .`, tải
  checkpoint `checkpoints_v2/converter` từ Hugging Face.
- **Tăng tốc bằng Intel UHD Graphics**: Intel có tài liệu chính thức hướng dẫn
  chạy OpenVoice (cả TTS nền lẫn ToneColorConverter) qua OpenVINO trên CPU/GPU
  Intel — nên bước này cũng chạy được trên GPU tích hợp thay vì chỉ CPU, giúp
  giữ tổng độ trễ pipeline trong khoảng chấp nhận được.
- **Kỳ vọng thực tế**: đây là chuyển giọng cross-lingual (giọng gốc tiếng Anh áp
  lên câu tiếng Việt) chạy gần real-time — chất lượng thường ở mức "nghe hao hao
  giống, nhận ra đặc trưng giọng" chứ khó đạt độ giống gần như bản sao. Chất
  lượng phụ thuộc nhiều vào độ dài/độ sạch của mẫu giọng tham chiếu.
- Không dùng **RVC** cho việc này — RVC cần train riêng 1 model nhỏ cho từng
  giọng trước (tốn thời gian chuẩn bị, cần vài phút dữ liệu), không hợp với việc
  đối tác thay đổi liên tục giữa các cuộc họp.
- **Phạm vi sử dụng**: bước này chỉ áp cho chiều **Anh→Việt**, tức bản dịch phát
  ra tai nghe riêng của bạn để hỗ trợ nghe hiểu cá nhân — không gửi lại cho đối
  tác hay bất kỳ ai khác. **Không áp bước nhuộm giọng cho chiều Việt→Anh**, vì
  chiều đó audio được gửi tới người khác; phát giọng nhái của một người thật tới
  bên thứ ba là chuyện khác hẳn về bản chất.

> **Chưa kiểm chứng:** mục 3.5b chưa được cài và chạy thử trong project này.
> Các bước trên là thiết kế đề xuất, cần thử nghiệm và đo độ trễ thực tế trước
> khi đưa vào dùng trong cuộc họp thật.

### 3.6. Phát audio ra

**sounddevice**, chỉ định rõ thiết bị, phát tuần tự từng câu.

**Hai cái bẫy đã gặp thực tế:**

- Piper trả audio **22050Hz** nhưng thiết bị chạy 44100/48000Hz → `Invalid
  sample rate [-9997]`. **Phải resample về đúng sample rate của thiết bị.**
- Thiết bị có thể mở lỗi giữa chừng → phải bắt exception và lùi về thiết bị mặc
  định, **không để một lỗi phát audio giết cả thread xử lý** (triệu chứng: app
  vẫn chạy, vẫn hiện text, nhưng im lặng hoàn toàn).

---

## 4. Ghép pipeline & xử lý đa luồng

Tách thành các thread nối bằng `queue.Queue`:

1. **Audio callback** — chỉ đẩy frame vào queue.
2. **Thread VAD** — resample + downmix, chạy webrtcvad, xuất từng câu.
3. **Thread worker** — nhận diện người nói → STT → MT → TTS → phát.
4. **GUI** — polling định kỳ (`root.after`), **không** update GUI từ thread khác.

### 4b. Chống độ trễ dồn (quan trọng)

Đây là vấn đề lớn nhất gặp phải khi dùng thật. Phân tích độ trễ một câu dài:

| Bước | Thời gian |
|---|---|
| Chờ im lặng để cắt câu | 0.7s |
| STT | 0.4–1.7s |
| Dịch | 0.5s |
| **Phát bản dịch ra tiếng** | **6.6s** |

**Thủ phạm là bước phát, không phải STT.** Đọc tiếng Việt mất gần bằng độ dài
câu gốc. Vì trong lúc phát app phải tạm ngưng thu (xem 4c), nội dung mới dồn vào
queue và **độ trễ tăng dần vô hạn**.

Ba cách xử lý, nên dùng cả ba:

- **Bỏ câu cũ khi tụt lại quá ngưỡng** (ví dụ 6s): nghe bản dịch của chuyện đã
  xảy ra 30 giây trước thì vô nghĩa — thà bỏ vài câu còn hơn trễ dồn.
- **Chỉnh tốc độ đọc** (`length_scale` < 1) để rút ngắn thời gian phát.
- **Chế độ phụ đề** (tắt đọc thành tiếng): đọc chữ trên màn hình thì không có độ
  trễ phát nào cả. **Đây là chế độ đúng nhất cho việc xem video/họp một chiều.**

Sự thật cần chấp nhận: **chế độ đọc thành tiếng không thể theo kịp người nói
liên tục**, vì đọc mất thời gian ngang câu gốc. Đây là giới hạn bản chất, không
phải lỗi cấu hình.

### 4c. Tự tắt thu khi đang đọc — cho máy chỉ có 1 loa

Nếu bản dịch phát ra chính thiết bị đang bị loopback bắt, nó sẽ bị bắt lại rồi
dịch tiếp → vòng lặp vô tận. Xử lý bằng cờ "đang phát": trong lúc phát thì bỏ
qua dữ liệu thu được, cộng thêm ~250ms đệm sau khi phát xong cho audio thoát hết
khỏi buffer thiết bị.

Nhờ cơ chế này, **máy chỉ có 1 loa duy nhất vẫn dùng được**. Đánh đổi: vài giây
đang đọc thì không nghe được nguồn.

---

## 5. Giao diện

- **Chọn chế độ**: "Xem video / nghe 1 chiều" vs "Họp 2 chiều".
- Mỗi chiều: chọn nguồn/đích, nút Bật/Tắt, **Tạm dừng** (khi bạn quay sang nói
  chuyện riêng), checkbox **Đọc thành tiếng**.
- Nút **Tự dò** thiết bị đang có âm thanh — giải quyết dứt điểm câu hỏi "âm
  thanh của tôi đang phát ra thiết bị nào".
- Hiển thị **độ trễ thực tế** từng câu và số câu bị bỏ.
- Nhãn người nói: `Người 1 (nam):` / `Người 2 (nữ):`.
- Dòng cảnh báo khi cấu hình thiết bị có nguy cơ vòng lặp.

---

## 6. Thứ tự nên làm khi tự code

1. Liệt kê & chọn thiết bị; **thử mở thật** để loại thiết bị không cắm.
2. Capture + phát lại nguyên bản (chưa dịch) — xác nhận đúng luồng.
3. Ghép webrtcvad, in ra mỗi khi cắt được 1 câu, tinh chỉnh ngưỡng im lặng.
4. Ghép faster-whisper, đo độ trễ, chọn cấu hình theo phần cứng.
5. Ghép MT, in bản dịch.
6. Ghép Piper, **nhớ resample về sample rate của thiết bị**.
7. Test toàn bộ với video YouTube tiếng Anh.
8. Cuối cùng mới làm GUI.

Bổ sung: nên viết sớm một lệnh **tự kiểm tra toàn bộ** (`--test`) in bảng
đạt/không đạt kèm việc cần làm tiếp. Rất đáng công, vì mỗi lần đổi máy hoặc
khởi động lại chỉ cần chạy 1 lệnh là biết còn chạy được không.

---

## 7. Cài đặt

Python 3.10–3.12 (64-bit). Nền chung:

```bash
pip install PyAudioWPatch sounddevice numpy scipy webrtcvad-wheels faster-whisper transformers sentencepiece torch piper-tts speechbrain
```

### 7a. Máy có GPU NVIDIA

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126 --force-reinstall
```

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

**Bẫy:** `pip install torch --index-url ...` mà không có `--force-reinstall` sẽ
báo "Requirement already satisfied" và **giữ nguyên bản CPU**.

**Bẫy 2:** DLL cuBLAS/cuDNN cài qua pip nằm trong `site-packages/nvidia/*/bin`,
không nằm trong PATH → CTranslate2 không tìm thấy. Phải gọi
`os.add_dll_directory()` cho các thư mục đó trước khi tạo `WhisperModel`.

### 7b. Máy công ty (Intel UHD Graphics, không admin)

```bash
pip install "openvino>=2024.4" "optimum-intel[openvino]"
```

Nếu cần export seq2seq (MarianMT/NLLB) sang OpenVINO thì phải ghim
`transformers==4.57.6` (xem 3.3b).

Tất cả đều là gói `pip` trong virtualenv — **không cần quyền admin**.

### 7c. Model cần tải (một lần, cần mạng)

| Model | Vai trò | Dung lượng |
|---|---|---|
| Whisper `medium` / `small` | STT | 1.5GB / 500MB |
| `facebook/nllb-200-distilled-600M` | dịch 2 chiều | 2.5GB |
| `vi_VN-vais1000-medium` (Piper) | giọng Việt | 60MB |
| `en_US-lessac-medium` (Piper) | giọng Anh | 60MB |
| `speechbrain/spkrec-ecapa-voxceleb` | nhận diện người nói | 80MB |

---

## 8. Các lỗi/vướng mắc thường gặp

**Thiết bị âm thanh**

- `webrtcvad` không build được trên Windows → dùng `webrtcvad-wheels`.
- `Invalid device [-9996]` khi phát → thiết bị được liệt kê nhưng **không có gì
  cắm vào** (jack tai nghe trống), hoặc là endpoint WDM-KS. Phải thử mở thật để lọc.
- `Invalid sample rate [-9997]` → Piper ra 22050Hz mà thiết bị chạy 44100Hz.
  Resample về sample rate của thiết bị.
- **App chạy, hiện text, nhưng không có tiếng nào** → thread worker đã chết vì
  lỗi phát audio. Phải bọc try/except và lùi về thiết bị mặc định.
- Mic ảo (Stereo Mix) không nhận được gì dù đã Enable → **ghép sai cặp card**.
  Stereo Mix của Realtek chỉ nghe được tiếng phát ra card Realtek.
- Sau khi khởi động lại máy, **index thiết bị đổi** → đừng hard-code index,
  luôn tra theo tên.

**Chất lượng**

- Whisper nghe sai/nhiễu → gần như chắc chắn quên resample 48kHz→16kHz hoặc
  quên downmix stereo→mono.
- Bản dịch ra các mảnh vụn vô nghĩa ("Do you have", "I also") → ngưỡng im lặng
  cắt câu quá ngắn, nâng lên ~700ms.
- Bản dịch lặp vô hạn ("phong phong phong...") → đặt `no_repeat_ngram_size=4`
  và `repetition_penalty`.
- Dịch sai thuật ngữ công việc ("quarterly" → "phần trăm") → đổi MarianMT sang NLLB.
- Nhận diện người nói gộp nhầm nam với nữ → **đừng tự chế đặc trưng giọng**,
  dùng ECAPA-TDNN.

**Hiệu năng**

- Độ trễ tăng dần theo thời gian → queue dồn ứ. Bỏ câu cũ khi tụt quá ngưỡng,
  và/hoặc chuyển sang chế độ phụ đề.
- Đã cài torch CUDA mà `torch.cuda.is_available()` vẫn False → pip giữ bản CPU
  cũ, cần `--force-reinstall`.
- GPU có mà vẫn chạy chậm → kiểm tra `device`/`compute_type` có đang là
  `cuda`/`float16` không; cấu hình CPU cũ (`int8`) sẽ không dùng GPU.

**Vòng lặp âm thanh**

- Nghe thấy bản dịch bị dịch lại → output trùng thiết bị đang bị loopback bắt.
  Hoặc chọn thiết bị khác, hoặc bật cơ chế tự tắt thu khi đang đọc (4c), hoặc bỏ
  tích "Đọc thành tiếng".

---

## Nguồn tham khảo

**Âm thanh**

- [PyAudioWPatch — WASAPI loopback, không cần VB-CABLE](https://github.com/s0d3s/PyAudioWPatch)
- [sounddevice](https://python-sounddevice.readthedocs.io/)
- [VB-CABLE](https://vb-audio.com/Cable/) — chỉ khi có quyền admin

**STT / MT / TTS**

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [Helsinki-NLP/opus-mt-en-vi](https://huggingface.co/Helsinki-NLP/opus-mt-en-vi)
- [Piper TTS — API Python](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
- [Gói en_vi bị gỡ khỏi Argos Translate](https://community.libretranslate.com/t/how-do-i-install-all-language-packages-why-does-the-vi-ones-fail-and-what-is-sbd/575)

**Nhận diện người nói**

- [SpeechBrain ECAPA-TDNN (VoxCeleb)](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)

**OpenVINO / Intel**

- [OpenVINO Toolkit](https://docs.openvino.ai/)
- [Optimum Intel — OpenVINO inference](https://huggingface.co/docs/optimum/intel/openvino/inference)

**Giữ giọng gốc**

- [OpenVoice V2 (myshell-ai/OpenVoice, MIT)](https://github.com/myshell-ai/OpenVoice)
