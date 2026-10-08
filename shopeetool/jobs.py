"""Các công việc chính: tải video theo link trong Google Sheet, đăng video lên Facebook Page."""
import os
import random
import re
import threading
import time
import traceback
import unicodedata
from datetime import datetime

import requests

from . import config as cfgmod
from .facebook import (FATAL_CODES, FBError, find_page, hint_for, norm, post_comment,
                       upload_video)
from .logger import Cancelled
from .shopee import ShopeeError, ShopeeSession, download_file, pick_best, product_id
from .sheet import SheetClient, SheetError

# Chỉ số cột (bắt đầu từ 0) trong sheet
C_LINK, C_DL_STATUS, C_DL_TIME, C_FILE, C_DL_NOTE = 0, 1, 2, 3, 4
C_PAGES, C_AFF, C_TEXT, C_TAGS, C_WHEN = 5, 6, 7, 8, 9
C_STATUS, C_TIME, C_IDS, C_NOTE = 10, 11, 12, 13
NCOLS = 14
POST_START_COL = 11  # cột K (đếm từ 1)
FB_MIN_LEAD = 12 * 60            # Facebook cho hẹn giờ từ 10 phút; chừa lề an toàn
FB_MAX_LEAD = 29 * 24 * 3600     # đến 30 ngày; chừa lề an toàn
DONE_STATUSES = ("Thành công", "Đã lên lịch")
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%H:%M %d/%m/%Y")

MODES = {
    "download": "Chỉ tải video",
    "post": "Chỉ đăng Facebook",
    "download_post": "Tải rồi đăng (lần lượt)",
    "parallel": "Tải và đăng song song",
}


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_client(cfg):
    s = cfg["sheet"]
    return SheetClient(s["url"], s["token"], s.get("tab", ""))


# ================================================================== TẢI VIDEO
def _dl_write(ctx, client, link, hint, status, file="", note="", with_time=True):
    stamp = _now_str() if with_time else ""
    res = client.tab_update(hint, link, 2, [status, stamp, file, note[:500]])
    if not res.get("found"):
        ctx.warn("Không tìm thấy lại dòng này trong sheet (có thể bạn vừa xóa/di chuyển dòng), bỏ qua ghi kết quả.")


def run_download(cfg, ctx, dry_run=False, retry=False):
    sc = cfg["shopee"]
    client = make_client(cfg)
    values = client.tab_list(5)

    todo = []
    for idx, cells in enumerate(values[1:], start=2):
        link = cells[0].strip() if len(cells) > 0 else ""
        status = cells[1].strip() if len(cells) > 1 else ""
        if not link.lower().startswith("http"):
            continue
        if status == "Thành công":
            continue
        if status.startswith("Lỗi") and not retry:
            continue
        todo.append((idx, link))

    if not todo:
        ctx.info("[Tải] Không có link nào cần tải (thêm link mới ở cột A, hoặc bật 'Chạy lại dòng lỗi').")
        return
    limit = cfgmod.to_int(sc.get("limit"), 10, 1)
    todo = todo[:limit]
    out_dir = cfgmod.videos_dir(cfg)
    ctx.info(f"[Tải] Sẽ xử lý {len(todo)} link. Thư mục lưu video: {out_dir}"
             + (" (CHẠY THỬ, không tải thật)" if dry_run else ""))

    if dry_run:
        for row, link in todo:
            ctx.info(f"[Tải] Dòng {row}: sẽ tải {link[:80]}", job="download", row=row)
            ctx.stat("dl_plan")
        return

    os.makedirs(out_dir, exist_ok=True)
    need_browser = any(not os.path.exists(os.path.join(out_dir, product_id(lk, r) + ".mp4")) for r, lk in todo)
    session = ShopeeSession(cfg, ctx).__enter__() if need_browser else None
    min_d = cfgmod.to_int(sc.get("min_delay"), 30)
    max_d = max(min_d, cfgmod.to_int(sc.get("max_delay"), 90))
    wait = cfgmod.to_int(sc.get("wait_seconds"), 60, 10)
    current = None
    try:
        for i, (row, link) in enumerate(todo, 1):
            ctx.check()
            current = (row, link)
            path = os.path.join(out_dir, product_id(link, row) + ".mp4")
            ctx.info(f"[Tải {i}/{len(todo)}] Dòng {row}: {link[:70]}", job="download", row=row)
            _dl_write(ctx, client, link, row, "Đang xử lý", with_time=False)
            status, note = "Lỗi", ""
            try:
                if os.path.exists(path):
                    status, note = "Thành công", "File đã có sẵn, bỏ qua tải lại"
                else:
                    urls, info = session.capture(link, wait)
                    if not urls:
                        note = "Không bắt được link video (sản phẩm có thể không có video)"
                        low = info.lower()
                        if "login" in low or "verify" in low or "captcha" in low:
                            note += (". Shopee có vẻ đang yêu cầu đăng nhập/xác minh: vào Cấu hình > Shopee > "
                                     "'Đăng nhập Shopee'")
                        elif info:
                            note += f" [{info[:100]}]"
                    else:
                        download_file(pick_best(urls), path, ctx)
                        status = "Thành công"
            except ShopeeError as e:
                note = str(e)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                note = f"Lỗi không xác định: {str(e)[:150]}"
                ctx.log("error", traceback.format_exc())

            _dl_write(ctx, client, link, row, status, path if status == "Thành công" else "", note)
            current = None
            ctx.result("Tải", row, status, note)
            if status == "Thành công":
                ctx.stat("dl_ok")
                ctx.ok(f"[Tải] Dòng {row}: thành công -> {os.path.basename(path)}", job="download", row=row)
            else:
                ctx.stat("dl_fail")
                ctx.error(f"[Tải] Dòng {row}: {note}", job="download", row=row)

            if i < len(todo):
                pause = random.randint(min_d, max_d)
                ctx.info(f"[Tải] Nghỉ {pause} giây trước link tiếp theo...")
                if not ctx.sleep(pause):
                    raise Cancelled()
    except Cancelled:
        if current:
            try:
                _dl_write(ctx, client, current[1], current[0], "", "", "", with_time=False)
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        if session:
            session.__exit__(None, None, None)


# ================================================================== ĐĂNG FACEBOOK
def norm_nfc(s):
    return unicodedata.normalize("NFC", s)


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
    for t in re.split(r"[\s,;#]+", norm_nfc(cell)):
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


def parse_done(ids_cell):
    """Cột ID bài đăng: mỗi dòng 'Tên Page [PAGE_ID] :: ID_BÀI' -> {PAGE_ID: ID_BÀI}."""
    return dict(re.findall(r"\[([^\]]+)\]\s*::\s*(\S+)", ids_cell))


def decide(cells, schedule_mode, now):
    """(hành động, lỗi, giờ hẹn): 'now' | 'schedule' | 'wait' | 'error'."""
    try:
        when = parse_time(cells[C_WHEN])
    except ValueError as e:
        return "error", str(e), None
    if when is None or when <= now:
        return "now", None, when
    lead = (when - now).total_seconds()
    if schedule_mode == "facebook" and FB_MIN_LEAD <= lead <= FB_MAX_LEAD:
        return "schedule", None, when
    return "wait", None, when


def wait_reason(when, schedule_mode, now):
    lead = (when - now).total_seconds()
    mins = int(lead // 60)
    if schedule_mode == "facebook":
        if lead < FB_MIN_LEAD:
            return (f"còn {mins} phút nữa: ngắn hơn mức tối thiểu để hẹn giờ trên Facebook (~10 phút), "
                    "sẽ đăng ngay khi đến giờ")
        if lead > FB_MAX_LEAD:
            return f"còn khoảng {lead / 86400:.0f} ngày nữa: xa hơn 30 ngày, Facebook chưa cho hẹn giờ"
    return f"còn {mins} phút nữa mới đến giờ (đăng khi đến giờ, chương trình cần đang chạy)"


def build_message(text, link, prefix, link_in_comment, tags):
    parts = []
    if text.strip():
        parts.append(text.strip())
    if link.strip() and not link_in_comment:
        parts.append(f"{prefix}{link.strip()}")
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)


def resolve_video(videos_dir, value):
    v = value.strip()
    if not v:
        return None
    if os.path.isfile(v):
        return v
    name = os.path.basename(v.replace("\\", "/"))
    for cand in ([name] if os.path.splitext(name)[1] else [name + ".mp4"]):
        p = os.path.join(videos_dir, cand)
        if os.path.isfile(p):
            return p
    return None


def _post_write(ctx, client, link, hint, status, ids_lines, note, with_time=True):
    stamp = _now_str() if with_time else ""
    res = client.tab_update(hint, link, POST_START_COL, [status, stamp, "\n".join(ids_lines), note[:500]])
    if not res.get("found"):
        ctx.warn("Không tìm thấy lại dòng này trong sheet, bỏ qua ghi kết quả.")


def run_post(cfg, ctx, dry_run=False, retry=False, quiet=False, sleep_state=None):
    fc = cfg["facebook"]
    schedule_mode = fc.get("schedule_mode", "local")
    version = fc.get("api_version", "v25.0")
    prefix = fc.get("link_prefix", "Mua tại: ")
    link_in_comment_opt = bool(fc.get("link_in_comment"))
    limit = cfgmod.to_int(fc.get("limit"), 5, 1)
    min_d = cfgmod.to_int(fc.get("min_delay"), 10)
    max_d = max(min_d, cfgmod.to_int(fc.get("max_delay"), 30))
    pages_cfg = cfg.get("pages", [])
    vdir = cfgmod.videos_dir(cfg)
    if sleep_state is None:
        sleep_state = {"uploads": 0}

    client = make_client(cfg)
    values = client.tab_list(NCOLS)

    # ----- chọn dòng cần đăng
    now = datetime.now()
    todo, stuck, no_page, waiting = [], [], 0, []
    for idx, cells in enumerate(values[1:], start=2):
        cells = (cells + [""] * NCOLS)[:NCOLS]
        link = cells[C_LINK].strip()
        if not link.lower().startswith("http"):
            continue
        if cells[C_DL_STATUS].strip() != "Thành công":
            continue
        if not parse_pages(cells[C_PAGES]):
            no_page += 1
            continue
        status = cells[C_STATUS].strip()
        if status in DONE_STATUSES:
            continue
        if status == "Đang xử lý":
            stuck.append(idx)
            continue
        if status.startswith(("Lỗi", "Một phần")) and not retry:
            continue
        action, _, when = decide(cells, schedule_mode, now)
        if action == "wait":
            waiting.append((idx, when, wait_reason(when, schedule_mode, now)))
            continue
        todo.append((idx, cells))

    ctx.set_stat("post_wait", len(waiting))
    if stuck:
        ctx.warn("[Đăng] Có dòng đang ở trạng thái 'Đang xử lý' (bị dừng giữa chừng): "
                 f"{', '.join(map(str, stuck))}. Chương trình KHÔNG tự đăng lại để tránh đăng trùng. "
                 "Hãy kiểm tra trên Facebook; nếu chưa có bài thì xóa ô 'Trạng thái đăng' (cột K) của dòng đó.")
    if no_page and not quiet:
        ctx.info(f"[Đăng] Có {no_page} dòng đã tải xong nhưng chưa điền Page (cột F) nên được bỏ qua.")
    if waiting and not quiet:
        ctx.info(f"[Đăng] Có {len(waiting)} dòng chưa đến lúc đăng (cột J - Giờ đăng):")
        for w_row, w_when, w_reason in waiting:
            ctx.info(f"   - Dòng {w_row}: giờ {w_when:%d/%m/%Y %H:%M} -> {w_reason}")
    if not todo:
        if not quiet:
            ctx.info("[Đăng] Không có dòng nào cần đăng.")
        return

    todo = todo[:limit]
    ctx.info(f"[Đăng] Sẽ xử lý {len(todo)} dòng." + (" (CHẠY THỬ, không đăng thật)" if dry_run else ""))

    cur = None
    uploading = False
    try:
        for i, (row, cells) in enumerate(todo, 1):
            ctx.check()
            link = cells[C_LINK].strip()
            text = cells[C_TEXT].strip()
            aff = cells[C_AFF].strip()
            tags = parse_tags(cells[C_TAGS])
            page_keys = parse_pages(cells[C_PAGES])
            ids_lines = [ln.strip() for ln in cells[C_IDS].splitlines() if ln.strip()]
            done = parse_done(cells[C_IDS])
            video = resolve_video(vdir, cells[C_FILE])
            ctx.info(f"[Đăng {i}/{len(todo)}] Dòng {row}: {link[:70]}", job="post", row=row)

            action, time_error, when = decide(cells, schedule_mode, datetime.now())
            if action == "wait":
                ctx.info("   (chưa đến giờ đăng, bỏ qua lần này)")
                continue

            use_link = aff or link
            notes = [] if aff else ["Cột G (Link affiliate) trống nên dùng link ở cột A"]
            link_comment = link_in_comment_opt and action != "schedule"
            if link_in_comment_opt and action == "schedule":
                notes.append("Hẹn giờ trên Facebook nên link được đặt trong nội dung bài "
                             "(chưa thể bình luận trước khi bài được đăng)")
            message = build_message(text, use_link, prefix, link_comment, tags)

            errors, targets = [], []
            if time_error:
                errors.append(time_error)
            if not video:
                errors.append(f"Không thấy file video '{cells[C_FILE].strip()}' (cột D) trong {vdir}")
            for key in page_keys:
                page = find_page(pages_cfg, key)
                if not page:
                    errors.append(f"Không thấy Page '{key}' trong Cấu hình > Facebook")
                elif not page.get("enabled", True):
                    errors.append(f"Page '{page['name']}' đang bị tắt trong Cấu hình > Facebook")
                elif str(page["id"]) in done:
                    ctx.info(f"   (đã đăng trước đó lên '{page['name']}', bỏ qua)")
                else:
                    targets.append(page)

            if dry_run:
                for e in errors:
                    ctx.error(f"   LỖI dòng {row}: {e}", job="post", row=row)
                if video and targets and not time_error:
                    size = os.path.getsize(video) / (1024 * 1024)
                    when_txt = (f"hẹn giờ trên Facebook lúc {when:%d/%m/%Y %H:%M}"
                                if action == "schedule" else "đăng ngay")
                    ctx.info(f"   -> sẽ {when_txt}: {os.path.basename(video)} ({size:.1f} MB) lên: "
                             f"{', '.join(p['name'] for p in targets)}")
                    ctx.info("      nội dung: " + (message.replace("\n", " | ")[:250] or "(trống)"))
                    for n in notes:
                        ctx.warn(f"      lưu ý: {n}")
                ctx.stat("post_plan" if not errors else "post_fail")
                ctx.result("Đăng (thử)", row, "Hợp lệ" if not errors else "Lỗi", "; ".join(errors))
                continue

            cur = {"row": row, "link": link, "ids": ids_lines}
            _post_write(ctx, client, link, row, "Đang xử lý", ids_lines, "", with_time=False)
            fatal = False

            if video and not time_error:
                for page in targets:
                    if sleep_state["uploads"] > 0:
                        pause = random.randint(min_d, max_d)
                        if pause:
                            ctx.info(f"   Nghỉ {pause} giây...")
                            if not ctx.sleep(pause):
                                raise Cancelled()
                    sleep_state["uploads"] += 1
                    ctx.info(f"   -> {'hẹn giờ' if action == 'schedule' else 'đăng'} lên '{page['name']}'...")
                    try:
                        uploading = True
                        post_id = upload_video(page, video, message, version,
                                               schedule_ts=when.timestamp() if action == "schedule" else None)
                        uploading = False
                        ids_lines.append(f"{page['name']} [{page['id']}] :: {post_id}")
                        _post_write(ctx, client, link, row, "Đang xử lý", ids_lines, "", with_time=False)
                        if link_comment and use_link:
                            try:
                                post_comment(page, post_id, use_link, version)
                            except FBError as e:
                                notes.append(f"{page['name']}: đã đăng video nhưng không đăng được bình luận: {e}")
                                ctx.warn(f"   Không đăng được bình luận cho '{page['name']}': {e}")
                        ctx.ok(f"   '{page['name']}': thành công (ID {post_id})", job="post", row=row)
                    except FBError as e:
                        uploading = False
                        msg = f"{page['name']}: Facebook báo lỗi {e.code}: {e}"
                        h = hint_for(e)
                        if h:
                            msg += f" -> {h}"
                        if e.code in FATAL_CODES:
                            fatal = True
                        errors.append(msg)
                        ctx.error(f"   {msg}", job="post", row=row)
                        if fatal:
                            break
                    except requests.RequestException as e:
                        uploading = False
                        msg = (f"{page['name']}: lỗi mạng khi tải lên, KHÔNG chắc đã đăng hay chưa "
                               f"(kiểm tra trên Facebook trước khi chạy lại): {str(e)[:120]}")
                        errors.append(msg)
                        ctx.error(f"   {msg}", job="post", row=row)
                    except OSError as e:
                        uploading = False
                        errors.append(f"{page['name']}: không đọc được file video: {e}")
                        ctx.error(f"   {errors[-1]}", job="post", row=row)

            done_count = len(parse_done("\n".join(ids_lines)))
            if action == "schedule" and done_count:
                notes.append(f"Đã hẹn giờ đăng trên Facebook lúc {when:%d/%m/%Y %H:%M}")
            if not errors:
                if action == "schedule":
                    status = "Đã lên lịch"
                    ctx.stat("post_sched")
                else:
                    status = "Thành công"
                    ctx.stat("post_ok")
            elif done_count > 0:
                status = "Một phần"
                ctx.stat("post_part")
            else:
                status = "Lỗi"
                ctx.stat("post_fail")
            note = "\n".join(errors + notes)
            _post_write(ctx, client, link, row, status, ids_lines, note)
            cur = None
            ctx.result("Đăng", row, status, note.replace("\n", "; "))
            (ctx.ok if status in DONE_STATUSES else ctx.warn)(f"[Đăng] Dòng {row}: {status}", job="post", row=row)
            if fatal:
                ctx.error("Dừng lượt đăng vì Facebook đang giới hạn/chặn tạm thời. Thử lại sau vài giờ.")
                break
    except Cancelled:
        if cur and not dry_run:
            try:
                n_done = len(parse_done("\n".join(cur["ids"])))
                if uploading:
                    _post_write(ctx, client, cur["link"], cur["row"], "Đang xử lý", cur["ids"],
                                "Bị dừng khi đang tải lên: kiểm tra Facebook rồi sửa trạng thái thủ công")
                elif n_done:
                    _post_write(ctx, client, cur["link"], cur["row"], "Một phần", cur["ids"],
                                "Bị dừng giữa chừng, bật 'Chạy lại dòng lỗi' để đăng nốt")
                else:
                    _post_write(ctx, client, cur["link"], cur["row"], "", [], "", with_time=False)
            except Exception:  # noqa: BLE001
                pass
        raise


# ================================================================== ĐIỀU PHỐI
def _guard(ctx, label, fn):
    """Chạy fn, ghi lỗi (trừ Cancelled) vào nhật ký thay vì làm sập cả lượt."""
    try:
        fn()
        return True
    except Cancelled:
        raise
    except (SheetError, ShopeeError) as e:
        ctx.error(f"[{label}] {e}")
    except FBError as e:
        h = hint_for(e)
        ctx.error(f"[{label}] Facebook báo lỗi {e.code}: {e}" + (f" -> {h}" if h else ""))
    except requests.RequestException as e:
        ctx.error(f"[{label}] Lỗi mạng: {str(e)[:150]}")
    except Exception as e:  # noqa: BLE001
        ctx.error(f"[{label}] Lỗi không mong muốn: {e}")
        ctx.log("error", traceback.format_exc())
    return False


def _run_parallel(cfg, ctx, dry_run, retry, interval=60):
    state = {"uploads": 0}

    def dl():
        try:
            run_download(cfg, ctx, dry_run, retry)
        except Cancelled:
            pass
        except Exception as e:  # noqa: BLE001
            ctx.error(f"[Tải] {e}")

    t = threading.Thread(target=dl, daemon=True)
    t.start()
    while t.is_alive() and not ctx.cancelled():
        _guard(ctx, "Đăng", lambda: run_post(cfg, ctx, dry_run, retry, quiet=True, sleep_state=state))
        end = time.time() + interval
        while t.is_alive() and time.time() < end and not ctx.cancelled():
            time.sleep(0.5)
    t.join()
    ctx.check()
    _guard(ctx, "Đăng", lambda: run_post(cfg, ctx, dry_run, retry, sleep_state=state))


def run_all(cfg, ctx, mode, dry_run=False, retry=False):
    """Điểm vào chung cho GUI và CLI. Luôn phát sự kiện 'done' khi kết thúc."""
    try:
        if mode == "download":
            _guard(ctx, "Tải", lambda: run_download(cfg, ctx, dry_run, retry))
        elif mode == "post":
            _guard(ctx, "Đăng", lambda: run_post(cfg, ctx, dry_run, retry))
        elif mode == "download_post":
            _guard(ctx, "Tải", lambda: run_download(cfg, ctx, dry_run, retry))
            ctx.check()
            _guard(ctx, "Đăng", lambda: run_post(cfg, ctx, dry_run, retry))
        elif mode == "parallel":
            _run_parallel(cfg, ctx, dry_run, retry)
        else:
            ctx.error(f"Chế độ không hợp lệ: {mode}")
    except Cancelled:
        ctx.warn("Đã dừng theo yêu cầu.")
    finally:
        ctx.emit({"type": "done", "stats": dict(ctx.stats), "cancelled": ctx.cancelled()})
