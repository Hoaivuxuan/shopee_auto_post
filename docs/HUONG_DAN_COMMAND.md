# Hướng dẫn sử dụng bằng dòng lệnh (Command)

Ngoài giao diện, chương trình có thể chạy hoàn toàn bằng lệnh. Cách này hợp để đặt lịch tự động (Task Scheduler) hoặc chạy trên máy không cần mở giao diện. **Cấu hình dùng chung với giao diện** (file `data\config.json`), nên bạn có thể thiết lập bằng giao diện rồi chạy bằng lệnh.

## 1. Cách gọi lệnh

Mở **Command Prompt** trong thư mục chương trình, rồi:

```
start /wait ShopeeFBTool.exe cli <lệnh> [tùy chọn]
```

- `start /wait` giúp Command Prompt chờ chương trình chạy xong và hiển thị kết quả ngay tại cửa sổ. Bản `.exe` là ứng dụng cửa sổ nên cần cách gọi này để thấy kết quả.
- Nếu chạy từ mã nguồn (đã cài Python): `py app.py cli <lệnh> [tùy chọn]`.
- Gõ `ShopeeFBTool.exe cli` (không kèm lệnh) để xem danh sách lệnh.
- Chữ in hoa như `LINK`, `TOKEN` chỉ là chỗ để thay bằng giá trị thật, đặt trong dấu ngoặc kép.
- Mã thoát: `0` là bình thường, `1` là có lỗi (hữu ích khi dùng trong file `.bat`).

## 2. Tổng hợp lệnh

### Cấu hình
| Lệnh | Ý nghĩa |
|---|---|
| `cli config show` | Xem cấu hình (token và URL được che) |
| `cli config path` | In đường dẫn file cấu hình |
| `cli config set KHÓA GIÁ_TRỊ` | Sửa một mục cấu hình, ví dụ `cli config set sheet.url "https://script.google.com/macros/s/.../exec"` |
| `cli check` | Kiểm tra môi trường: trình duyệt, ffmpeg, thư mục, Sheet, Page |

Các khóa hay dùng của `config set`:
| Khóa | Ý nghĩa |
|---|---|
| `sheet.url`, `sheet.token`, `sheet.tab` | Kết nối Google Sheet |
| `shopee.videos_dir` | Thư mục lưu video |
| `shopee.browser` | `msedge`, `chrome` hoặc `chromium` |
| `shopee.show_browser` | `true` để hiện cửa sổ trình duyệt khi tải |
| `shopee.wait_seconds`, `shopee.limit`, `shopee.min_delay`, `shopee.max_delay` | Chờ video, số link mỗi lần, nghỉ giữa các link |
| `facebook.app_id`, `facebook.app_secret`, `facebook.api_version` | Ứng dụng Meta |
| `facebook.schedule_mode` | `local` hoặc `facebook` |
| `facebook.link_in_comment`, `facebook.link_prefix` | Cách đặt link |
| `facebook.limit`, `facebook.min_delay`, `facebook.max_delay` | Số dòng mỗi lần, nghỉ giữa các bài |

### Google Sheet
| Lệnh | Ý nghĩa |
|---|---|
| `cli test-sheet` | Kiểm tra kết nối Google Sheet |
| `cli init-sheet` | Ghi tiêu đề các cột A-N |

### Shopee
| Lệnh | Ý nghĩa |
|---|---|
| `cli login-shopee` | Mở trình duyệt để đăng nhập Shopee; đăng nhập xong nhấn Enter ở cửa sổ lệnh để lưu phiên |
| `cli clear-shopee` | Xóa phiên đăng nhập đã lưu |

### Facebook
| Lệnh | Ý nghĩa |
|---|---|
| `cli exchange TOKEN_NGẮN_HẠN` | Đổi token ngắn hạn sang dài hạn (cần App ID/Secret trong cấu hình hoặc `--app-id`, `--app-secret`) |
| `cli sync-pages TOKEN --exchange` | Lấy tất cả Page và lưu vào cấu hình; `--exchange` đổi token sang dài hạn trước. Bỏ `--exchange` nếu token đã là dài hạn |
| `cli add-page "TÊN" PAGE_ID PAGE_TOKEN` | Thêm tay một Page |
| `cli list-pages` | Xem danh sách Page |
| `cli check-pages` | Kiểm tra token của các Page |

### Chạy công việc
| Lệnh | Ý nghĩa |
|---|---|
| `cli download` | Tải video theo link trong sheet |
| `cli post` | Đăng các video đã tải lên Facebook Page |
| `cli all` | Tải xong rồi đăng (lần lượt) |
| `cli all --parallel` | Vừa tải vừa đăng (song song) |

Tùy chọn dùng chung: 
| Tùy chọn | Ý nghĩa |
|---|---|
| `--dry-run` | Chạy thử, không tải/đăng thật, không ghi vào sheet |
| `--retry` | Chạy lại các dòng Lỗi / Một phần |
| `--limit N` | Số dòng/link tối đa mỗi lần |

Tùy chọn riêng:
| Tùy chọn | Áp dụng cho | Ý nghĩa |
|---|---|---|
| `--show` | download, all | Hiện cửa sổ trình duyệt |
| `--min-delay N`, `--max-delay N` | download, post | Khoảng nghỉ giữa 2 link/2 bài (giây); `0` để không nghỉ |
| `--schedule local` hoặc `--schedule facebook` | post | Cách hẹn giờ đăng |
| `--link-in-comment` | post | Đưa link vào bình luận đầu tiên |
| `--watch PHÚT` | post | Chạy liên tục, quét lại mỗi PHÚT phút (Ctrl+C để dừng) |

## 3. Quy trình thiết lập lần đầu bằng lệnh

```
start /wait ShopeeFBTool.exe cli config set sheet.url "URL-APPS-SCRIPT"
start /wait ShopeeFBTool.exe cli config set sheet.token "TOKEN-CUA-BAN"
start /wait ShopeeFBTool.exe cli test-sheet
start /wait ShopeeFBTool.exe cli init-sheet
start /wait ShopeeFBTool.exe cli login-shopee
start /wait ShopeeFBTool.exe cli config set facebook.app_id "APP_ID"
start /wait ShopeeFBTool.exe cli config set facebook.app_secret "APP_SECRET"
start /wait ShopeeFBTool.exe cli sync-pages "TOKEN_NGAN_HAN" --exchange
start /wait ShopeeFBTool.exe cli list-pages
start /wait ShopeeFBTool.exe cli all --dry-run
```

## 4. Ví dụ dùng hằng ngày

```
cli download --limit 10
cli post --dry-run
cli post --schedule facebook --min-delay 0 --max-delay 0
cli post --watch 5
cli all --parallel
cli all --retry
```

## 5. Đặt lịch bằng Task Scheduler

Tạo file `chay_tu_dong.bat` cạnh chương trình:

```
@echo off
cd /d "%~dp0"
start /wait ShopeeFBTool.exe cli all
```

Trong Task Scheduler: **Create Basic Task**, chọn tần suất, Action là **Start a program** trỏ tới file `.bat` đó, ô **Start in** là thư mục chương trình. Trong thuộc tính chọn **Run only when user is logged on** (bước tải cần trình duyệt) và mục *If the task is already running* chọn **Do not start a new instance**. Khi chạy bằng Task Scheduler không có cửa sổ để xem, hãy xem kết quả trong thư mục `data\logs` hoặc ngay trên Google Sheet.

Thay cho Task Scheduler, bạn cũng có thể dùng tính năng **Tự chạy lại mỗi N phút** trong giao diện.

## 6. Tương ứng với các script lẻ cũ

Nếu trước đây bạn dùng các script `.py` riêng, đây là cách chuyển sang chương trình mới:
| Script cũ | Lệnh mới |
|---|---|
| `shopee_batch_appsscript.py` | `cli download` |
| `shopee_fb_post.py` | `cli post` |
| `shopee_fb_post.py --watch 5` | `cli post --watch 5` |
| `shopee_fb_post.py --dry-run` | `cli post --dry-run` |
| `shopee_fb_post.py --init`, `shopee_batch_appsscript.py --init` | `cli init-sheet` |
| `shopee_fb_post.py --exchange APP_ID APP_SECRET TOKEN` | `cli exchange TOKEN --app-id APP_ID --app-secret APP_SECRET` |
| `shopee_fb_post.py --sync-pages TOKEN` | `cli sync-pages TOKEN` |
| `shopee_fb_post.py --add-page "TÊN" ID TOKEN` | `cli add-page "TÊN" ID TOKEN` |
| `shopee_fb_post.py --list-pages` | `cli list-pages` |
| `shopee_capture_video.py --login` | `cli login-shopee` |
| `chay_tat_ca.bat` | `cli all` |
| `chay_song_song.bat` | `cli all --parallel` |

Khác biệt cần nhớ:
- Mặc định nghỉ giữa 2 bài đăng là 10-30 giây (script cũ là 120-300 giây). Đổi bằng `--min-delay` và `--max-delay`.
- Chương trình mới không còn dùng `yt-dlp`; video được bắt trực tiếp từ trình duyệt.
- Cấu hình nằm trong `data\config.json` thay vì các biến môi trường `SHEET_URL`, `SHEET_TOKEN`.
- Cần Apps Script bản mới (nút **Sao chép mã Apps Script** trong giao diện; mã gốc nằm trong `shopeetool/appscript.py`).

## 7. Lỗi thường gặp khi dùng lệnh

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy gì in ra | Dùng `start /wait ShopeeFBTool.exe cli ...` (không bỏ `start /wait`) |
| `Chưa nhập URL hoặc Token` | Chạy `cli config set sheet.url ...` và `cli config set sheet.token ...` |
| Gõ lệnh bị lỗi vì có ký tự `&` hoặc `?` | Đặt giá trị trong dấu ngoặc kép |
| `Không bắt được link video` | Đăng nhập lại Shopee (`cli login-shopee`), thử `--show` |
| Lỗi Facebook 190 | Lấy lại token và chạy `cli sync-pages TOKEN --exchange` |
