# Công thức Shorts thuyết minh (di sản / thủ công)

> Lưu ngày: 2026-10-20  
> Nguồn chuẩn: [YouTube Shorts `cnJblXj7EUk`](https://www.youtube.com/shorts/cnJblXj7EUk) — kênh **BIẾT HAY CHƯA**  
> File mẫu local: `data/videos/cnJblXj7EUk.mp4` (~**149s / 2:29**, 9:16)  
> Mục đích: áp dụng thống nhất cho nhiều video Douyin → video AI (cắt + VO + phụ đề)

Dùng kèm plan kỹ thuật: [`PLAN_DOUYIN_AI_VIDEO.md`](./PLAN_DOUYIN_AI_VIDEO.md).

---

## 1. Mục tiêu sản phẩm

| Chỉ số | Mục tiêu |
|--------|----------|
| Độ dài | **~150s** (kiểu mẫu ~2.5 phút); hard cap **≤180s (3 phút)** |
| Tỷ lệ | 9:16 dọc |
| Giọng | Nam miền Bắc, chậm–vừa, truyền cảm (`length_scale` Piper ~1.35–1.4) |
| VO | **Gần như liên tục** (≥90–95% thời lượng có lời) |
| Hình | Montage cận cảnh / macro, bám thao tác |
| Chủ đề | Bám `caption_vi` / bản dịch — không tin ASR nếu lệch chủ đề |

---

## 2. Công thức cắt hình (quan trọng)

### 2.1 Không làm

- ❌ Chỉ lấy **3 khối dài** (30–55s) đầu / giữa / cuối rồi ghép  
- ❌ Để một góc máy đứng lâu trong khi lời chỉ “tóm” cả đoạn  
- ❌ Cắt nhảy lung tung không theo quy trình nghề  

### 2.2 Nên làm (theo mẫu)

- ✅ **Montage dày**: nhiều shot ngắn  
  - Tham chiếu mẫu: ~**60 cắt** / 149s  
  - Trung vị shot ~**2s**; phần lớn **1–4s**  
  - Shot ≥5–12s chỉ dùng cho hook / cảnh tượng trưng  
- ✅ Kể **theo chuỗi quy trình**, rút gọn từng bước bằng shot ngắn, không bỏ mất mạch nghề  
- ✅ Ưu tiên cận cảnh: tay → nguyên liệu → lửa/khuôn → chi tiết → thành phẩm  

### 2.3 Khung chương (7 beat — áp dụng mọi video thủ công/di sản)

Điều chỉnh thời lượng tỷ lệ theo tổng video (mẫu = 149s):

| # | Tỷ lệ thời gian | Vai trò | Nội dung hình |
|---|-----------------|---------|---------------|
| 1 | **0–8%** | Hook | Cảnh mở bất ngờ / nguyên liệu lạ / tay trong môi trường thật |
| 2 | **8–21%** | Chuẩn bị | Rửa, chọn, nghiền, chuẩn bị liệu |
| 3 | **21–38%** | Pha & biến đổi | Trộn, màu, lò/nhiệt, trạng thái vật liệu đổi |
| 4 | **38–48%** | Cầu nối kỹ thuật | Kéo/kéo sợi/thanh… + chuẩn bị bước lõi |
| 5 | **48–75%** | **Lõi nghề** (dài nhất) | Thao tác chính (đèn công / đục / thêu / …) cận cảnh |
| 6 | **75–93%** | Ý nghĩa | Thành phẩm + biểu tượng văn hóa / giá trị |
| 7 | **93–100%** | Kết + CTA | Ẩn dụ cảm xúc + nhắc theo dõi / giữ nghề |

**Quy tắc chọn clip nguồn Douyin dài:** trong mỗi beat lấy **nhiều đoạn ngắn** (hoặc 1 đoạn rồi cắt phụ theo scene) sao cho tổng ≈ tỷ lệ trên; ưu tiên cảnh có chuyển động tay + thay đổi vật liệu rõ.

### 2.4 Gợi ý triển khai kỹ thuật (sau này)

1. Chọn timeline theo 7 beat (LLM + `topic_vi`).  
2. Trong mỗi beat: scene-detect / cắt theo khoảng 1.5–4s (hoặc chia đều nếu không detect được).  
3. Concat giữ thứ tự beat — **không** sắp lại theo score thuần.  
4. Hard cap tổng ≤ 180s; ưu tiên cắt bớt beat 2–3 nếu thừa, **giữ beat 1, 5, 6, 7**.

---

## 3. Công thức lời thuyết minh

### 3.1 Mật độ & nhịp

| Chỉ số | Mục tiêu |
|--------|----------|
| Phủ VO | ≥ 90% độ dài video |
| Độ dài câu | ~4–8 giây / câu (hoặc 1 ý / câu) |
| Mật độ chữ | cao kiểu tài liệu (~12–18 ký tự/giây trên toàn video) — chậm nói nhưng **nhiều ý nối tiếp** |
| Khoảng nghỉ | chỉ nghỉ ngắn giữa câu (≤0.5–1s), không để 20–40s chỉ BGM |

### 3.2 Sáu lớp lời (bắt buộc đủ)

1. **Hook phản trực giác**  
   Mở bằng điều người xem “nghĩ sai” hoặc chi tiết bất ngờ.  
   *Mẫu:* “Nhiều người nghĩ thủy tinh chỉ được làm từ cắt, nhưng lưu ly truyền thống bắt đầu từ vỏ trai…”

2. **Giải thích khớp hình**  
   Mỗi câu mô tả đúng thao tác / vật liệu đang chiếu — không nói chung chung cả đoạn dài.

3. **Câu cầu nối** (giữa video, trước beat lõi)  
   *Mẫu:* “Và từ đây, kỹ thuật quan trọng nhất mới bắt đầu.”

4. **Định nghĩa / tên nghề**  
   Gắn thuật ngữ + biệt danh cảm xúc.  
   *Mẫu:* “Đèn công… được ví như nghệ thuật điêu khắc trong lửa.”

5. **Cao trào cảm xúc**  
   Ẩn dụ: thời gian, vẻ đẹp mong manh, lưu giữ di sản.  
   *Mẫu:* khóa vẻ đẹp một mùa hoa vào lưu ly / không bao giờ tàn.

6. **CTA ngắn**  
   Đăng ký / theo dõi để nghề xưa không bị lãng quên — **không** nhồi hashtag trong VO.

### 3.3 Phong cách ngôn ngữ

- Giọng **miền Bắc** chuẩn (ạ / đấy / nhé — vừa phải; tránh khẩu ngữ Nam).  
- Không emoji, không hashtag trong lời đọc.  
- Không bịa nguyên liệu/thao tác lệch `caption_vi`.  
- ASR chỉ dùng làm mốc thời gian nếu nhiễu — **chủ đề lấy từ bản dịch**.

### 3.4 Prompt viết lời (template tái sử dụng)

```
Viết lời thuyết minh tiếng Việt (nam Bắc, chậm, truyền cảm) cho video thủ công/di sản.
Bám caption_vi / topic_vi. Cấm lệch chủ đề dù ASR nhiễu.

Cấu trúc bắt buộc:
1) Hook phản trực giác (1–2 câu)
2) Từng bước khớp timeline (mỗi mốc 1 câu, 4–8s)
3) Một câu cầu nối trước đoạn kỹ thuật lõi
4) Định nghĩa tên nghề + biệt danh
5) Kết cảm xúc (ẩn dụ)
6) CTA ngắn (không hashtag)

Mỗi dòng JSON: {"t_start", "t_end", "text"} khớp timeline đã cắt.
Phủ lời ≥ 90% thời lượng. Không để khoảng trống dài.
```

---

## 4. Công thức phụ đề

| Thuộc tính | Chuẩn |
|------------|--------|
| Kiểu | **Karaoke / cụm ngắn** (2–6 chữ / lần hiện), không cả câu dài một khối |
| Font | Sans-serif đậm, trắng |
| Viền | Đen dày (đọc được trên nền sáng/tối) |
| Vị trí | Giữa–dưới khung (safe zone Shorts; tránh nút like/share) |
| Đồng bộ | Theo nhịp đọc TTS (fade/out sau khi đọc xong cụm) |
| Watermark | Tuỳ kênh — nhỏ dưới phụ đề; không che tay/lửa |

---

## 5. Âm thanh

| Lớp | Mức gợi ý |
|-----|-----------|
| Voiceover | Chính (~0.85–0.95) |
| BGM gốc / nhạc | Nhẹ (~0.35–0.45) + **duck** khi có lời |
| Tiếng Trung gốc | Tắt hoặc rất nhỏ nếu chồng lời VI |

Tốc độ TTS: ưu tiên chậm truyền cảm (Piper `length_scale` ~1.35–1.4; Edge rate âm; không `atempo` tăng tốc mạnh).

---

## 6. Checklist QA trước khi xuất bản

- [ ] Độ dài trong **120–180s** (lý tưởng ~140–160s)  
- [ ] Có đủ 7 beat (hoặc rút gọn có lý do; vẫn còn hook + lõi + kết)  
- [ ] Shot trung bình ngắn (cảm giác “nhiều cảnh”, không 3 khối đứng)  
- [ ] VO phủ gần hết video; nghe liền mạch  
- [ ] Có hook + câu cầu nối + định nghĩa nghề + kết cảm xúc + CTA  
- [ ] Lời khớp `caption_vi` / chủ đề  
- [ ] Phụ đề cụm ngắn, trắng + viền đen, không che chủ thể  
- [ ] BGM không át lời  

---

## 7. So sánh nhanh: mẫu vs pipeline cũ

| | Shorts mẫu | Pipeline cũ (tránh lặp lại) |
|--|------------|------------------------------|
| Cắt | ~60 shot ngắn theo quy trình | 3 khối dài |
| VO | Liên tục, nhiều câu | 3 câu + nhiều khoảng trống |
| Đồng bộ | Câu ↔ thao tác | Câu tóm cả đoạn |
| Cảm xúc | Hook → lõi → ẩn dụ → CTA | Thiếu cầu nối / CTA |

---

## 8. Ánh xạ sang code (để triển khai dần)

| Thành phần | File / chỗ chỉnh |
|------------|------------------|
| Target/max giây | `douyin_process.py`, `douyin_highlight.py` (`150` / `180`) |
| Chọn beat / clip | `douyin_highlight.py` — prompt + normalize theo 7 beat |
| Cắt phụ shot ngắn | `douyin_cut.py` (+ scene detect sau này) |
| Viết VO dày | `douyin_voice.py` — `_script_prompt`, `CHARS_PER_SEC` |
| TTS chậm | `douyin_tts_piper.py` `DEFAULT_LENGTH_SCALE` |
| Phụ đề karaoke | `douyin_subtitle.py` |
| Job UI | `douyin_ai_job.py`, admin-ui Xem trước |

Khi đổi prompt/highlight/cut: **đọc lại §2–§4** trước khi merge.

---

## 9. Lịch sử

| Ngày | Ghi chú |
|------|---------|
| 2026-10-20 | Chốt công thức từ phân tích `cnJblXj7EUk` (cắt montage + VO tài liệu 6 lớp + phụ đề karaoke) |
| 2026-10-20 | Code: `douyin_highlight` 7 beat, `douyin_cut` montage 2.6s, `douyin_voice` slot VO, `douyin_subtitle` karaoke — test `7670530751607098667` |
