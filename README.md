# Shopee Auto Post

Bộ công cụ Python tự động **tải video sản phẩm Shopee** từ danh sách link trong **Google Sheet**, sau đó **đăng video lên một hoặc nhiều Facebook Page** (đăng ngay hoặc hẹn giờ) và **ghi trạng thái vào lại sheet**.

> Chỉ dùng cho video bạn có quyền sử dụng (video của bạn, hoặc shop/chủ video đã đồng ý). Tự động hóa trên Shopee/Facebook có rủi ro với tài khoản, nên dùng tài khoản phụ và không chạy dồn dập.

## Tính năng

- Mở trình duyệt thật (Playwright/Chromium), bắt link video `.mp4` / `.m3u8` giống tab Network (F12) rồi tải về.
- Đọc/ghi Google Sheet qua **Google Apps Script Web app** (miễn phí, không cần Google Cloud) hoặc qua **gspread + Service Account**.
- Đăng video lên nhiều Facebook Page bằng **Graph API**, hỗ trợ:
  - Đăng ngay hoặc hẹn giờ (tự đăng khi đến giờ, hoặc nhờ Facebook hẹn giờ).
  - Nội dung + link affiliate + hashtag, tùy chọn đưa link vào bình luận đầu tiên.
  - Chạy lại các dòng lỗi / đăng nốt các Page chưa thành công, chống đăng trùng.
  - Tự dừng khi Facebook giới hạn tốc độ.
- Chế độ chạy liên tục (`--watch`), chạy thử (`--dry-run`), nghỉ ngẫu nhiên giữa các lượt.

## Cấu trúc thư mục

```
shopee_auto_post/
├── README.md
├── .gitignore
└── Shopee/
    ├── shopee_video_dl.py          # Tải video từ 1 link (yt-dlp, link .mp4 trực tiếp, .m3u8 qua ffmpeg)
    ├── shopee_capture_video.py     # Mở trình duyệt bắt link video, đăng nhập Shopee (--login)
    ├── shopee_batch_appsscript.py  # Tải video hàng loạt từ Google Sheet qua Apps Script
    ├── shopee_batch_gsheet.py      # Tải video hàng loạt từ Google Sheet qua gspread (Service Account)
    ├── shopee_fb_post.py           # Đăng video đã tải lên Facebook Page, quản lý Page/token
    ├── apps_script_Code.gs         # Mã Google Apps Script (Web app) để đọc/ghi sheet
    ├── pages.example.json          # Mẫu file cấu hình Page (copy thành pages.json)
    ├── chay_tat_ca.bat             # Chạy lần lượt: tải video -> đăng Facebook
    ├── chay_song_song.bat          # Chạy song song 2 cửa sổ: tải video và đăng Facebook
    ├── ShopeeFBTool_v1.0.zip       # Bản đóng gói có giao diện (GUI) của công cụ
    ├── HUONG_DAN_SU_DUNG.md        # Hướng dẫn sử dụng bản giao diện
    ├── HUONG_DAN_KET_NOI.md        # Hướng dẫn kết nối Google Sheet và Facebook Page
    └── HUONG_DAN_COMMAND.md        # Hướng dẫn dòng lệnh
```

Các file/thư mục sinh ra khi chạy (đã được `.gitignore` loại bỏ vì chứa dữ liệu nhạy cảm hoặc dung lượng lớn):

| File / thư mục | Nội dung |
|---|---|
| `pages.json` | Danh sách Page và **Page access token** |
| `shopee_state.json` | Cookie phiên đăng nhập Shopee |
| `browser_profile/` | Dữ liệu trình duyệt |
| `service_account.json` | Khóa Service Account Google (nếu dùng `shopee_batch_gsheet.py`) |
| `videos/` | Video đã tải |

## Yêu cầu

- Windows, Python 3.9+ (dùng lệnh `py`).
- [ffmpeg](https://ffmpeg.org/download.html) (cần khi video là luồng `.m3u8`), ví dụ `winget install ffmpeg`.

Cài thư viện:

```bash
py -m pip install playwright requests yt-dlp
py -m playwright install chromium
# Chỉ khi dùng shopee_batch_gsheet.py
py -m pip install gspread
```

## Thiết lập lần đầu

### 1. Google Sheet + Apps Script

1. Tạo Google Sheet, vào **Tệp > Cài đặt**: Ngôn ngữ = Việt Nam, Múi giờ = (GMT+07:00) Hà Nội.
2. Vào **Tiện ích mở rộng > Apps Script**, dán nội dung `Shopee/apps_script_Code.gs`, **đổi `TOKEN`** thành chuỗi bí mật của bạn.
3. **Triển khai > Tùy chọn triển khai mới > Web app**, `Execute as: Me`, `Who has access: Anyone`, copy **Web app URL** (kết thúc `/exec`).
4. Đặt biến môi trường để khỏi phải truyền `--url`, `--token` mỗi lần:

```bash
setx SHEET_URL "https://script.google.com/macros/s/.../exec"
setx SHEET_TOKEN "TOKEN_CUA_BAN"
```

Chi tiết xem [HUONG_DAN_KET_NOI.md](Shopee/HUONG_DAN_KET_NOI.md).

### 2. Đăng nhập Shopee (lưu phiên)

```bash
cd Shopee
py shopee_capture_video.py --login
```

### 3. Facebook Page

Cần một app trên [Meta for Developers](https://developers.facebook.com) với quyền `pages_show_list`, `pages_manage_posts`, `publish_video`.

```bash
# Đổi token ngắn hạn sang token dài hạn
py shopee_fb_post.py --exchange APP_ID APP_SECRET TOKEN_NGAN_HAN
# Lấy tất cả Page (chạy lại để thêm Page mới / làm mới token)
py shopee_fb_post.py --sync-pages TOKEN_DAI_HAN
# Hoặc thêm tay một Page
py shopee_fb_post.py --add-page "Tên Page" PAGE_ID PAGE_TOKEN
# Xem danh sách
py shopee_fb_post.py --list-pages
```

### 4. Tạo tiêu đề cột trong sheet

```bash
py shopee_batch_appsscript.py --init   # cột A-E (tải video)
py shopee_fb_post.py --init            # cột F-N (đăng bài)
```

## Cấu trúc Google Sheet (tab đầu tiên)

| Cột | Nội dung | Ai điền |
|---|---|---|
| A | Link sản phẩm Shopee | Bạn |
| B-E | Trạng thái tải, Thời gian, File video, Ghi chú | Chương trình |
| F | Page (tên hoặc ID; nhiều Page ngăn cách bằng dấu phẩy/xuống dòng) | Bạn |
| G | Link affiliate (trống thì dùng link cột A) | Bạn |
| H | Nội dung bài đăng | Bạn |
| I | Tag, ví dụ `#giadung #sale` hoặc `giadung, sale` | Bạn |
| J | Giờ đăng, ví dụ `04/10/2026 09:00` (trống = đăng ngay) | Bạn |
| K-N | Trạng thái đăng, Đã xử lý lúc, ID bài đăng, Ghi chú đăng | Chương trình |

Chỉ dòng có cột B = `Thành công` (đã tải xong) và đã điền cột F mới được đăng.

## Sử dụng

### Tải video

```bash
# Một link
py shopee_capture_video.py "https://shopee.vn/..."
py shopee_video_dl.py --video-url "https://.../abc.mp4"

# Hàng loạt từ Google Sheet (Apps Script)
py shopee_batch_appsscript.py --limit 10
py shopee_batch_appsscript.py --retry --show

# Hàng loạt từ Google Sheet (gspread + service_account.json)
py shopee_batch_gsheet.py --sheet "LINK_SHEET"
```

Tùy chọn chính: `--out` (thư mục lưu, mặc định `videos`), `--limit`, `--wait` (giây chờ video), `--min-delay/--max-delay` (nghỉ giữa 2 link), `--show` (hiện trình duyệt), `--retry` (chạy lại dòng lỗi).

### Đăng Facebook

```bash
py shopee_fb_post.py --dry-run                 # chạy thử, không đăng thật
py shopee_fb_post.py                           # đăng thật
py shopee_fb_post.py --watch 5                 # quét lại mỗi 5 phút
py shopee_fb_post.py --schedule facebook       # nhờ Facebook hẹn giờ (máy tắt vẫn đăng)
py shopee_fb_post.py --retry                   # đăng nốt các dòng Lỗi / Một phần
```

Tùy chọn khác: `--tab`, `--limit` (mặc định 5), `--min-delay/--max-delay` (mặc định 120-300 giây), `--link-in-comment`, `--link-prefix "Mua tại: "`, `--videos`, `--pages`, `--api-version` (mặc định `v25.0`).

**Hẹn giờ:**
- `--schedule local` (mặc định): chương trình tự đăng khi đến giờ, máy phải bật và job đang chạy (`--watch` hoặc Task Scheduler).
- `--schedule facebook`: tải video lên ngay, Facebook tự đăng đúng giờ. Giờ hẹn phải cách hiện tại khoảng 12 phút đến 29 ngày.

### Chạy bằng file .bat

- `chay_tat_ca.bat`: tải video rồi đăng Facebook lần lượt (có thể đặt lịch bằng Task Scheduler).
- `chay_song_song.bat`: mở 2 cửa sổ, một cửa sổ tải video, một cửa sổ quét mỗi 2 phút để đăng video vừa tải xong.

> Hai file `.bat` đang trỏ tới thư mục `D:\Shopee`, sửa lại đường dẫn `cd /d` cho đúng nơi bạn đặt source.

## Trạng thái trong sheet

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Thành công (cột B) | Đã tải video | Điền cột F-J để đăng |
| Lỗi (cột B) | Không tải được, xem cột E | Sửa nguyên nhân, chạy với `--retry` |
| Thành công (cột K) | Đã đăng lên mọi Page | Không cần làm gì |
| Đã lên lịch | Facebook sẽ tự đăng đúng giờ | Không cần làm gì |
| Một phần | Một số Page đã lên, một số lỗi | Chạy `--retry` để đăng nốt, không đăng trùng |
| Lỗi (cột K) | Không đăng được, xem cột N | Sửa nguyên nhân rồi chạy lại |
| Đang xử lý | Bị dừng giữa chừng | Kiểm tra trên Facebook; nếu chưa có bài thì xóa ô đó để chạy lại |

## Bảo mật

- **Không commit** `pages.json`, `shopee_state.json`, `browser_profile/`, `service_account.json` (đã có trong `.gitignore`).
- Không chia sẻ Web app URL, `TOKEN` của Apps Script, App Secret và Page token.
- Dùng `pages.example.json` làm mẫu: copy thành `pages.json` hoặc để `--sync-pages` tự tạo.

## Tài liệu chi tiết

- [Hướng dẫn sử dụng (bản giao diện)](Shopee/HUONG_DAN_SU_DUNG.md)
- [Hướng dẫn kết nối Google Sheet & Facebook Page](Shopee/HUONG_DAN_KET_NOI.md)
- [Hướng dẫn dòng lệnh](Shopee/HUONG_DAN_COMMAND.md)
