# Cài đặt và chạy trên Ubuntu

Chương trình dùng chung mã nguồn cho Windows và Ubuntu; chỉ khác cách cài đặt, cách chạy và vài mặc định. Phần dùng giao diện, kết nối Google Sheet, Facebook Page xem ở các hướng dẫn còn lại (giống hệt Windows).

Hỗ trợ: **Ubuntu 22.04 / 24.04** (bản Desktop). Máy không có màn hình (server) vẫn chạy được bằng dòng lệnh qua `xvfb-run`.

## 1. Chạy từ mã nguồn (khuyên dùng)

```bash
cd shopee_auto_post
chmod +x scripts/ubuntu/*.sh        # chỉ cần nếu chép từ file .zip
./scripts/ubuntu/setup.sh           # cài gói hệ thống, tạo .venv, cài thư viện và Chromium (cần sudo)
./scripts/ubuntu/chay_ung_dung.sh   # mở giao diện
```

`setup.sh` cài: `python3-venv`, `python3-tk` (giao diện), `ffmpeg` (video m3u8), `xvfb` (chạy trình duyệt khi không có màn hình), thư viện trong `requirements.txt` và Chromium của Playwright.

## 2. Bản đóng gói (không cần Python trên máy đích)

Trên một máy Ubuntu đã chạy `setup.sh`:

```bash
./scripts/ubuntu/build.sh
```

Kết quả: thư mục `dist/ShopeeFBTool/` và file `dist/ShopeeFBTool-<phiên bản>-ubuntu.tar.gz`. Trên máy đích:

```bash
tar xzf ShopeeFBTool-1.0.0-ubuntu.tar.gz
cd ShopeeFBTool
./ShopeeFBTool                 # giao diện
./ShopeeFBTool cli check       # dòng lệnh
```

Máy đích cần **Google Chrome** (tải gói `.deb` tại google.com/chrome rồi `sudo apt install ./google-chrome-stable_current_amd64.deb`). Bản build trên Ubuntu 22.04 chạy được trên 22.04 và 24.04; build trên 24.04 có thể không chạy trên 22.04.

## 3. Dòng lệnh

Mọi lệnh giống [HUONG_DAN_COMMAND.md](HUONG_DAN_COMMAND.md), chỉ thay phần gọi chương trình (không cần `start /wait`):

| Windows | Ubuntu (mã nguồn) | Ubuntu (bản đóng gói) |
|---|---|---|
| `start /wait ShopeeFBTool.exe cli check` | `./scripts/ubuntu/chay_ung_dung.sh cli check` | `./ShopeeFBTool cli check` |
| `py app.py cli post --dry-run` | `./scripts/ubuntu/chay_ung_dung.sh cli post --dry-run` | `./ShopeeFBTool cli post --dry-run` |

## 4. Đặt lịch chạy tự động (cron)

Đăng nhập Shopee **một lần** khi có màn hình: `./scripts/ubuntu/chay_ung_dung.sh cli login-shopee`. Sau đó `crontab -e` và thêm (chạy mỗi 30 phút):

```
*/30 * * * * cd /duong/dan/shopee_auto_post && flock -n /tmp/shopeefb.lock xvfb-run -a ./scripts/ubuntu/chay_ung_dung.sh cli all >> data/logs/cron.log 2>&1
```

- `xvfb-run -a`: tạo màn hình ảo vì bước tải video cần trình duyệt thật.
- `flock -n`: lượt trước chưa xong thì bỏ qua lượt mới (giống "Do not start a new instance" của Task Scheduler).

## 5. Khác biệt so với Windows

| Mục | Windows | Ubuntu |
|---|---|---|
| Trình duyệt mặc định | Microsoft Edge | Google Chrome, tự chuyển sang Chromium của Playwright nếu không có |
| Thư mục dữ liệu | `data\` cạnh chương trình, dự phòng `%LOCALAPPDATA%\ShopeeFBTool` | `data/` cạnh chương trình, dự phòng `~/.local/share/ShopeeFBTool` |
| Cài ffmpeg | `winget install ffmpeg` | `sudo apt install ffmpeg` |
| Đặt lịch | Task Scheduler | cron |

Chrome/Edge cài bằng **snap** không dùng được với Playwright; hãy dùng gói `.deb` hoặc Chromium của Playwright.

## 6. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `$'\r': command not found` khi chạy `.sh` | File bị đổi sang xuống dòng Windows: `sed -i 's/\r$//' scripts/ubuntu/*.sh` |
| `Permission denied` khi chạy `.sh` | `chmod +x scripts/ubuntu/*.sh` |
| `No module named 'tkinter'` | `sudo apt install python3-tk` |
| `Không mở được trình duyệt` | Cài Google Chrome (.deb) hoặc chạy lại `setup.sh` |
| `Missing X server or $DISPLAY` / `cannot open display` | Chạy kèm `xvfb-run -a ...` |
