#!/usr/bin/env python3
"""
Quét Google Sheet (CÙNG tab với phần tải video), tìm các video đã tải THÀNH CÔNG,
đăng lên một hoặc nhiều Facebook Page (đăng ngay hoặc theo giờ hẹn), rồi ghi trạng thái vào lại sheet.

Cần: py -m pip install requests
Cần: Google Apps Script bản mới (apps_script_Code.gs) đã triển khai phiên bản mới.

=== Các cột trong sheet (tab đầu tiên) ===
  A Link sản phẩm | B Trạng thái | C Thời gian | D File video | E Ghi chú              <- phần tải video (chương trình ghi)
  F Page | G Link affiliate | H Nội dung | I Tag | J Giờ đăng                          <- BẠN ĐIỀN
  K Trạng thái đăng | L Đã xử lý lúc | M ID bài đăng | N Ghi chú đăng                 <- chương trình ghi
  - F: tên Page (hoặc Page ID); nhiều Page thì ngăn cách bằng dấu phẩy hoặc xuống dòng.
  - G trống thì dùng link ở cột A (kèm ghi chú), nên điền link affiliate vào G.
  - I: tag (hashtag), vd "#giadung #sale" hoặc "giadung, sale". Chương trình tự thêm dấu # và bỏ trùng.
  - J: giờ hẹn đăng, vd "04/10/2026 09:00" hoặc ô định dạng Ngày giờ. Để trống = đăng ngay.
    Giờ đã qua = đăng ngay. Cần dòng có cột B = "Thành công" (đã tải xong) và đã điền cột F.
  - Bài đăng gồm: Nội dung, rồi dòng link ("Mua tại: ..."), rồi các tag.

=== Hẹn giờ ===
  --schedule local     (mặc định) chương trình tự đăng khi đến giờ; máy phải bật và job phải đang chạy
                       (dùng --watch 5, hoặc Task Scheduler chạy mỗi 10-15 phút).
  --schedule facebook  chương trình tải video lên NGAY và nhờ Facebook tự đăng đúng giờ (máy tắt cũng được).
                       Facebook chỉ cho hẹn giờ trong khoảng từ 10 phút đến 30 ngày kể từ lúc gọi API;
                       dòng nằm ngoài khoảng đó sẽ được chờ và xử lý ở lần quét sau.
  Giờ trong sheet được hiểu theo giờ của máy tính đang chạy chương trình.

=== Quản lý Page (lưu trong pages.json cạnh script, FILE NÀY CHỨA TOKEN: giữ bí mật) ===
  py shopee_fb_post.py --exchange APP_ID APP_SECRET TOKEN_NGAN_HAN     (đổi sang token dài hạn)
  py shopee_fb_post.py --sync-pages TOKEN_DAI_HAN                      (lấy tất cả Page; chạy lại để thêm Page mới)
  py shopee_fb_post.py --add-page "Tên Page" PAGE_ID PAGE_TOKEN        (thêm tay một Page)
  py shopee_fb_post.py --list-pages                                    (xem danh sách)

=== Đăng bài ===
  1) Ghi tiêu đề cho các cột F-N:   py shopee_fb_post.py --init
  2) Chạy thử, không đăng thật:     py shopee_fb_post.py --dry-run
  3) Đăng thật:                     py shopee_fb_post.py
  4) Chạy liên tục, quét mỗi 5 phút: py shopee_fb_post.py --watch 5

Tùy chọn: --url/--token (hoặc biến môi trường SHEET_URL, SHEET_TOKEN), --tab (mặc định tab đầu tiên),
  --limit 5 (số DÒNG tối đa mỗi lần quét), --min-delay 120 --max-delay 300 (nghỉ giữa các bài, giây),
  --retry (chạy lại dòng "Lỗi"/"Một phần", chỉ đăng nốt các Page chưa thành công),
  --link-in-comment (đưa link vào bình luận đầu tiên; với bài hẹn giờ trên Facebook link vẫn nằm trong nội dung),
  --link-prefix "Mua tại: ", --videos videos, --pages pages.json, --api-version v25.0

Chỉ đăng video bạn có quyền sử dụng (của bạn, hoặc chủ video đã đồng ý).
"""
import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime

import requests

# Chỉ số cột (bắt đầu từ 0) trong sheet
C_LINK, C_DL_STATUS, C_DL_TIME, C_FILE, C_DL_NOTE = 0, 1, 2, 3, 4
C_PAGES, C_AFF, C_TEXT, C_TAGS, C_WHEN = 5, 6, 7, 8, 9
C_STATUS, C_TIME, C_IDS, C_NOTE = 10, 11, 12, 13
NCOLS = 14
POST_START_COL = 11  # cột K (đếm từ 1): nơi chương trình bắt đầu ghi kết quả đăng
POST_HEADERS = ["Page", "Link affiliate", "Nội dung", "Tag", "Giờ đăng",
                "Trạng thái đăng", "Đã xử lý lúc", "ID bài đăng", "Ghi chú đăng"]
GRAPH = "https://graph.facebook.com"
# Mã lỗi Facebook liên quan giới hạn tốc độ / bị chặn tạm thời: dừng cả lượt chạy
FATAL_CODES = {4, 17, 32, 341, 368, 613}
# Facebook cho hẹn giờ từ 10 phút đến 30 ngày; chừa lề an toàn
FB_MIN_LEAD = 12 * 60
FB_MAX_LEAD = 29 * 24 * 3600
DONE_STATUSES = ("Thành công", "Đã lên lịch")
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%H:%M %d/%m/%Y")


# ---------------------------------------------------------------- Google Sheet
class SheetClient:
    """Gọi Google Apps Script Web app để đọc/ghi sheet."""

    def __init__(self, url, token):
        self.url = url
        self.token = token

    def call(self, action, **payload):
        body = {"token": self.token, "action": action, **payload}
        last_error = None
        data = None
        for attempt in range(4):
            try:
                r = requests.post(self.url, json=body, timeout=90)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                last_error = e
                time.sleep(5 * (attempt + 1))
        if data is None:
            raise RuntimeError(
                f"Không gọi được Apps Script ({last_error}). Kiểm tra lại Web app URL và "
                "mục 'Who has access' phải là 'Anyone'."
            )
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Apps Script báo lỗi"))
        return data


# -------------------------------------------------------------------- Facebook
class FBError(Exception):
    def __init__(self, message, code=None, subcode=None, http=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http = http


def fb_check(resp):
    try:
        data = resp.json()
    except ValueError:
        raise FBError(f"Phản hồi không hợp lệ (HTTP {resp.status_code})", http=resp.status_code)
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise FBError(err.get("message", f"HTTP {resp.status_code}"),
                      err.get("code"), err.get("error_subcode"), resp.status_code)
    return data


def upload_video(page, path, message, version, schedule_ts=None):
    """Đăng video lên Page bằng một request multipart (phù hợp video nhỏ hơn ~1GB).
    Nếu có schedule_ts (unix time) thì nhờ Facebook hẹn giờ đăng."""
    url = f"{GRAPH}/{version}/{page['id']}/videos"
    data = {"description": message, "access_token": page["token"]}
    if schedule_ts:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(int(schedule_ts))
    with open(path, "rb") as f:
        resp = requests.post(
            url, data=data,
            files={"source": (os.path.basename(path), f, "video/mp4")},
            timeout=3600,
        )
    return fb_check(resp)["id"]


def post_comment(page, video_id, text, version):
    resp = requests.post(
        f"{GRAPH}/{version}/{video_id}/comments",
        data={"message": text, "access_token": page["token"]},
        timeout=60,
    )
    return fb_check(resp).get("id")


# ------------------------------------------------------------------ pages.json
def norm(s):
    return " ".join(unicodedata.normalize("NFC", str(s)).split()).lower()


def load_pages(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("pages", [])


def save_pages(path, pages):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pages": pages}, f, ensure_ascii=False, indent=2)


def find_page(pages, key):
    k = norm(key)
    for p in pages:
        if str(p["id"]).strip() == key.strip() or norm(p["name"]) == k:
            return p
    return None


def cmd_exchange(app_id, app_secret, short_token, version):
    resp = requests.get(
        f"{GRAPH}/{version}/oauth/access_token",
        params={"grant_type": "fb_exchange_token", "client_id": app_id,
                "client_secret": app_secret, "fb_exchange_token": short_token},
        timeout=60,
    )
    data = fb_check(resp)
    print("Token dài hạn (giữ bí mật, dùng cho --sync-pages):\n")
    print(data["access_token"])
    if data.get("expires_in"):
        print(f"\nHiệu lực khoảng {int(data['expires_in']) // 86400} ngày.")


def cmd_sync_pages(user_token, version, path):
    url = f"{GRAPH}/{version}/me/accounts"
    params = {"fields": "id,name,access_token", "limit": 100, "access_token": user_token}
    found = []
    while url:
        data = fb_check(requests.get(url, params=params, timeout=60))
        found += data.get("data", [])
        url = data.get("paging", {}).get("next")
        params = None

    pages = load_pages(path)
    by_id = {str(p["id"]): p for p in pages}
    added = updated = 0
    for fp in found:
        pid = str(fp["id"])
        if pid in by_id:
            by_id[pid]["token"] = fp["access_token"]  # giữ nguyên tên bạn đã đặt, chỉ cập nhật token
            updated += 1
        else:
            pages.append({"name": fp["name"], "id": pid, "token": fp["access_token"]})
            added += 1
    save_pages(path, pages)
    print(f"Facebook trả về {len(found)} Page. Thêm mới: {added} | Cập nhật token: {updated}")
    print(f"Đã lưu vào {os.path.abspath(path)} (file chứa token, đừng chia sẻ).")
    if not found:
        print("Không có Page nào: kiểm tra token có quyền pages_show_list và bạn là quản trị viên Page.")


def cmd_add_page(name, pid, token, path):
    pages = load_pages(path)
    for p in pages:
        if str(p["id"]) == pid:
            p["name"], p["token"] = name, token
            break
    else:
        pages.append({"name": name, "id": pid, "token": token})
    save_pages(path, pages)
    print(f"Đã lưu Page '{name}' ({pid}) vào {path}")


def cmd_list_pages(path):
    pages = load_pages(path)
    if not pages:
        print(f"Chưa có Page nào trong {path}. Dùng --sync-pages hoặc --add-page.")
        return
    print(f"{len(pages)} Page trong {path}:")
    for p in pages:
        print(f"  - {p['name']}  (ID: {p['id']})")


# -------------------------------------------------------------------- đăng bài
def resolve_video(videos_dir, value):
    v = value.strip()
    if not v:
        return None
    if os.path.isfile(v):
        return v
    name = os.path.basename(v.replace("\\", "/"))
    p = os.path.join(videos_dir, name)
    return p if os.path.isfile(p) else None


def parse_pages(cell):
    out, seen = [], set()
    for p in re.split(r"[,;\n]+", cell):
        p = p.strip()
        if p and norm(p) not in seen:
            seen.add(norm(p))
            out.append(p)
    return out


def parse_tags(cell):
    """'#giadung, sale  #Mới_nhất' -> ['#giadung', '#sale', '#Mới_nhất'] (bỏ trùng, bỏ ký tự lạ)."""
    out, seen = [], set()
    for t in re.split(r"[\s,;#]+", unicodedata.normalize("NFC", cell)):
        t = re.sub(r"\W", "", t)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append("#" + t)
    return out


def parse_time(s):
    s = " ".join(str(s).split())
    if not s:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError(f"Giờ đăng '{s}' không đọc được. Nhập dạng 04/10/2026 09:00 "
                     "(ngày/tháng/năm giờ:phút) hoặc dùng ô định dạng Ngày giờ.")


def decide(cells, args, now):
    """Trả về (hành động, lỗi, giờ hẹn): 'now' | 'schedule' | 'wait' | 'error'."""
    try:
        when = parse_time(cells[C_WHEN])
    except ValueError as e:
        return "error", str(e), None
    if when is None or when <= now:
        return "now", None, when
    lead = (when - now).total_seconds()
    if args.schedule == "facebook" and FB_MIN_LEAD <= lead <= FB_MAX_LEAD:
        return "schedule", None, when
    return "wait", None, when


def wait_reason(when, args, now):
    lead = (when - now).total_seconds()
    mins = int(lead // 60)
    if args.schedule == "facebook":
        if lead < FB_MIN_LEAD:
            return (f"còn {mins} phút nữa: ngắn hơn mức tối thiểu để hẹn giờ trên Facebook (khoảng 10 phút), "
                    "nên chờ đến giờ rồi đăng ngay")
        if lead > FB_MAX_LEAD:
            return f"còn khoảng {lead / 86400:.0f} ngày nữa: xa hơn 30 ngày, Facebook chưa cho hẹn giờ"
    return f"còn {mins} phút nữa mới đến giờ (chế độ local: đăng khi đến giờ)"


def build_message(text, link, prefix, link_in_comment, tags):
    parts = []
    if text.strip():
        parts.append(text.strip())
    if link.strip() and not link_in_comment:
        parts.append(f"{prefix}{link.strip()}")
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)


def write_post(client, args, link, hint, status, ids_lines, note, with_time=True):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if with_time else ""
    res = client.call("tab_update", tab=args.tab, hint=hint, key_cols=[1], key=link,
                      start_col=POST_START_COL,
                      values=[status, stamp, "\n".join(ids_lines), note[:500]])
    if not res.get("found"):
        print("  (không tìm thấy lại dòng này trong sheet, bỏ qua ghi kết quả)")


def select_rows(values, args):
    todo, stuck, no_page, waiting = [], [], 0, []
    now = datetime.now()
    for idx, cells in enumerate(values[1:], start=2):
        cells = (cells + [""] * NCOLS)[:NCOLS]
        link = cells[C_LINK].strip()
        if not link.lower().startswith("http"):
            continue
        if cells[C_DL_STATUS].strip() != "Thành công":
            continue                      # chưa tải xong video thì chưa đăng
        if not parse_pages(cells[C_PAGES]):
            no_page += 1
            continue
        status = cells[C_STATUS].strip()
        if status in DONE_STATUSES:
            continue
        if status == "Đang xử lý":
            stuck.append(idx)
            continue
        if status.startswith(("Lỗi", "Một phần")) and not args.retry:
            continue
        action, _, when = decide(cells, args, now)
        if action == "wait":
            waiting.append((idx, when, wait_reason(when, args, now)))
            continue
        todo.append((idx, cells))
    return todo, stuck, no_page, waiting


def run_posting(args):
    client = SheetClient(args.url, args.token)
    pages_cfg = load_pages(args.pages)

    values = client.call("tab_list", tab=args.tab, ncols=NCOLS)["values"]
    todo, stuck, no_page, waiting = select_rows(values, args)

    if stuck:
        print("Có dòng đang ở trạng thái 'Đang xử lý' (bị dừng giữa chừng): "
              f"{', '.join(map(str, stuck))}.\n"
              "Chương trình KHÔNG tự đăng lại các dòng này để tránh đăng trùng. "
              "Hãy kiểm tra trên Facebook; nếu chưa có bài thì xóa ô 'Trạng thái đăng' (cột K) của dòng đó để chạy lại.\n")
    if no_page:
        print(f"Có {no_page} dòng đã tải xong nhưng chưa điền Page (cột F) nên được bỏ qua.\n")
    if waiting:
        print(f"Có {len(waiting)} dòng chưa được đăng lần này (xem cột J - Giờ đăng):")
        for w_row, w_when, w_reason in waiting:
            print(f"  - Dòng {w_row}: giờ đăng {w_when:%d/%m/%Y %H:%M} -> {w_reason}")
        print()
    if not todo:
        print("Không có dòng nào cần đăng.")
        return

    todo = todo[: args.limit]
    print(f"Sẽ xử lý {len(todo)} dòng.{' (CHẠY THỬ, không đăng thật)' if args.dry_run else ''}\n")

    ok = sched = part = fail = 0
    state = {"uploads": 0, "uploading": False}
    cur = None
    try:
        for i, (row, cells) in enumerate(todo, 1):
            link = cells[C_LINK].strip()
            text = cells[C_TEXT].strip()
            aff = cells[C_AFF].strip()
            tags = parse_tags(cells[C_TAGS])
            page_keys = parse_pages(cells[C_PAGES])
            ids_lines = [l.strip() for l in cells[C_IDS].splitlines() if l.strip()]
            done = parse_done(cells[C_IDS])
            video = resolve_video(args.videos, cells[C_FILE])
            print(f"[{i}/{len(todo)}] Dòng {row}: {link[:80]}")

            action, time_error, when = decide(cells, args, datetime.now())
            if action == "wait":
                print("  (chưa đến giờ đăng, bỏ qua lần này)")
                continue

            use_link = aff or link
            notes = [] if aff else ["Cột G (Link affiliate) trống nên dùng link ở cột A"]
            link_comment = args.link_in_comment and action != "schedule"
            if args.link_in_comment and action == "schedule":
                notes.append("Hẹn giờ trên Facebook nên link được đặt trong nội dung bài "
                             "(chưa thể bình luận trước khi bài được đăng)")
            message = build_message(text, use_link, args.link_prefix, link_comment, tags)

            errors, targets = [], []
            if time_error:
                errors.append(time_error)
            if not video:
                errors.append(f"Không thấy file video '{cells[C_FILE].strip()}' (cột D) trong {args.videos}")
            for key in page_keys:
                page = find_page(pages_cfg, key)
                if not page:
                    errors.append(f"Không thấy Page '{key}' trong {args.pages}")
                elif str(page["id"]) in done:
                    print(f"  (đã đăng trước đó lên '{page['name']}', bỏ qua)")
                else:
                    targets.append(page)

            if args.dry_run:
                for e in errors:
                    print("  -> LỖI:", e)
                if video and targets and not time_error:
                    size = os.path.getsize(video) / (1024 * 1024)
                    if action == "schedule":
                        when_txt = f"hẹn giờ trên Facebook lúc {when:%d/%m/%Y %H:%M}"
                    else:
                        when_txt = "đăng ngay"
                    print(f"  -> sẽ {when_txt}: {video} ({size:.1f} MB) lên: {', '.join(p['name'] for p in targets)}")
                    print("     nội dung: " + (message.replace("\n", " | ")[:250] or "(trống)"))
                    if link_comment:
                        print("     bình luận đầu tiên:", use_link)
                    for n in notes:
                        print("     lưu ý:", n)
                if errors:
                    fail += 1
                else:
                    ok += 1
                continue

            cur = {"row": row, "link": link, "ids": ids_lines}
            write_post(client, args, link, row, "Đang xử lý", ids_lines, "", with_time=False)
            fatal = False

            if video and not time_error:
                for page in targets:
                    if state["uploads"] > 0:
                        pause = random.randint(args.min_delay, args.max_delay)
                        print(f"  Nghỉ {pause} giây...")
                        time.sleep(pause)
                    state["uploads"] += 1
                    print(f"  -> {'hẹn giờ' if action == 'schedule' else 'đăng'} lên '{page['name']}'...")
                    try:
                        state["uploading"] = True
                        post_id = upload_video(page, video, message, args.api_version,
                                               schedule_ts=when.timestamp() if action == "schedule" else None)
                        state["uploading"] = False
                        ids_lines.append(f"{page['name']} [{page['id']}] :: {post_id}")
                        write_post(client, args, link, row, "Đang xử lý", ids_lines, "", with_time=False)
                        if link_comment and use_link:
                            try:
                                post_comment(page, post_id, use_link, args.api_version)
                            except FBError as e:
                                notes.append(f"{page['name']}: đã đăng video nhưng không đăng được bình luận: {e}")
                        print(f"     Thành công (ID {post_id})")
                    except FBError as e:
                        state["uploading"] = False
                        msg = f"{page['name']}: Facebook báo lỗi {e.code}: {e}"
                        if e.code == 190:
                            msg += " (token hết hạn/không hợp lệ: chạy lại --sync-pages)"
                        if e.code in FATAL_CODES:
                            msg += " (bị giới hạn/chặn tạm thời: dừng lượt chạy)"
                            fatal = True
                        errors.append(msg)
                        print("     LỖI:", msg)
                        if fatal:
                            break
                    except requests.RequestException as e:
                        state["uploading"] = False
                        errors.append(f"{page['name']}: lỗi mạng khi tải lên, KHÔNG chắc đã đăng hay chưa "
                                      f"(hãy kiểm tra trên Facebook trước khi chạy lại): {e}")
                        print("     LỖI mạng:", e)
                    except OSError as e:
                        state["uploading"] = False
                        errors.append(f"{page['name']}: không đọc được file video: {e}")

            done_count = len(parse_done("\n".join(ids_lines)))
            if action == "schedule" and done_count:
                notes.append(f"Đã hẹn giờ đăng trên Facebook lúc {when:%d/%m/%Y %H:%M}")
            if not errors:
                if action == "schedule":
                    status = "Đã lên lịch"
                    sched += 1
                else:
                    status = "Thành công"
                    ok += 1
            elif done_count > 0:
                status = "Một phần"
                part += 1
            else:
                status = "Lỗi"
                fail += 1
            write_post(client, args, link, row, status, ids_lines, "\n".join(errors + notes))
            cur = None
            print("  =>", status)
            if fatal:
                print("\nDừng lượt chạy vì Facebook đang giới hạn/chặn tạm thời. Thử lại sau vài giờ.")
                break
    except KeyboardInterrupt:
        print("\nĐã dừng theo yêu cầu (Ctrl+C).")
        if cur and not args.dry_run:
            try:
                n_done = len(parse_done("\n".join(cur["ids"])))
                if state["uploading"]:
                    write_post(client, args, cur["link"], cur["row"], "Đang xử lý", cur["ids"],
                               "Bị dừng khi đang tải lên: kiểm tra Facebook rồi sửa trạng thái thủ công")
                elif n_done:
                    write_post(client, args, cur["link"], cur["row"], "Một phần", cur["ids"],
                               "Bị dừng giữa chừng, chạy lại với --retry để đăng nốt")
                else:
                    write_post(client, args, cur["link"], cur["row"], "", [], "", with_time=False)
            except Exception:  # noqa: BLE001
                pass
        raise

    if args.dry_run:
        print(f"\nXong (chạy thử). Hợp lệ: {ok} | Lỗi: {fail}.")
    else:
        print(f"\nXong. Thành công: {ok} | Đã lên lịch: {sched} | Một phần: {part} | Lỗi: {fail}.")


def parse_done(ids_cell):
    """Đọc cột ID bài đăng: mỗi dòng dạng 'Tên Page [PAGE_ID] :: ID_BÀI' -> {PAGE_ID: ID_BÀI}."""
    return dict(re.findall(r"\[([^\]]+)\]\s*::\s*(\S+)", ids_cell))


def main():
    ap = argparse.ArgumentParser(description="Quét sheet và đăng video đã tải lên nhiều Facebook Page.")
    ap.add_argument("--url", default=os.environ.get("SHEET_URL"), help="Web app URL của Apps Script")
    ap.add_argument("--token", default=os.environ.get("SHEET_TOKEN"), help="TOKEN trong Code.gs")
    ap.add_argument("--tab", default="", help="Tên tab (mặc định: tab đầu tiên, cùng tab với tải video)")
    ap.add_argument("--videos", default="videos")
    ap.add_argument("--pages", default="pages.json")
    ap.add_argument("--limit", type=int, default=5, help="Số dòng tối đa mỗi lần quét")
    ap.add_argument("--min-delay", type=int, default=120)
    ap.add_argument("--max-delay", type=int, default=300)
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--watch", type=int, metavar="PHUT", help="Chạy liên tục, quét lại mỗi PHUT phút")
    ap.add_argument("--schedule", choices=["local", "facebook"], default="local",
                    help="local: tự đăng khi đến giờ (máy phải bật); facebook: nhờ Facebook hẹn giờ")
    ap.add_argument("--link-in-comment", action="store_true")
    ap.add_argument("--link-prefix", default="Mua tại: ")
    ap.add_argument("--api-version", default="v25.0")
    # quản lý Page / token
    ap.add_argument("--exchange", nargs=3, metavar=("APP_ID", "APP_SECRET", "TOKEN_NGAN_HAN"))
    ap.add_argument("--sync-pages", metavar="TOKEN_DAI_HAN")
    ap.add_argument("--add-page", nargs=3, metavar=("TEN", "PAGE_ID", "PAGE_TOKEN"))
    ap.add_argument("--list-pages", action="store_true")
    args = ap.parse_args()

    try:
        if args.exchange:
            cmd_exchange(*args.exchange, args.api_version)
            return
        if args.sync_pages:
            cmd_sync_pages(args.sync_pages, args.api_version, args.pages)
            return
        if args.add_page:
            cmd_add_page(*args.add_page, args.pages)
            return
        if args.list_pages:
            cmd_list_pages(args.pages)
            return
    except FBError as e:
        print(f"Facebook báo lỗi {e.code}: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print("Lỗi mạng:", e)
        sys.exit(1)

    if not args.url or not args.token:
        ap.error("Cần --url và --token (hoặc đặt biến môi trường SHEET_URL, SHEET_TOKEN)")
    if args.max_delay < args.min_delay:
        args.max_delay = args.min_delay

    if args.init:
        try:
            SheetClient(args.url, args.token).call(
                "tab_set_header", tab=args.tab, start_col=6, headers=POST_HEADERS)
        except RuntimeError as e:
            print("Lỗi:", e)
            print("Nhớ cập nhật Apps Script bản mới và triển khai phiên bản mới.")
            sys.exit(1)
        print("Đã ghi tiêu đề các cột F-N: " + " | ".join(POST_HEADERS))
        print("Bạn điền: F (Page), G (Link affiliate), H (Nội dung), I (Tag), J (Giờ đăng).")
        print("Gợi ý: đặt cột J là định dạng Ngày giờ; File > Cài đặt: Ngôn ngữ = Việt Nam, múi giờ = (GMT+07:00) Hà Nội.")
        return

    try:
        if args.watch:
            print(f"Chế độ theo dõi: quét mỗi {args.watch} phút. Bấm Ctrl+C để dừng.\n")
            while True:
                try:
                    run_posting(args)
                except RuntimeError as e:
                    print("Lỗi:", e)
                print(f"\nĐợi {args.watch} phút rồi quét lại...\n")
                time.sleep(args.watch * 60)
        else:
            try:
                run_posting(args)
            except RuntimeError as e:
                print("Lỗi:", e)
                sys.exit(1)
    except KeyboardInterrupt:
        print("\nĐã dừng.")


if __name__ == "__main__":
    main()
