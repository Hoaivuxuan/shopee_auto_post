# douyin_to_social_media

Hệ thống lấy video từ **Douyin**, xử lý thành video ngắn (thuyết minh tiếng Việt), rồi đăng lên các nền tảng mạng xã hội.

```
Douyin (nguồn)
    → tải về
    → dịch / ASR / cắt highlight
    → lồng tiếng + phụ đề
    → video ngắn 9:16 (~150s)
    → đăng: Facebook · YouTube Shorts · TikTok · …
```

Trước đây dự án tên `youtube_to_facebook` (nguồn YouTube → chỉ Facebook). Định hướng mới: **Douyin là nguồn chính**, đích đăng là **đa nền tảng**.

---

## Pipeline

| Bước | Module | Trạng thái |
|------|--------|------------|
| 1. Tải Douyin | `douyin_download.py` | ✅ |
| 2. Dịch caption ZH→VI | `douyin_translate.py` | ✅ |
| 3. ASR tiếng Trung | `douyin_asr.py` | ✅ |
| 4. Chọn highlight ≤180s | `douyin_highlight.py` + `douyin_llm.py` | ✅ |
| 5. Cắt / ghép | `douyin_cut.py` | ✅ |
| 6. Lồng tiếng VI | `douyin_voice.py` (Piper / FPT / edge-tts) | ✅ |
| 7. Phụ đề burn-in | `douyin_subtitle.py` | ✅ |
| 8. Orchestrate 1 video | `douyin_process.py` + `douyin_ai_job.py` | ✅ |
| 9. Đăng Facebook | `douyin_poster.py` | ✅ |
| 10. Đăng YouTube Shorts | `douyin_youtube_poster.py` + `publishers/youtube.py` | ✅ |
| 11. Đăng TikTok | `douyin_tiktok_poster.py` + `publishers/tiktok.py` | ✅ |
| 12. Đăng Instagram Reels | `douyin_instagram_poster.py` + `publishers/instagram.py` | ✅ |

Setup: [`docs/YOUTUBE_SETUP.md`](docs/YOUTUBE_SETUP.md) · [`docs/TIKTOK_SETUP.md`](docs/TIKTOK_SETUP.md) · [`docs/INSTAGRAM_SETUP.md`](docs/INSTAGRAM_SETUP.md)

Công thức biên tập: [`docs/CONG_THUC_SHORTS_THUYET_MINH.md`](docs/CONG_THUC_SHORTS_THUYET_MINH.md)  
Plan kỹ thuật AI: [`docs/PLAN_DOUYIN_AI_VIDEO.md`](docs/PLAN_DOUYIN_AI_VIDEO.md)  
Định hướng hệ thống: [`docs/DINH_HUONG.md`](docs/DINH_HUONG.md)

---

## Chạy nhanh

```bash
# Host
.venv/bin/python douyin_to_social_media/admin_web.py
# → http://127.0.0.1:8766

# Docker Compose (service dts)
docker compose up -d dts
```

### Chất lượng video ngắn

Mặc định **ưu tiên chất lượng** (chậm hơn được) — cấu hình tại `douyin_quality.py`:

| Bước | Cài đặt chất lượng |
|------|-------------------|
| ASR | Whisper `large-v3`, beam 5, best_of 5 |
| Highlight / Script | Nhiệt độ thấp hơn, timeout LLM dài, nhiều ngữ cảnh transcript |
| Cắt / phụ đề | FFmpeg `slow` + CRF 18, audio 256k, re-encode khi ghép |
| TTS | `auto`: FPT → Edge neural (không ưu tiên Piper tốc độ) |
| Mux | TTS nổi hơn BGM, AAC 320k |

Video đã tạo trước cần **Tạo lại video ngắn** để áp dụng cấu hình mới.

Biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `DTS_HOST` | `0.0.0.0` | Host bind admin |
| `DTS_PORT` | `8766` | Port admin |
| `WHISPER_MODEL` | `large-v3` | Model ASR (chất lượng cao) |
| `OLLAMA_URL` | `http://127.0.0.1:11434/api/generate` | Fallback LLM local |

(`YT_FB_HOST` / `YT_FB_PORT` vẫn được đọc như alias cũ.)

---

## Dữ liệu

```
douyin_to_social_media/data/
├── douyin/                 # kho chính (nguồn Douyin)
│   ├── videos/             # mp4 gốc
│   ├── processed/{id}/     # transcript, script, output_ai.mp4
│   ├── manifest.json
│   ├── translations.json
│   ├── posts.json          # lịch sử đăng (theo nền tảng)
│   └── config.json         # token / auto-post / platforms
└── videos/                 # legacy YouTube Shorts (tham chiếu / phụ)
```

---

## Legacy

- `download_shorts.py`, `poster.py`, `suggest.py`: pipeline YouTube cũ (affiliate / tham chiếu công thức). Không phải luồng sản xuất chính.
- UI vẫn có tab nguồn YouTube để vận hành legacy khi cần; mặc định là **Douyin**.
