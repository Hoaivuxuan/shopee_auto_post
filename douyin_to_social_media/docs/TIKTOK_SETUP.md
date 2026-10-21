# Thiết lập Douyin → TikTok

## 1. TikTok for Developers

1. Tạo app tại [developers.tiktok.com](https://developers.tiktok.com/)
2. Thêm sản phẩm **Content Posting API**
3. Bật **Direct Post**
4. Xin scope **`video.publish`** (+ `user.info.basic`)
5. Thêm Redirect URI: `http://127.0.0.1:8768/callback`

> App chưa audit: video có thể bị giới hạn `SELF_ONLY` / private. Sau audit mới public ổn định.

## 2. Trong admin

1. Tab **TikTok** → Cấu hình
2. Dán **Client key** / **Client secret** → Lưu key
3. Bấm **Ủy quyền TikTok** — xem terminal in URL OAuth, đăng nhập đúng tài khoản
4. Token lưu: `data/douyin/tiktok_token.json`
5. Tạo video ngắn AI → Đăng

## 3. File cấu hình

- `tiktok_config.json` — key, privacy, auto
- `tiktok_posts.json` — lịch sử đăng (tách Facebook/YouTube/IG)
