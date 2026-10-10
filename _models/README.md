# Model dùng chung cho mọi video

Thư mục này không bị tool dọn dẹp chuyển đi. Dùng lại, không tải lại. Chưa có model thì `_tools/videokit.py` tự tải ở lần chạy đầu (từ Hugging Face `Systran/faster-whisper-large-v3`).

| Thư mục | Model | Dùng cho |
|---|---|---|
| `faster-whisper-large-v3/` | Whisper large-v3 (bản faster-whisper, 2,9 GB) | Lấy mốc thời gian từng từ, nghe lại giọng đọc để bắt lỗi (Template mục 4.1, 6.2) |

Đã cài sẵn: `faster-whisper`, `av<19` (bản 19 không chạy được với faster-whisper 1.2.1), `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`. Chạy bằng GPU RTX 4060, khoảng 1 giây mỗi đoạn thoại.

Cách dùng: phải thêm thư mục DLL của CUDA vào PATH **trước khi** import, nếu không sẽ lỗi `cublas64_12.dll is not found`:

```python
import glob, os, nvidia
for d in glob.glob(os.path.join(list(nvidia.__path__)[0], "*", "bin")):
    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

from faster_whisper import WhisperModel

model = WhisperModel("_models/faster-whisper-large-v3", device="cuda", compute_type="float16")
segments, _ = model.transcribe("assets/voice/s1.wav", language="vi", word_timestamps=True)
for seg in segments:
    for w in seg.words:
        print(w.start, w.end, w.word)
```

Không có GPU thì dùng `device="cpu", compute_type="int8"`.

Tìm chỗ ngắt sai: Whisper hay gộp khoảng lặng vào từ, nên đo khoảng lặng bằng ffmpeg rồi đối chiếu với mốc thời gian từ:

```
ffmpeg -i assets/voice/s1.wav -af silencedetect=noise=-35dB:d=0.15 -f null -
```
