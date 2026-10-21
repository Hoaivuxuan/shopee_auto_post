# Thiết lập Douyin → YouTube Shorts

## 1. Google Cloud

1. Tạo project tại [Google Cloud Console](https://console.cloud.google.com/)
2. Bật **YouTube Data API v3**
3. OAuth consent screen (External / Testing — thêm email tài khoản kênh)
4. Credentials → **OAuth client ID** → Application type **Desktop app**
5. Tải JSON, đổi tên thành `client_secrets.json`

## 2. Đặt file trên máy

```
douyin_to_social_media/data/douyin/client_secrets.json
```

Mẫu: `client_secrets.example.json`

## 3. Ủy quyền

1. Mở admin → chọn đích **YouTube** → tab **Cấu hình**
2. Bấm **Ủy quyền YouTube** (mở trình duyệt)
3. Google sẽ hỏi chọn **tài khoản Gmail**, rồi (nếu có nhiều kênh) chọn **Brand Account / kênh YouTube** muốn đăng
4. Token lưu tại `data/douyin/youtube_token.json` — **gắn với đúng kênh đã chọn**

Cổng OAuth mặc định: `8767` (cấu hình trong `youtube_config.json` → `oauth_port`). Container dùng `network_mode: host` nên redirect localhost hoạt động.

### Đổi kênh đăng (cùng một Gmail)

YouTube API **không** cho chọn `channel_id` lúc upload với tài khoản thường. Muốn đăng kênh khác:

1. Xóa `data/douyin/youtube_token.json` (hoặc bấm lại **Ủy quyền YouTube**)
2. Trong màn chọn kênh Google, chọn đúng Brand Account (ví dụ *Tinh Hoa Phương Đông* / *XoàiCon28*), **không** chọn kênh cá nhân mặc định
3. Kiểm tra admin hiện đúng tên kênh trước khi đăng lại

## 4. Tiêu đề & mô tả (Xem trước → YouTube)

Trên tab **Xem trước** khi đích là YouTube, nội dung tách 2 ô:

| Trường | Ý nghĩa |
|--------|---------|
| **Tiêu đề được dịch** | Title Shorts — không gắn tag dịch Douyin; khi đăng luôn kết thúc bằng `#Shorts` |
| **Mô tả được chọn lọc từ nội dung của video** | Description — phần chữ từ kịch bản AI; hashtag cố định `#shortviral #kienthucthuvi #khampha #vuive` |

Bấm **Lưu tiêu đề & mô tả** trước khi đăng. File lưu trong `translations.json` (`title_vi`, `description_vi`).

## 5. Đăng

- Chỉ đăng file `processed/{id}/output_ai.mp4` (video ngắn AI)
- Lịch sử riêng: `youtube_posts.json` (không lẫn `posts.json` của Facebook)
