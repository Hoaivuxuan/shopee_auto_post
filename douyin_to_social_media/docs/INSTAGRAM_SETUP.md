# Thiết lập Douyin → Instagram Reels

## Điều kiện

- Tài khoản **Instagram Professional** (Business/Creator)
- Đã **liên kết với Facebook Page**
- **Page Access Token** có quyền đăng content (cùng token dùng tab Facebook nếu Page đúng)

## Trong admin

1. Cấu hình tab **Facebook** trước (Page + token) — IG sẽ tái dùng
2. Tab **Instagram** → kiểm tra đã hiện `@username`
3. (Tuỳ chọn) dán token ghi đè / đặt `public_base_url` trong `instagram_config.json` nếu Meta bắt `video_url` công khai
4. Tạo video ngắn AI → Đăng Reels

## Ghi chú kỹ thuật

- Mặc định: tạo container `REELS` + **resumable upload**
- Nếu API không trả URI upload: đặt `public_base_url` trỏ ra admin (vd. `http://your-host:8766`) để IG kéo `/api/douyin/ai-media/{id}`
- Lịch sử: `instagram_posts.json`
