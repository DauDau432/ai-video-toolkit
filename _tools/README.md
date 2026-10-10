# _tools: bộ công cụ dựng video dùng chung

Thư mục này không bị tool dọn dẹp chuyển đi. **Bắt buộc dùng cho mọi video** (Template mục 4.1, 10.4). Không tự viết script render, trộn âm hay báo cáo đồng bộ khác.

Nguyên tắc: **giọng đọc có trước, hình dựng theo giọng.** Bạn chỉ viết 2 thứ:

1. `docs/timeline.json`: thứ tự đoạn giọng và các hành động, mỗi hành động gắn vào một **từ khóa trong lời đọc**, không ghi số giây.
2. Một file HTML có hàm `window.renderAtTime(t)` vẽ đúng trạng thái màn hình tại giây `t`.

Công cụ tự đo thời lượng giọng thật, dùng Whisper tìm từ khóa, tính thời điểm mọi hành động, render từng khung 60 fps, trộn âm, rồi nghe lại thành phẩm để đo độ lệch.

## Lệnh (chạy ở thư mục gốc dự án)

| Lệnh | Việc |
|---|---|
| `python _tools/videokit.py setup` | Kiểm tra máy, tự cài thư viện Python, Chromium, model Whisper, ACE-Step (sinh nhạc) còn thiếu rồi chạy thử. Chạy đầu mỗi phiên làm việc (Template Giai đoạn 0); chỉ làm tiếp khi in "Máy đã sẵn sàng làm video." |
| `python _tools/videokit.py timeline` | Tính timeline bản demo, in ra lời Whisper nghe được và giây của từng hành động. Chạy lệnh này trước tiên để sửa từ khóa. Thêm `--full` cho toàn bộ cảnh. |
| `python _tools/videokit.py still 12.5` | Chụp khung hình tại giây 12.5 vào `tmp/still_12.50.png` để xem nhanh bố cục, cỡ chữ. Thêm `--full` để dùng thời gian của bản đầy đủ. |
| `python _tools/videokit.py music "dark cyber ambient, synth bass, no vocals" --seconds 180 --out assets/bgm/nhac.wav` | Sinh nhạc nền không lời bằng ACE-Step 1.5 trên máy (10 đến 470 giây), chuẩn hóa âm lượng, in seed. Thêm `--seed N` để sinh lại đúng bản cũ, `--bpm N` để ép nhịp. Lần đầu tự cài ACE-Step vào `_models/ace-step/` và tải model (khoảng 10 GB). Mô tả viết tiếng Anh, hợp chủ đề (Template mục 6). |
| `python _tools/videokit.py demo` | Dựng `output/preview/demo.mp4` từ các cảnh trong `demo_scenes`, kèm `output/preview/sync-report.md` và ảnh trước/sau ở `output/preview/sync-frames/`. |
| `python _tools/videokit.py full` | Dựng `output/final/<tên>-16x9.mp4` (hoặc `9x16`). Từ chối chạy nếu chưa có `docs/approval.md` (Template mục 10.1). Báo cáo ở `output/preview/sync-report-full.md`. |

Mã thoát: 0 = đạt, 1 = lỗi đầu vào (thiếu file, không tìm thấy từ khóa…), 2 = dựng xong nhưng kiểm tra KHÔNG ĐẠT. Gặp 1 hoặc 2 phải sửa rồi chạy lại, không được báo người dùng là xong.

Ví dụ chạy được ngay: `_tools/example/` (vào thư mục đó rồi chạy `python ../videokit.py demo`).

## Giọng đọc

Mỗi đoạn là một file `assets/voice/<id>.wav` (id trùng cột ID trong `docs/voiceover.md`). Sinh giọng xong, nghe kiểm tra theo Template mục 6.2, rồi mới viết timeline. Sửa giọng thì chỉ cần chạy lại lệnh; mọi mốc thời gian tự tính lại.

Cả video một giọng. Script sinh giọng phải sinh lại file khi lời, giọng hoặc tốc độ đổi (không bỏ qua chỉ vì file đã có). Trước khi dựng, công cụ đo cao độ mọi đoạn; đoạn lệch hẳn số đông (ví dụ giọng nữ lẫn trong giọng nam) làm lệnh dừng với mã 1.

## docs/timeline.json

```json
{
  "project_name": "Bao mat VPS Linux",
  "html": "assets/templates/video.html",
  "width": 1920, "height": 1080, "fps": 60,
  "demo_scenes": ["scene_01", "scene_02"],
  "lead_in": 0.3,
  "segment_gap": 0.3,
  "scene_gap": 0.6,
  "bgm": {"file": "assets/bgm/nhac.wav", "volume": 0.25, "duck": 0.35},
  "scenes": [
    {
      "scene_id": "scene_01",
      "segments": ["s1", "s2", {"id": "s3", "gap_after": 1.0}],
      "actions": [
        {"id": "click_terminal", "type": "click", "target": "#terminal", "sfx": "assets/sfx/click.wav",
         "anchor": {"segment_id": "s1", "keyword": "khởi tạo", "offset": 0}},
        {"id": "type_cmd", "type": "type", "text": "journalctl -u ssh", "duration": 1.4, "sfx": "assets/sfx/key.wav",
         "anchor": {"segment_id": "s3", "keyword": "các con bot", "offset": -0.2}}
      ]
    }
  ]
}
```

| Trường | Ý nghĩa |
|---|---|
| `width`, `height`, `fps` | Mặc định 1920, 1080, 60. Video dọc: 1080 x 1920. Không đặt thấp hơn 1080p hoặc dưới 60 fps khi người dùng chưa đồng ý. |
| `lead_in`, `segment_gap`, `scene_gap` | Khoảng lặng (giây) trước đoạn đầu, giữa các đoạn, sau đoạn cuối mỗi cảnh. Chỉnh riêng một đoạn bằng `{"id": "s3", "gap_after": 1.0}`, riêng một cảnh bằng `"pause_after"`. |
| `bgm` | Nhạc nền tự lặp, tự giảm xuống `duck` lần khi có lời. `volume` để 0.25 (25%, người dùng đã chọn), không tự đặt thấp hơn khi người dùng chưa yêu cầu. Không có nhạc thì `null`. |
| `segments` | Thứ tự đoạn giọng trong cảnh. Cảnh nối tiếp nhau, không có giờ bắt đầu viết tay. |
| `actions[].id` | Tên duy nhất, HTML dùng tên này để lấy thời gian. |
| `actions[].type` | Chuột: `cursor_move`, `hover`, `click`, `double_click`, `right_click`, `drag`. Phím: `type`, `key`, `shortcut`. Khác: `reveal`, `zoom`, `scroll`… tùy bạn đặt. |
| `actions[].anchor` | `segment_id` + `keyword` (vài từ **đúng như Whisper nghe được**, xem lệnh `timeline`) + `offset` giây (âm = sớm hơn). Không có `keyword` thì dùng đầu đoạn, hoặc cuối đoạn với `"at": "end"`. |
| `actions[].duration` | Thời lượng (giây) của hành động. `type`: thời gian gõ hết `text`. |
| `actions[].target` | Bộ chọn CSS của phần tử chuột đi tới. Bắt buộc với loại chuột. `drag` thêm `to`. |
| `actions[].keys` | Chữ hiện trên phím cho `key` / `shortcut`, ví dụ `"Ctrl + C"`. |
| `actions[].sfx` | Tiếng hiệu ứng, đặt đúng lúc hành động. Với `type` có `text`: phát mỗi lần gõ một ký tự. Thêm `sfx_volume` (mặc định 0.6), `sfx_offset`. |
| `actions[].no_visual_change` | `true` nếu hành động cố ý không đổi hình (hiếm). Mặc định công cụ coi hành động không làm hình thay đổi là lỗi. |

## HTML

```html
<script>
window.renderAtTime = function (t) {
  const sc = VK.scene(t);                          // cảnh đang chiếu tại t
  // ẩn/hiện cảnh theo sc.scene_id
  title.style.opacity = VK.p(t, "title_in");       // 0..1, mượt, theo duration của action
  terminal.classList.toggle("focus", VK.on(t, "click_terminal"));  // true từ lúc click
  cmd.textContent = VK.typed(t, "type_cmd");       // chữ gõ dở, nhịp không đều như người thật
  caret.style.visibility = VK.caret(t) ? "visible" : "hidden";
};
</script>
```

Quy tắc:

- `renderAtTime(t)` chỉ phụ thuộc `t`. Gọi lại cùng `t` phải ra cùng hình; gọi lùi `t` cũng phải đúng.
- Không viết số giây cứng. Mọi mốc lấy từ `VK.*` hoặc `window.TIMELINE` (`TIMELINE.actions[id].start/end`, `TIMELINE.segments[id].start/end/words`, `TIMELINE.scenes`).
- Không dùng `setTimeout`, `setInterval`, `requestAnimationFrame`, CSS `transition`/`animation`, `Math.random()`, video hay GIF tự chạy. Công cụ tắt các thứ này khi render; hiệu ứng nào dựa vào chúng sẽ đứng im.
- Ảnh, font phải nằm trong `assets/` (khai báo `@font-face` trỏ tới file trong `assets/fonts/`, không dùng Google Fonts hay link mạng), nạp xong trước khi render (không đổi `src` ảnh trong `renderAtTime`; ẩn/hiện thay vì nạp mới).
- Màn hình mới chỉ hiện khi lời nói tới (Template mục 4): cảnh nhiều đoạn thoại thì đổi hình theo action neo vào từ khóa của từng đoạn, không bật sẵn mọi thứ từ đầu cảnh.
- Trang đúng bằng `width` x `height` px, không thanh cuộn.
- Con trỏ chuột, vòng sóng click và phím bấm hiện lên màn hình (keycap) do công cụ tự vẽ từ các action có `target` hoặc loại `key`/`shortcut`. HTML chỉ vẽ **kết quả** của thao tác (nút sáng, menu mở, chữ hiện). Cảnh không có action chuột thì không có con trỏ. Điểm xuất phát của chuột: `"cursor_start": [x, y]` trong cảnh.
- Con trỏ soạn thảo nhấp nháy dùng `VK.caret(t)` (chu kỳ 1 giây) để phần kiểm tra không nhầm là thay đổi.

Các hàm `VK`: `p(t, id, dur?)` tiến độ 0..1, `on(t, id)`, `typed(t, id, text?)`, `caret(t)`, `scene(t)`, `ease(x)`, `clamp(x)`, `a(id)` lấy action.

## Dễ đọc trên điện thoại (Template mục 10.4)

Ở 1920 x 1080: chữ thường ít nhất 32 px, chữ trong terminal/code ít nhất 34 px, tiêu đề 64 px trở lên. Một màn hình chỉ một ý chính, chiếm phần lớn khung hình; không bày dashboard nhiều ô nhỏ. Cần chi tiết nhỏ thì phóng to (zoom) vào vùng đang thao tác. Kiểm tra bằng lệnh `still` trước khi dựng.

## Kiểm tra tự động (sync-report)

Sau khi dựng, công cụ đo trên chính file video:

- Trước khi dựng: mọi file `timeline.json` nhắc tới (HTML, giọng, nhạc nền, hiệu ứng) phải có sẵn; thiếu file nào thì dừng với mã 1 và liệt kê.
- Trước khi dựng: trang phải chạy không cần mạng. Công cụ vẽ thử từng cảnh và chặn mọi yêu cầu ra mạng; có yêu cầu nào (Google Fonts, ảnh, CDN…) thì dừng với mã 1 và in ra đường dẫn.
- Thông số: độ phân giải, fps, codec, âm thanh 48 kHz, thời lượng hình bằng tiếng, âm lượng -14 LUFS / đỉnh -1 dBTP.
- Whisper nghe lại thành phẩm, tìm từng từ khóa, so với thời điểm hành động: lệch quá ±150 ms là cảnh báo, quá ±300 ms là không đạt.
- So khung hình ngay trước và sau mỗi hành động: hình không đổi là không đạt (thao tác không hiện ra).
- Ảnh trước/sau từng hành động trong `sync-frames/` để mở xem bằng mắt.
- Chỗ nối giữa các tiến trình render: vẽ lại khung đầu mỗi đoạn trên trang đã chạy sẵn và so với video. Khác nhau (font, ảnh chưa nạp kịp, hoặc `renderAtTime` phụ thuộc lần gọi trước) là không đạt, vì video sẽ giật ở chỗ đó.

Báo cáo do công cụ viết; không tự viết hay sửa tay `sync-report.md`.

## Máy và tốc độ

Render song song nhiều Chromium (mặc định 5 tiến trình cho nhẹ máy, đổi bằng `--workers`). Mã hóa H.264 bằng GPU NVIDIA (`h264_nvenc`, CQ 18) nếu dùng được, không thì tự chuyển sang `libx264` CRF 16. Hai cách cho chất lượng gần như nhau (SSIM 0,9995). Đo thử trên máy này (driver 617.42): 18 giây video 60 fps dựng mất 11 giây với cả GPU lẫn CPU, vì phần chậm là chụp khung hình bằng trình duyệt chứ không phải mã hóa.

File tạm ở `tmp/videokit/` (kết quả Whisper được lưu lại, giọng không đổi thì không chạy lại).
