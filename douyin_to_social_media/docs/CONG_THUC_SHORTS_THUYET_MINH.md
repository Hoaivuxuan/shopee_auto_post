# Công thức Shorts thuyết minh (di sản / thủ công)

> Cập nhật: 2026-10-22  
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
| Hình | Montage cận cảnh / macro, **bám thao tác nghề** — không lan man intro |
| Chủ đề | Bám `caption_vi` / bản dịch — không tin ASR nếu lệch chủ đề |
| Khớp hình–lời | Mỗi câu VO khớp cảnh đang chiếu (tay / liệu / lửa / thành phẩm) |

---

## 2. Công thức cắt hình (quan trọng)

### 2.1 Không làm

- ❌ Chỉ lấy **3 khối dài** (30–55s) đầu / giữa / cuối rồi ghép  
- ❌ Để một góc máy đứng lâu trong khi lời chỉ “tóm” cả đoạn  
- ❌ Cắt nhảy lung tung không theo quy trình nghề  
- ❌ **Lấy gần hết short từ nửa đầu nguồn** khi video gốc dài (cánh đồng / đi hái / không khí) trong khi lời nói về làm bánh / thao tác  
- ❌ **7 clip liền mạch từ giây 0** chiếm ~150s đầu của video ≥3–5 phút  
- ❌ Tin ASR ảo giác / nghèo để “bịa” timeline nghề trên cảnh intro  

### 2.2 Nên làm (theo mẫu)

- ✅ **Montage dày**: nhiều shot ngắn  
  - Tham chiếu mẫu: ~**60 cắt** / 149s  
  - Trung vị shot ~**2s**; phần lớn **1–4s**  
  - Shot ≥5–12s chỉ dùng cho hook / cảnh tượng trưng  
- ✅ Kể **theo chuỗi quy trình**, rút gọn từng bước bằng shot ngắn, không bỏ mất mạch nghề  
- ✅ Ưu tiên cận cảnh: tay → nguyên liệu → lửa/khuôn → chi tiết → thành phẩm  
- ✅ Với nguồn dài kiểu Lý Tử Thất: **bỏ / rút cực ngắn** phần mở đầu phong cảnh; ưu tiên nửa sau có thao tác  

### 2.3 Khung chương (7 beat — áp dụng mọi video thủ công/di sản)

Hai lớp thời gian **không được nhầm**:

| Lớp | Ý nghĩa |
|-----|---------|
| **Timeline đầu ra** (short ~150s) | Tỷ lệ beat dưới đây — thứ tự kể chuyện trên Shorts |
| **Cửa sổ nguồn Douyin** | Chỗ lấy cảnh trên video gốc — với nguồn dài thường lệch về **nửa sau** |

#### 2.3.1 Tỷ lệ trên Shorts đã cắt (đầu ra)

Điều chỉnh thời lượng tỷ lệ theo tổng short (mẫu = 149s):

| # | Tỷ lệ trên short | Vai trò | Nội dung hình |
|---|------------------|---------|---------------|
| 1 | **0–8%** | Hook | Cận cảnh thành phẩm / thao tác lõi bất ngờ (không bắt buộc là giây 0 nguồn) |
| 2 | **8–21%** | Chuẩn bị | Rửa, chọn, nghiền, chuẩn bị liệu |
| 3 | **21–38%** | Pha & biến đổi | Trộn, màu, lò/nhiệt, trạng thái vật liệu đổi |
| 4 | **38–48%** | Cầu nối kỹ thuật | Kéo/kéo sợi/thanh… + chuẩn bị bước lõi |
| 5 | **48–75%** | **Lõi nghề** (dài nhất) | Thao tác chính (đèn công / đục / thêu / sên bột / cắt bánh…) cận cảnh |
| 6 | **75–93%** | Ý nghĩa | Thành phẩm + biểu tượng văn hóa / giá trị |
| 7 | **93–100%** | Kết + CTA | Ẩn dụ cảm xúc + nhắc theo dõi / giữ nghề |

#### 2.3.2 Cửa sổ trên video NGUỒN (chọn clip)

Video thủ công dài (≥ ~200s / ~3.5 phút) thường **30–50% đầu = intro phong cảnh**. Không map beat short 1:1 lên cùng % của nguồn.

**Nguồn dài (≥200s) — lệch nửa sau (bắt buộc):**

| Beat | Cửa sổ nguồn (gợi ý) | Ghi chú |
|------|----------------------|---------|
| 1 hook | **90–99%** | Thành phẩm / cắt bánh gần cuối — hấp dẫn hơn cánh đồng |
| 2 prep | **52–62%** | Rửa/chọn liệu — sau khi hết intro đồng |
| 3 transform | **60–72%** | Trộn / hấp / biến đổi |
| 4 bridge | **68–78%** | Cầu nối kỹ thuật |
| 5 core | **75–90%** | Thao tác chính (dài nhất trên short) |
| 6 meaning | **88–96%** | Thành phẩm + ý nghĩa |
| 7 cta | **94–100%** | Kết |

**Nguồn ngắn (<200s):** phân bố đều hơn; hook có thể ở đầu nguồn (0–12%).

**Quy tắc chọn clip nguồn:**

1. Trong mỗi beat lấy **nhiều đoạn ngắn** (hoặc 1 đoạn rồi cắt phụ) sao cho tổng ≈ tỷ lệ §2.3.1.  
2. Ưu tiên cảnh có **chuyển động tay + thay đổi vật liệu** rõ.  
3. Concat theo **thứ tự beat 1→7**, không sort thuần theo `start` nguồn (hook lấy từ cuối nguồn là hợp lệ).  
4. Nếu ASR phủ < ~25% thời lượng nguồn **hoặc** LLM trả clip “front-loaded” (cả cụm nằm trong ~55% đầu nguồn dài) → **bỏ LLM**, dùng heuristic cửa sổ §2.3.2.  

### 2.4 Triển khai kỹ thuật (đã áp dụng)

1. `douyin_highlight.py`: prompt 7 beat + `SOURCE_WINDOWS` / `SOURCE_WINDOWS_SHORT` + từ chối front-loaded + heuristic khi ASR sparse.  
2. `douyin_cut.py`: montage shot ~2.6s trong mỗi beat; **giữ thứ tự beat**.  
3. Hard cap tổng ≤ 180s; ưu tiên cắt bớt beat 2–3 nếu thừa, **giữ beat 1, 5, 6, 7**.  
4. Viết VO / TTS **sau** khi đã có timeline cắt — lời bám shot, không bám intro nguồn đã bỏ.  

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
- Không mô tả “cánh đồng / đi hái” dài nếu timeline short đã bỏ intro đó — lời phải khớp **cảnh đã cắt**.

### 3.4 Prompt viết lời (template tái sử dụng)

```
Viết lời thuyết minh tiếng Việt (nam Bắc, chậm, truyền cảm) cho video thủ công/di sản.
Bám caption_vi / topic_vi. Cấm lệch chủ đề dù ASR nhiễu.
Chỉ mô tả thao tác/cảnh có trên timeline đã cắt (không kể intro nguồn đã bỏ).

Cấu trúc bắt buộc:
1) Hook phản trực giác (1–2 câu) — khớp cảnh hook (thường là thành phẩm)
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
| Đồng bộ | Theo nhịp đọc TTS; mỗi câu **khít slot** timeline (pad/cắt audio cho khớp) |
| Watermark | Tuỳ kênh — nhỏ dưới phụ đề; không che tay/lửa |

---

## 5. Âm thanh

| Lớp | Mức gợi ý |
|-----|-----------|
| Voiceover | Chính (~0.85–0.95) |
| BGM gốc / nhạc | Nhẹ (~0.35–0.45) + **duck** khi có lời |
| Tiếng Trung gốc | Tắt hoặc rất nhỏ nếu chồng lời VI |

**TTS / sync (tránh lệch phụ đề & cắt đuôi):**

| Quy tắc | Chi tiết |
|---------|----------|
| Provider ưu tiên | FPT leminh → **Piper speaker 2** (ổn định) → Edge; nhiều `fpt_api_key` xoay khi 429 |
| Tốc độ | Piper `length_scale` ~1.35–1.4; mỗi câu **fit đúng slot** (`atempo` tối đa ~1.35 rồi pad/cắt) |
| Độ dài audio | Tổng TTS ≈ độ dài video cắt — **không** để TTS dài hơn rồi bị mux cắt giữa câu |
| Fallback | Khi FPT cooldown: Piper trước, không nhảy thẳng Edge nếu còn Piper |

---

## 6. Checklist QA trước khi xuất bản

- [ ] Độ dài trong **120–180s** (lý tưởng ~140–160s)  
- [ ] Có đủ 7 beat (hoặc rút gọn có lý do; vẫn còn hook + lõi + kết)  
- [ ] Shot trung bình ngắn (cảm giác “nhiều cảnh”, không 3 khối đứng)  
- [ ] **Không lan man intro**: short không chỉ toàn cánh đồng / đi hái khi chủ đề là làm bánh / nghề  
- [ ] Clip nguồn (video dài) chạm **nửa sau** — có rõ tay + liệu + thao tác  
- [ ] Hook là thành phẩm / lõi hấp dẫn, không phải 10–20s phong cảnh mở đầu  
- [ ] VO phủ gần hết video; nghe liền mạch; **không cắt đột ngột trước phụ đề**  
- [ ] Có hook + câu cầu nối + định nghĩa nghề + kết cảm xúc + CTA  
- [ ] Lời khớp `caption_vi` / chủ đề **và** khớp cảnh đang chiếu  
- [ ] Phụ đề cụm ngắn, trắng + viền đen, không che chủ thể  
- [ ] BGM không át lời; giọng ổn định (ưu tiên Piper nếu FPT lỗi)  

---

## 7. So sánh nhanh: mẫu vs lỗi đã gặp vs pipeline đúng

| | Shorts mẫu | Lỗi cần tránh | Pipeline đúng |
|--|------------|---------------|---------------|
| Cắt | ~60 shot ngắn theo quy trình | 0–150s đầu nguồn (intro) | 7 beat lệch nửa sau + montage |
| VO | Liên tục, nhiều câu | Lời nói làm bánh trên cảnh đồng | Câu ↔ thao tác trên timeline cắt |
| Đồng bộ | Câu ↔ thao tác | TTS dài hơn video → cắt đuôi | Fit từng câu vào slot |
| Cảm xúc | Hook → lõi → ẩn dụ → CTA | Hook = cánh đồng | Hook = thành phẩm / lõi |

---

## 8. Ánh xạ sang code

| Thành phần | File / chỗ chỉnh |
|------------|------------------|
| Target/max giây | `douyin_process.py`, `douyin_highlight.py` (`150` / `180`) |
| Cửa sổ nguồn / front-loaded / ASR sparse | `douyin_highlight.py` — `SOURCE_WINDOWS*`, `_is_front_loaded`, `_asr_coverage` |
| Chọn beat / clip | `douyin_highlight.py` — prompt + normalize **theo beat** |
| Cắt phụ shot ngắn | `douyin_cut.py` (montage ~2.6s) |
| Viết VO dày | `douyin_voice.py` — `_script_prompt`, `CHARS_PER_SEC` |
| TTS + fit slot + cascade key | `douyin_voice.py`, `douyin_tts_piper.py`, `douyin_tts_fpt.py` |
| Phụ đề karaoke | `douyin_subtitle.py` |
| Job UI | `douyin_ai_job.py`, admin-ui Xem trước |

Khi đổi prompt/highlight/cut: **đọc lại §2–§5** trước khi merge.

---

## 9. Lịch sử

| Ngày | Ghi chú |
|------|---------|
| 2026-10-20 | Chốt công thức từ phân tích `cnJblXj7EUk` (cắt montage + VO tài liệu 6 lớp + phụ đề karaoke) |
| 2026-10-20 | Code: `douyin_highlight` 7 beat, `douyin_cut` montage 2.6s, `douyin_voice` slot VO, `douyin_subtitle` karaoke — test `7670530751607098667` |
| 2026-10-22 | Khắc phục short lan man intro nguồn dài (ASR nghèo → LLM lấy 0–150s): cửa sổ nguồn lệch nửa sau, từ chối front-loaded, hook thành phẩm gần cuối; TTS fit slot + cascade FPT→Piper→Edge / nhiều `fpt_api_key` — case `7000587983069957383` |
