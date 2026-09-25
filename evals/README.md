# evals/ - bộ đo độ trễ, độ chính xác và sao chép giọng

Các script này **không thuộc app**; chúng đo trên máy thật để quyết định kiến trúc (xem
[`docs/architecture-windows-vs-macos.md`](../docs/architecture-windows-vs-macos.md)). Chạy trong `.venv`, từ thư mục gốc.

## Dữ liệu (không đưa lên git)

`evals/samples/` nằm trong `.gitignore`: âm thanh mẫu có bản quyền của người khác, chỉ dùng đo cục bộ.
Tải bằng `yt-dlp` (âm thanh 16kHz mono) hoặc từ bộ FLEURS:

```bash
yt-dlp --no-playlist -f bestaudio -x --audio-format wav --postprocessor-args "ffmpeg:-ar 16000 -ac 1" -o "evals/samples/<ten>.%(ext)s" "<url>"
```

FLEURS tiếng Việt (tập dev, 205MB): `data/vi_vn/audio/dev.tar.gz` và `data/vi_vn/dev.tsv` từ
`huggingface.co/datasets/google/fleurs`, giải nén vào `evals/samples/fleurs/`. Tập dev chỉ có giọng nam.

## Script

| Script | Đo gì | Cần |
|---|---|---|
| `replay.py <wav>` | Cắt câu bằng VAD thật, STT + dịch, mô phỏng hàng đợi để tính độ trễ đầu-cuối | file WAV 16kHz mono |
| `analyze.py <wav>` | Gom câu đúng theo timer của app, độ trễ từ lúc bắt đầu câu, quét tham số VAD | kết quả `replay.py` |
| `diagnose_vi.py <wav>` | Chiều Việt→Anh: câu bị lọc, độ tin cậy thấp, câu lặp, nhãn người nói, tên riêng | file WAV tiếng Việt |
| `wer_fleurs.py` | Độ chính xác tiếng Việt (WER/CER) của Zipformer và Whisper | FLEURS dev, `models/sherpa/` |
| `spike_sherpa.py <wav>` | Silero VAD và Zipformer-vi (sherpa-onnx) so với Whisper | `pip install sherpa-onnx`, `models/sherpa/` |
| `spike_streaming.py <wav>` | Mô phỏng nhận diện dạng luồng (LocalAgreement) | như trên |
| `spike_cloning.py [model...]` | Sao chép giọng: tốc độ, độ giống ECAPA, độ dễ hiểu | `pip install mlx-audio`, model MLX |
| `e2e_clone.py` | Kiểm tra tích hợp `DirectionPipeline` với sao chép giọng, không cần thiết bị âm thanh | như trên, FLEURS |
| `../macos/bench/bench_stt.py`, `bench_engine.py` | Tốc độ STT faster-whisper và MLX | ffmpeg |
| `../macos/bench/apple_ml_bench.swift` | Apple Translation và SpeechAnalyzer (macOS 26) | Xcode |

## Lưu ý

- Số đo ghi trong tài liệu kiến trúc là của **M2 Pro 32GB, macOS 26**; máy khác sẽ khác.
- `wer_fleurs.py` so văn bản đã chuẩn hoá (chữ thường, bỏ dấu câu); số viết bằng chữ hay chữ số có thể bị tính là lỗi.
- Độ giống giọng bằng ECAPA (chéo ngôn ngữ) chỉ là thước đo thô; **nghe thử** các file trong `evals/samples/cloning/`.
- Đừng in hay commit văn bản nhận diện của video có bản quyền; script chỉ lưu cục bộ trong `evals/samples/`.
