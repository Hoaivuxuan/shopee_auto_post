"""Xếp bài Sẵn sàng đăng vào những ngày đã chọn khi bật tự động đăng."""
import json
import os
import threading
from datetime import datetime, timedelta

from .paths import data_dir, reset_workspace, use_workspace

_LOCK = threading.Lock()
_RUNNING = set()
_STOP = False
VN_HOURS = timedelta(hours=7)
DATE_MODES = ("day", "days", "week")
MAX_AHEAD_DAYS = 29


def _tz():
    from datetime import timezone
    return timezone(VN_HOURS)


def _now():
    return datetime.now(_tz())


def _path():
    return os.path.join(data_dir(), "auto_post.json")


def _blank():
    return {
        "enabled": False,
        "per_day": 6,
        "page_id": "",
        "categories": [],
        "dates": [],
        "date_mode": "day",
        "planned_on": "",
        "settled_on": "",
        "settled_dates": [],
        "settled_count": 0,
        "running": False,
        "message": "",
        "slots": [],
    }


def load_settings():
    path = _path()
    data = _blank()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, json.JSONDecodeError):
            stored = {}
        if isinstance(stored, dict):
            data.update({key: stored.get(key, data[key]) for key in data})
    data["per_day"] = _count(data.get("per_day"))
    data["enabled"] = bool(data.get("enabled"))
    data["page_id"] = str(data.get("page_id") or "")
    data["categories"] = _category_names(data.get("categories"), empty_ok=True)
    data["dates"] = _stored_dates(data.get("dates"))
    data["date_mode"] = _date_mode(data.get("date_mode"))
    data["settled_dates"] = _stored_dates(data.get("settled_dates"))
    data["settled_on"] = str(data.get("settled_on") or "")
    try:
        data["settled_count"] = int(data.get("settled_count") or 0)
    except (TypeError, ValueError):
        data["settled_count"] = 0
    data["slots"] = data.get("slots") if isinstance(data.get("slots"), list) else []
    with _LOCK:
        try:
            from .auth import current_username
            key = current_username() or data_dir()
        except (ImportError, ValueError):
            key = data_dir()
        data["running"] = key in _RUNNING
    return data


def save_settings(data):
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stored = {key: data.get(key) for key in _blank()}
    stored["running"] = False
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, ensure_ascii=False, indent=2)


def _count(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Số bài trong ngày phải là số nguyên") from exc
    if number < 1 or number > 48:
        raise ValueError("Số bài trong ngày từ 1 đến 48")
    return number


def _minute(when):
    trimmed = when.replace(second=0, microsecond=0)
    if trimmed < when:
        trimmed += timedelta(minutes=1)
    return trimmed


def _day_text(day):
    return day.strftime("%Y-%m-%d")


def _show_day(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text


def _stored_dates(value):
    if not isinstance(value, list):
        return []
    found = []
    for item in value:
        text = str(item or "").strip()
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            continue
        if text not in found:
            found.append(text)
    found.sort()
    return found


def _date_mode(value):
    text = str(value or "day")
    return text if text in DATE_MODES else "day"


def _active_dates(dates, now=None):
    now = now or _now()
    today = now.date()
    last = today + timedelta(days=MAX_AHEAD_DAYS)
    found = []
    for text in _stored_dates(dates):
        day = datetime.strptime(text, "%Y-%m-%d").date()
        if today <= day <= last:
            found.append(text)
    return found


def normalize_dates(value, now=None):
    """Giữ các ngày từ hôm nay đến 29 ngày sau, giờ Việt Nam."""
    now = now or _now()
    if not isinstance(value, list) or not value:
        raise ValueError("Hãy chọn ít nhất một ngày")
    today = now.date()
    last = today + timedelta(days=MAX_AHEAD_DAYS)
    found = []
    for item in value:
        text = str(item or "").strip()
        try:
            day = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Ngày phải theo dạng YYYY-MM-DD") from exc
        if day < today:
            raise ValueError(f"Ngày {_show_day(text)} đã qua")
        if day > last:
            raise ValueError("Facebook chỉ cho hẹn trước tối đa 29 ngày")
        if text not in found:
            found.append(text)
    found.sort()
    return found


def even_times(count, now=None, day=None):
    """Chia đều suốt ngày, đến 23:59. Hôm nay bắt đầu sau 12 phút vì Facebook yêu cầu hẹn trước."""
    now = now or _now()
    target = day or now.date()
    end = datetime(target.year, target.month, target.day, 23, 59, tzinfo=_tz())
    if target == now.date():
        start = _minute(now + timedelta(minutes=12))
        if start >= end:
            raise ValueError("Hôm nay không còn đủ thời gian. Facebook cần hẹn trước ít nhất 12 phút.")
    else:
        start = datetime(target.year, target.month, target.day, 0, 0, tzinfo=_tz())
    if count <= 1:
        return [start]
    span = (end - start).total_seconds()
    step = span / (count - 1)
    return [_minute(start + timedelta(seconds=round(step * index))) for index in range(count)]


def _category_names(value, empty_ok=False):
    if not isinstance(value, list):
        if empty_ok or value is None:
            return []
        raise ValueError("Danh mục tự động đăng không hợp lệ")
    names = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in names:
            names.append(text)
    return names


def _same_category(wanted, item):
    """Khớp cả tên mục đang hiện và tên cũ còn lưu trong dữ liệu."""
    from .shopee_affiliate import canonical_category
    allowed = set()
    for name in wanted or []:
        _, label = canonical_category(name)
        if label:
            allowed.add(label)
    if not allowed:
        return True
    _, label = canonical_category(item.get("category_name") or "", item.get("category_id") or "")
    return label in allowed


def _ready_ids(raw, page_id, categories=None):
    from .social import already_posted
    found = []
    for item in raw.get("products") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "")
        link = (item.get("short_link") or item.get("long_link") or "").strip()
        if not item_id or not item.get("video_file") or not link:
            continue
        if not _same_category(categories, item):
            continue
        if already_posted(item, "facebook", page_id):
            continue
        found.append(item_id)
    return found


def _fit(when, previous):
    earliest = _now() + timedelta(minutes=12)
    if previous is not None and earliest < previous + timedelta(minutes=1):
        earliest = previous + timedelta(minutes=1)
    if when < earliest:
        when = earliest
    return _minute(when)


def public_status():
    data = load_settings()
    ready = 0
    try:
        from .admin_web import _load_catalog
        if data["page_id"]:
            ready = len(_ready_ids(_load_catalog(), data["page_id"], data.get("categories")))
    except (OSError, ValueError, FileNotFoundError):
        ready = 0
    slots = []
    for slot in data["slots"]:
        if not isinstance(slot, dict):
            continue
        slots.append({
            "item_id": str(slot.get("item_id") or ""),
            "name": str(slot.get("name") or ""),
            "at": str(slot.get("at") or ""),
            "ok": bool(slot.get("ok")),
            "error": str(slot.get("error") or ""),
        })
    return {
        "enabled": data["enabled"],
        "per_day": data["per_day"],
        "page_id": data["page_id"],
        "categories": data["categories"],
        "dates": data["dates"],
        "date_mode": data["date_mode"],
        "planned_on": data["planned_on"],
        "running": data["running"],
        "message": data["message"],
        "ready_count": ready,
        "slots": slots,
    }


def update_settings(enabled, per_day, page_id, categories=None, dates=None, date_mode=None):
    count = _count(per_day)
    page_id = str(page_id or "").strip()
    chosen = None if categories is None else _category_names(categories, empty_ok=True)
    if enabled and not page_id:
        raise ValueError("Hãy chọn Page Facebook trước khi bật tự động đăng")
    if dates is None:
        picked = [_now().strftime("%Y-%m-%d")] if enabled else None
    elif enabled:
        picked = normalize_dates(dates)
    else:
        picked = _stored_dates(dates)
    data = load_settings()
    page_changed = bool(data["page_id"]) and page_id != data["page_id"]
    data["per_day"] = count
    data["page_id"] = page_id
    if chosen is not None:
        data["categories"] = chosen
    if picked is not None:
        data["dates"] = picked
    if date_mode is not None:
        data["date_mode"] = _date_mode(date_mode)
    data["enabled"] = bool(enabled)
    if page_changed:
        data["slots"] = []
        data["planned_on"] = ""
        data["settled_on"] = ""
        data["settled_dates"] = []
        data["settled_count"] = 0
    if not data["enabled"]:
        data["message"] = "Đã tắt tự động đăng. Các bài đã hẹn vẫn giữ trên Facebook."
        save_settings(data)
        return public_status()
    dates_now = _active_dates(data["dates"])
    if not dates_now:
        raise ValueError("Hãy chọn ít nhất một ngày")
    if not _days_short(data["slots"], dates_now, count):
        _remember_plan(data, dates_now, count, _summary(data["slots"], dates_now, count))
        save_settings(data)
        return public_status()
    data["settled_on"] = ""
    data["settled_dates"] = []
    data["settled_count"] = 0
    data["message"] = "Đang xếp bài cho các ngày đã chọn."
    save_settings(data)
    _kick()
    return public_status()


def _ok_count(data):
    return sum(1 for slot in data["slots"] if isinstance(slot, dict) and slot.get("ok"))


def _workspace_key():
    try:
        from .auth import current_username
        return current_username() or data_dir()
    except (ImportError, ValueError):
        return data_dir()


def _kick():
    key = _workspace_key()
    workspace = data_dir()
    try:
        from .auth import current_username, set_current_user
        username = current_username()
    except (ImportError, ValueError):
        username = None
        set_current_user = None
    with _LOCK:
        if key in _RUNNING:
            return
        _RUNNING.add(key)

    def runner():
        ws_token = use_workspace(workspace)
        user_token = set_current_user(username) if set_current_user and username else None
        try:
            _safe_plan(key)
        finally:
            if user_token is not None:
                from .auth import reset_current_user
                reset_current_user(user_token)
            reset_workspace(ws_token)

    threading.Thread(target=runner, name=f"auto-post-{key}", daemon=True).start()


def _safe_plan(key):
    try:
        _plan_today()
    except Exception as exc:
        data = load_settings()
        data["message"] = str(exc)[:180]
        save_settings(data)
    finally:
        with _LOCK:
            _RUNNING.discard(key)


def _ok_on(slots, day):
    found = []
    for slot in slots or []:
        if not isinstance(slot, dict) or not slot.get("ok"):
            continue
        if str(slot.get("at") or "").startswith(day):
            found.append(slot)
    return found


def _days_short(slots, dates, per_day):
    """[(ngày, số bài còn thiếu)] cho những ngày chưa đủ quota."""
    short = []
    for day in dates:
        have = {str(slot.get("item_id") or "") for slot in _ok_on(slots, day)}
        need = per_day - len(have)
        if need > 0:
            short.append((day, need))
    return short


def _remember_plan(data, dates, per_day, message):
    data["planned_on"] = dates[-1] if dates else ""
    data["settled_on"] = data["planned_on"]
    data["settled_dates"] = list(dates)
    data["settled_count"] = per_day
    data["message"] = message


def _latest_slot(kept):
    latest = None
    for slot in kept:
        try:
            when = datetime.strptime(slot.get("at") or "", "%Y-%m-%d %H:%M").replace(tzinfo=_tz())
        except ValueError:
            continue
        if latest is None or when > latest:
            latest = when
    return latest


def _pending_ids(ready_ids, kept, per_day):
    done = {str(slot.get("item_id") or "") for slot in kept}
    need = per_day - len(done)
    if need <= 0:
        return []
    return [item_id for item_id in ready_ids if item_id not in done][:need]


def _plan_dates(data):
    dates = _active_dates(data.get("dates"))
    if dates:
        return dates
    return [_now().strftime("%Y-%m-%d")]


def _plan_today():
    from .admin_web import _POSTING, _POST_LOCK, _facebook_tools, _find_product, _load_catalog, _post_one
    data = load_settings()
    if not data["enabled"]:
        return
    dates = _plan_dates(data)
    quota = data["per_day"]
    if not data.get("dates"):
        data["dates"] = list(dates)
    short = _days_short(data["slots"], dates, quota)
    slots = [slot for slot in data["slots"] if isinstance(slot, dict) and slot.get("ok")]
    if not short:
        _remember_plan(data, dates, quota, _summary(slots, dates, quota))
        data["slots"] = slots
        save_settings(data)
        return
    tools = _facebook_tools(data["page_id"])
    page = tools["page"]
    if not page:
        raise RuntimeError("Chưa chọn Page Facebook đang bật và có token")
    raw = _load_catalog()
    need_new = sum(need for _, need in short)
    chosen = _pending_ids(
        _ready_ids(raw, page["id"], data.get("categories")),
        slots,
        len(slots) + need_new,
    )
    if not chosen:
        _remember_plan(data, dates, quota, "Chưa có sản phẩm Sẵn sàng đăng nào chưa lên trang này.")
        data["slots"] = slots
        save_settings(data)
        return
    previous = _latest_slot(slots)
    stopped = False
    cursor = 0
    for day, need in short:
        if stopped:
            break
        batch = chosen[cursor:cursor + need]
        cursor += need
        if not batch:
            break
        target = datetime.strptime(day, "%Y-%m-%d").date()
        try:
            times = even_times(len(batch), day=target)
        except ValueError as exc:
            for item_id in batch:
                slots.append({"item_id": item_id, "name": "", "at": "", "ok": False, "error": str(exc)})
            continue
        for item_id, when in zip(batch, times):
            if _STOP or not load_settings()["enabled"]:
                stopped = True
                break
            if stopped:
                slots.append({"item_id": item_id, "name": "", "at": "", "ok": False, "error": "Dừng vì Facebook đang giới hạn tốc độ"})
                continue
            when = _fit(when, previous)
            if when.strftime("%Y-%m-%d") != day:
                slots.append({"item_id": item_id, "name": "", "at": "", "ok": False, "error": "Quá 23:59, không còn chỗ trong ngày này"})
                continue
            label = when.strftime("%Y-%m-%d %H:%M")
            with _POST_LOCK:
                claim = f"{_workspace_key()}:facebook:{page['id']}:{item_id}"
                if claim in _POSTING:
                    slots.append({"item_id": item_id, "name": "", "at": label, "ok": False, "error": "Sản phẩm này đang được đăng"})
                    continue
                raw = _load_catalog()
                item = _find_product(raw, item_id)
                _POSTING.add(claim)
            try:
                outcome = _post_one(raw, item, item_id, "schedule", int(when.timestamp()), label, tools)
            finally:
                with _POST_LOCK:
                    _POSTING.discard(claim)
            name = (item or {}).get("name") or ""
            if outcome.get("fatal"):
                stopped = True
            slots.append({
                "item_id": item_id,
                "name": name,
                "at": label if outcome.get("ok") else "",
                "ok": bool(outcome.get("ok")),
                "error": outcome.get("error") or "",
            })
            if outcome.get("ok"):
                previous = when
            data["slots"] = slots
            data["planned_on"] = day
            data["message"] = _summary(slots, dates, quota)
            save_settings(data)
        if _STOP or not load_settings()["enabled"]:
            break
    data = load_settings()
    data["slots"] = slots
    data["dates"] = dates
    _remember_plan(data, dates, quota, _summary(slots, dates, data["per_day"]))
    save_settings(data)


def _summary(slots, dates, per_day):
    if len(dates) <= 1:
        day = dates[0] if dates else ""
        ok = [slot for slot in slots if slot.get("ok") and slot.get("at") and (not day or str(slot.get("at")).startswith(day))]
        ok.sort(key=lambda slot: slot["at"])
        if not ok:
            failed = next((slot.get("error") for slot in slots if slot.get("error")), "")
            return failed or "Chưa xếp được bài nào."
        text = f"Đã xếp {len(ok)}/{per_day} bài từ {ok[0]['at'][11:]} đến {ok[-1]['at'][11:]}{_gap_phrase(ok)}."
        if len(ok) < per_day:
            text += " Không đủ sản phẩm Sẵn sàng đăng cho cả ngày."
        return text
    parts = []
    total_ok = 0
    for day in dates:
        ok = [slot for slot in slots if slot.get("ok") and str(slot.get("at") or "").startswith(day)]
        total_ok += len(ok)
        parts.append(f"{len(ok)}/{per_day} ngày {_show_day(day)}")
    if total_ok == 0:
        failed = next((slot.get("error") for slot in slots if slot.get("error")), "")
        return failed or "Chưa xếp được bài nào."
    text = "Đã xếp " + ", ".join(parts) + "."
    if total_ok < per_day * len(dates):
        text += " Không đủ sản phẩm Sẵn sàng đăng cho hết các ngày đã chọn."
    return text


def _gap_phrase(ok):
    times = []
    for slot in ok:
        try:
            times.append(datetime.strptime(slot["at"], "%Y-%m-%d %H:%M"))
        except ValueError:
            continue
    if len(times) < 2:
        return ""
    gaps = [int((times[index + 1] - times[index]).total_seconds() // 60) for index in range(len(times) - 1)]
    minutes = gaps[-1] if len(gaps) == 1 or len(set(gaps[1:])) == 1 else 0
    if minutes <= 0:
        return ""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f", cách nhau {hours} giờ {mins} phút"
    if hours:
        return f", cách nhau {hours} giờ"
    return f", cách nhau {mins} phút"


def tick():
    data = load_settings()
    if not data["enabled"] or data["running"]:
        return
    active = _active_dates(data["dates"])
    if not active:
        return
    if data.get("settled_count") == data["per_day"] and all(day in data["settled_dates"] for day in active):
        return
    if not _days_short(data["slots"], active, data["per_day"]):
        return
    _kick()


def _tick_all_workspaces():
    """Duyệt mọi workspace để xếp bài / gửi comment theo từng người dùng."""
    try:
        from .auth import list_workspace_usernames, set_current_user, reset_current_user, workspace_dir
    except (ImportError, ValueError):
        tick()
        try:
            from .admin_web import deliver_pending_comments
            deliver_pending_comments()
        except Exception:
            pass
        return

    names = list_workspace_usernames()
    if not names:
        tick()
        try:
            from .admin_web import deliver_pending_comments
            deliver_pending_comments()
        except Exception:
            pass
        return

    for username in names:
        ws_token = use_workspace(workspace_dir(username))
        user_token = set_current_user(username)
        try:
            tick()
            try:
                from .admin_web import deliver_pending_comments
                deliver_pending_comments()
            except Exception:
                pass
        finally:
            reset_current_user(user_token)
            reset_workspace(ws_token)


def start():
    def loop():
        import time
        while not _STOP:
            try:
                _tick_all_workspaces()
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=loop, name="auto-post-day", daemon=True).start()
