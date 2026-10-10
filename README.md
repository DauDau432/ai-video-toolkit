# AI Video Toolkit

Bộ công cụ để **AI agent trong IDE** tự làm video hướng dẫn, giải thích từ một chủ đề: viết kịch bản, sinh giọng đọc, dựng hình 1080p 60 fps khớp với lời, rồi tự kiểm tra trước khi giao cho bạn.

Bạn chỉ đưa chủ đề, trả lời vài câu hỏi, xem bản demo khoảng 1 phút và duyệt. Phần còn lại agent làm trên máy bạn, miễn phí.

## Dùng với AI agent trong IDE, không dùng AI chat

Bộ công cụ này viết cho các agent **chạy được lệnh và sửa file trên máy bạn**, ví dụ Claude Code, Cursor (Agent), Antigravity, Windsurf, GitHub Copilot (Agent mode), Cline.

Không dùng được với AI chat trên web (ChatGPT, Gemini, Claude.ai…): chat chỉ trả lời bằng chữ, không tự sinh giọng, không chạy được `videokit.py`, không xem được ảnh kiểm tra, nên không thể tự dựng và tự kiểm tra video.

## Có gì trong repo

| File | Dùng để |
|---|---|
| `Template.md` | Bộ quy trình và quy chuẩn agent phải theo: hỏi gì trước, viết tài liệu nào, đồng bộ lời với hình ra sao, khi nào dừng chờ duyệt. |
| `_tools/videokit.py` | Công cụ dựng video. Agent chỉ viết kịch bản thời gian (`docs/timeline.json`) và một trang HTML; công cụ tự đo giọng, dùng Whisper tìm từ khóa để canh hình đúng lúc, vẽ chuột và phím, render từng khung, trộn âm và kiểm tra. Chi tiết: [`_tools/README.md`](_tools/README.md). |
| `_tools/vk.js` | Thư viện nhỏ cho trang HTML (chuột, gõ phím, hiệu ứng theo thời gian). |
| `_tools/example/` | Dự án mẫu chạy được ngay. |
| `clean_workspace.py` | Cất dự án video cũ vào `_archive/` (không xóa gì) và tạo thư mục trống cho video mới. |
| `_models/README.md` | Ghi chú về model Whisper (model tải riêng, không nằm trong repo). |

## Cài đặt (một lần)

Cần Windows 10/11, Python 3.11 trở lên, khoảng 5 GB trống. Card NVIDIA giúp chạy nhanh hơn nhưng không bắt buộc.

1. Tải repo:

   ```bash
   git clone https://github.com/DauDau432/ai-video-toolkit.git
   ```

2. Cài ffmpeg (bản full) và thêm vào PATH, rồi mở lại IDE:

   ```bash
   winget install Gyan.FFmpeg
   ```

3. Mở thư mục repo trong IDE và nhắn agent:

   ```
   Chạy python _tools/videokit.py setup và xử lý đến khi máy sẵn sàng.
   ```

   Lệnh `setup` tự cài các thư viện Python (thêm thư viện CUDA nếu có card NVIDIA), Chromium để render, tải model Whisper large-v3 (2,9 GB, một lần) vào `_models/`, rồi chạy thử từng thứ. Thấy dòng "Máy đã sẵn sàng làm video." là xong. Tự chạy cũng được, kết quả như nhau.

   Agent cũng phải chạy lại lệnh này đầu mỗi phiên làm video (Template Giai đoạn 0), nên thiếu gì sẽ lộ ra từ đầu chứ không phải giữa lúc dựng.

Nhạc nền, hiệu ứng âm thanh của từng video do agent tải hoặc tạo vào `assets/` của video đó (Template mục 7). Font trong `assets/fonts/` thì dùng chung: tải một lần, `clean_workspace.py` giữ lại cho video sau. Nhạc nền được agent chọn theo chủ đề từng video từ thư viện miễn phí Mixkit (`videokit.py music`), không phải một bản nhạc dùng chung. Trước khi dựng, `videokit.py` dừng nếu thiếu file nào và chặn mọi thứ tải từ mạng, nên agent buộc phải chuẩn bị đủ trên máy trước.

## Làm một video

Mở **thư mục repo** trong IDE (agent phải làm việc ở đúng thư mục này), rồi nhắn cho agent:

**1. Bắt đầu**

```
Đọc Template.md và _tools/README.md, làm theo đúng quy trình trong đó.
Chủ đề video: <chủ đề của bạn>
```

Agent sẽ gửi một lượt câu hỏi (mục 14.1: thời lượng, nền tảng đăng, giọng nam/nữ, phong cách…). Mỗi câu có đề xuất sẵn; câu nào đồng ý thì trả lời "ok".

**2. Xem demo**

Agent viết tài liệu trong `docs/`, sinh giọng, dựng bản demo khoảng 1 phút ở `output/preview/demo.mp4` kèm `sync-report.md`, rồi **dừng lại chờ bạn**. Bạn:

- Xem `demo.mp4` trên điện thoại hoặc máy tính.
- Đọc `KICH-BAN.md` ở thư mục gốc: lời thoại, cách đọc, cách tự sửa.
- Muốn sửa gì thì nhắn agent sửa rồi dựng lại demo.

**3. Duyệt và dựng bản đầy đủ**

```
ok duyệt, dựng bản đầy đủ
```

Bản cuối nằm ở `output/final/<tên-video>-16x9.mp4` (hoặc `9x16`), kèm nội dung đăng (tiêu đề, mô tả, hashtag) cho các nền tảng bạn đã chọn.

**4. Sang video mới**

Chạy `python clean_workspace.py` (hoặc file `clean_workspace.exe` nếu bạn tự đóng gói), chọn mục 2. Video cũ được cất vào `_archive/<thời gian>_<tên>/`; `Template.md`, `_tools/`, `_models/` và font trong `assets/fonts/` giữ nguyên.

## Khi agent làm sai

`videokit.py` tự bắt phần lớn lỗi kỹ thuật và trả mã khác 0 khi không đạt:

- Máy thiếu công cụ hoặc dự án thiếu file (giọng, nhạc, hiệu ứng, HTML).
- Hình lệch lời quá ±150 ms.
- Thao tác không hiện ra trên màn hình.
- Lẫn giọng khác (ví dụ giọng nữ lẫn trong giọng nam).
- Hình giật ở chỗ nối.
- HTML tải font hay ảnh từ mạng.
- Sai độ phân giải, fps, âm lượng.

Agent hay quên quy định khi làm lâu. Khi thấy sai, nhắc đúng mục trong Template, ví dụ:

```
Bạn vi phạm Template mục 4 (hình không đi trước lời): nút đăng ký hiện khi lời còn đang tóm tắt. Sửa lại, chạy videokit demo, chờ chạy xong, gửi tôi số liệu trong sync-report.md.
```

Một vài điều nên yêu cầu agent:

- Chạy lệnh dựng và **chờ đến khi xong**, không báo "đang render, chờ chút".
- Chỉ báo những gì đã kiểm tra thật, kèm số liệu trong báo cáo.
- Không tự dựng bản đầy đủ khi bạn chưa duyệt demo.

## Thư mục khi đang làm video

```
Template.md          quy trình (không sửa khi đang làm video)
KICH-BAN.md          bản tóm tắt cho bạn đọc
_tools/  _models/    công cụ và model dùng chung
docs/                tài liệu của agent: kịch bản, lời thoại, timeline.json
assets/              giọng, nhạc, hiệu ứng, font, trang HTML
scripts/             script riêng của video (ví dụ sinh giọng)
output/preview/      demo.mp4, sync-report.md, ảnh kiểm tra
output/final/        video hoàn chỉnh
tmp/                 file tạm, xóa được
```

Chỉ `Template.md`, `_tools/`, `clean_workspace.py` và các file README được đưa lên git. Dự án video, model và `_archive/` ở lại trên máy (xem `.gitignore`).
