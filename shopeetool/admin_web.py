"""Trang quản trị cục bộ: theo dõi sản phẩm từ Shopee tới file ảnh/video và Facebook.

Chạy tay:  .venv/bin/python shopeetool/admin_web.py
Docker:   docker compose up -d --build
Mở:       http://127.0.0.1:8765
"""
import json
import os
import re
import sys
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

VN_TZ = timezone(timedelta(hours=7))


def now_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMIN_PORT", "8765"))
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXT = (".mp4",)
_POST_LOCK = threading.Lock()
_POSTING = set()
_JOBS_LOCK = threading.Lock()
_USER_JOBS = {}
_IDLE_LINK = {
    "status": "idle",
    "message": "",
    "updated": 0,
    "failed": 0,
    "total": 0,
    "done": 0,
}
_IDLE_REFRESH = {
    "status": "idle",
    "message": "",
    "added": 0,
    "total": 0,
    "offers": [],
    "errors": [],
    "offer_id": "",
    "offer_name": "",
    "queued_id": "",
    "queued_name": "",
}
def _job_key():
    try:
        from .auth import current_username
        return current_username() or data_dir()
    except (ImportError, ValueError):
        return data_dir()


def _user_jobs():
    key = _job_key()
    with _JOBS_LOCK:
        slot = _USER_JOBS.get(key)
        if slot is None:
            slot = {
                "board": {"stamp": None, "body": None},
                "refresh": dict(_IDLE_REFRESH),
                "link": dict(_IDLE_LINK),
            }
            _USER_JOBS[key] = slot
        return slot


def _run_in_workspace(name, target, *args):
    """Chạy job nền trong đúng workspace của người dùng đang đăng nhập."""
    try:
        from .auth import current_username, reset_current_user, set_current_user
        from .paths import reset_workspace, use_workspace
    except (ImportError, ValueError):
        threading.Thread(target=target, args=args, name=name, daemon=True).start()
        return
    username = current_username()
    workspace = data_dir()

    def runner():
        ws_token = use_workspace(workspace)
        user_token = set_current_user(username) if username else None
        try:
            target(*args)
        finally:
            if user_token is not None:
                reset_current_user(user_token)
            reset_workspace(ws_token)

    threading.Thread(target=runner, name=name, daemon=True).start()


def _bootstrap():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)


def data_dir():
    try:
        from .paths import data_dir as _data_dir
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.paths import data_dir as _data_dir
    return _data_dir()


def web_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _fb_groups():
    try:
        from . import fb_group as mod
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool import fb_group as mod
    return mod


def _fb_login():
    try:
        from . import fb_login as mod
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool import fb_login as mod
    return mod


def _stored_media(item, field):
    """Đường dẫn ảnh/video đã ghi lúc tải file. Không dò từng file trên ổ đĩa."""
    rel = str(item.get(field) or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return ""
    return rel


def load_board():
    """Đọc products_affiliate.json và dựng danh sách cho trang quản trị."""
    path = os.path.join(data_dir(), "products_affiliate.json")
    if not os.path.isfile(path):
        return {
            "updated_at": "",
            "stats": _stats([]),
            "products": [],
            "error": "Chưa có data/products_affiliate.json",
        }
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    try:
        from .shopee_affiliate import canonical_category
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.shopee_affiliate import canonical_category
    products = []
    for item in raw.get("products") or []:
        if not isinstance(item, dict):
            continue
        shop = str(item.get("shop_id") or "0")
        iid = str(item.get("item_id") or "0")
        image = _stored_media(item, "image_file")
        video = _stored_media(item, "video_file")
        has_source = bool(item.get("video_url"))
        if video:
            video_state = "ready"
        elif has_source:
            video_state = "missing"
        else:
            video_state = "none"
        short = item.get("short_link") or ""
        permalink = item.get("facebook_permalink") or ""
        if permalink.startswith("/"):
            permalink = "https://www.facebook.com" + permalink
        category_id, category_name = canonical_category(
            item.get("category_name") or "",
            item.get("category_id") or "",
        )
        products.append({
            "item_id": iid,
            "shop_id": shop,
            "name": item.get("name") or "",
            "shop_name": item.get("shop_name") or "",
            "category_id": category_id,
            "category_name": category_name,
            "price": item.get("price") or 0,
            "price_formatted": item.get("price_formatted") or "",
            "commission_rate": item.get("commission_rate") or "",
            "short_link": short,
            "has_long_link": bool(item.get("long_link")),
            "image_file": image,
            "video_file": video,
            "video_state": video_state,
            "ready": bool(video and (short or item.get("long_link"))),
            "facebook_page_name": item.get("facebook_page_name") or "",
            "facebook_video_id": item.get("facebook_video_id") or "",
            "facebook_status": item.get("facebook_status") or "",
            "facebook_permalink": permalink,
            "facebook_checked_at": item.get("facebook_checked_at") or "",
            "facebook_scheduled_at": item.get("facebook_scheduled_at") or "",
            "facebook_error": item.get("facebook_error") or "",
            "publications": _publications(item),
        })
    return {
        "updated_at": raw.get("updated_at") or "",
        "facebook_checked_at": _latest_check(products),
        "stats": _stats(products),
        "categories": _category_options(products),
        "products": products,
    }


def _category_options(products):
    """Mục affiliate cố định, rồi các mục lạ còn trong dữ liệu."""
    try:
        from .shopee_affiliate import OFFERS
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.shopee_affiliate import OFFERS
    names = []
    for offer in OFFERS:
        label = offer["name"]
        if label not in names:
            names.append(label)
    for item in products:
        label = item.get("category_name") or ""
        if label and label not in names:
            names.append(label)
    return names


def board_response():
    """JSON danh sách đã dựng. Dùng lại khi file sản phẩm chưa đổi."""
    path = os.path.join(data_dir(), "products_affiliate.json")
    jobs = _user_jobs()
    cache = jobs["board"]
    if not os.path.isfile(path):
        return json.dumps(load_board(), ensure_ascii=False).encode("utf-8")
    st = os.stat(path)
    stamp = (st.st_mtime_ns, st.st_size)
    with _JOBS_LOCK:
        if cache["stamp"] == stamp and cache["body"] is not None:
            return cache["body"]
    try:
        body = json.dumps(load_board(), ensure_ascii=False).encode("utf-8")
    except (OSError, json.JSONDecodeError, ValueError):
        with _JOBS_LOCK:
            if cache["body"] is not None:
                return cache["body"]
        raise
    with _JOBS_LOCK:
        cache["stamp"] = stamp
        cache["body"] = body
    return body


def catalog_refresh_status():
    """Trạng thái nút Cập nhật danh sách."""
    refresh = _user_jobs()["refresh"]
    with _JOBS_LOCK:
        return {
            "status": refresh["status"],
            "message": refresh["message"],
            "added": refresh["added"],
            "total": refresh["total"],
            "offers": list(refresh["offers"]),
            "errors": list(refresh["errors"]),
            "offer_name": refresh.get("offer_name") or "",
            "queued_name": refresh.get("queued_name") or "",
        }


def _refresh_set(**kwargs):
    refresh = _user_jobs()["refresh"]
    with _JOBS_LOCK:
        refresh.update(kwargs)


def _catalog_target(offer_key: str):
    """Mọi mục dùng khóa *, vì mã all là tab Tất cả trên Shopee."""
    key = str(offer_key or "").strip()
    if not key:
        raise ValueError("Hãy chọn một mục trước khi cập nhật danh sách.")
    if key in {"*", "Mọi mục"}:
        return {"id": "*", "name": "Mọi mục"}
    try:
        from .shopee_affiliate import offer_by_key
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.shopee_affiliate import offer_by_key
    return offer_by_key(key)


def _catalog_label(offer):
    if offer["id"] == "*":
        return "mọi mục"
    return f"mục {offer['name']}"


def start_catalog_refresh(offer_key: str = ""):
    """Chạy lấy sản phẩm mới ở nền. Mọi mục đi lần lượt từng danh mục, không ghi trùng."""
    offer = _catalog_target(offer_key)
    label = _catalog_label(offer)
    refresh = _user_jobs()["refresh"]
    with _JOBS_LOCK:
        if refresh["status"] == "running":
            already = True
            if refresh.get("offer_id") != offer["id"]:
                refresh["queued_id"] = offer["id"]
                refresh["queued_name"] = offer["name"]
        else:
            already = False
            refresh.update({
                "status": "running",
                "message": f"Đang chuẩn bị cập nhật {label}...",
                "added": 0,
                "total": 0,
                "offers": [],
                "errors": [],
                "offer_id": offer["id"],
                "offer_name": offer["name"],
                "queued_id": "",
                "queued_name": "",
            })
    if not already:
        _run_in_workspace("catalog-refresh", _run_catalog_refresh, offer["id"])
    status = catalog_refresh_status()
    if already and status.get("queued_name"):
        current = status.get("offer_name") or "mục đang chạy"
        status["message"] = f"Đang cập nhật {current}. Xong sẽ cập nhật {status['queued_name']}."
    return status


def _finish_refresh_message(result):
    added = int(result.get("added") or 0)
    images = int(result.get("images") or 0)
    videos = int(result.get("videos") or 0)
    media_failed = int(result.get("media_failed") or 0)
    errors = result.get("errors") or []
    names = [item.get("name") or "" for item in (result.get("offers") or [])]
    if len(names) > 1:
        label = "mọi mục"
    elif names and names[0]:
        label = f"mục {names[0]}"
    else:
        label = "mục đang chọn"
    media = f"Đã tải {images} ảnh và {videos} video."
    if media_failed:
        media += f" Không tải được {media_failed} sản phẩm."
    if errors and added == 0 and images == 0 and videos == 0:
        message = errors[0].get("error") or "Không cập nhật được danh sách"
        status = "error"
    elif errors:
        failed = ", ".join(item.get("name") or "" for item in errors)
        message = (
            f"Đã thêm {added} sản phẩm mới vào {label}. {media} "
            f"Chưa lấy hết danh sách: {failed}."
        )
        status = "done"
    else:
        message = (
            f"Đã thêm {added} sản phẩm mới vào {label}. {media} "
            "Không ghi sản phẩm trùng."
        )
        status = "done"
    return status, message, added, errors


def _run_catalog_refresh(offer_key: str):
    try:
        from .shopee_affiliate import update_product_catalog
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.shopee_affiliate import update_product_catalog
    current = offer_key
    while current:
        try:
            result = update_product_catalog(
                offer_key=current,
                on_progress=lambda message: _refresh_set(message=message),
            )
            status, message, added, errors = _finish_refresh_message(result)
            total = int(result.get("total") or 0)
            offers = result.get("offers") or []
        except Exception as exc:
            status, message, added, errors = "error", str(exc)[:300], 0, []
            total, offers = 0, []
        refresh = _user_jobs()["refresh"]
        with _JOBS_LOCK:
            queued_id = refresh.get("queued_id") or ""
            queued_name = refresh.get("queued_name") or ""
            refresh["queued_id"] = ""
            refresh["queued_name"] = ""
            if queued_id and queued_id != current:
                next_label = "mọi mục" if queued_id == "*" else f"mục {queued_name}"
                refresh.update({
                    "status": "running",
                    "message": f"Đang chuẩn bị cập nhật {next_label}...",
                    "added": 0,
                    "total": 0,
                    "offers": [],
                    "errors": [],
                    "offer_id": queued_id,
                    "offer_name": queued_name,
                })
                current = queued_id
            else:
                refresh.update({
                    "status": status,
                    "message": message,
                    "added": added,
                    "total": total,
                    "offers": offers,
                    "errors": errors,
                })
                current = ""


def _stats(products):
    return {
        "total": len(products),
        "short_link": sum(1 for p in products if p.get("short_link")),
        "image": sum(1 for p in products if p.get("image_file")),
        "video_ready": sum(1 for p in products if p.get("video_state") == "ready"),
        "video_missing": sum(1 for p in products if p.get("video_state") == "missing"),
        "video_none": sum(1 for p in products if p.get("video_state") == "none"),
        "ready": sum(1 for p in products if p.get("ready")),
        "facebook": sum(1 for p in products if p.get("facebook_status") == "published"),
    }


def _publications(item):
    try:
        from .social import publications_of
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.social import publications_of
    return publications_of(item)


def _social():
    try:
        from . import social
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool import social
    return social


def _latest_check(products):
    stamps = [p.get("facebook_checked_at") or "" for p in products]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else ""


def _catalog_path():
    return os.path.join(data_dir(), "products_affiliate.json")


def _load_catalog():
    path = _catalog_path()
    if not os.path.isfile(path):
        raise FileNotFoundError("Chưa có data/products_affiliate.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or not isinstance(raw.get("products"), list):
        raise ValueError("File sản phẩm không đúng định dạng")
    return raw


def _save_catalog(raw):
    raw["total_with_short_link"] = sum(1 for p in raw["products"] if isinstance(p, dict) and p.get("short_link"))
    path = _catalog_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _find_product(raw, item_id):
    for item in raw["products"]:
        if isinstance(item, dict) and str(item.get("item_id") or "") == str(item_id):
            return item
    return None


def clean_short_link(value):
    """Link rút gọn người dùng dán tay. Chuỗi rỗng nghĩa là xóa link."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) > 500 or any(ch.isspace() for ch in value):
        raise ValueError("Link không hợp lệ")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Link cần bắt đầu bằng https://")
    return value


def set_short_link(item_id, value):
    raw = _load_catalog()
    item = _find_product(raw, item_id)
    if item is None:
        raise LookupError("Không thấy sản phẩm")
    item["short_link"] = clean_short_link(value)
    raw["updated_at"] = now_str()
    _save_catalog(raw)
    return item["short_link"]


def _short_link_batch():
    try:
        from . import short_link_batch as mod
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool import short_link_batch as mod
    return mod


def export_missing_short_links():
    batch = _short_link_batch()
    raw = _load_catalog()
    links = batch.missing_links(raw.get("products") or [])
    if not links:
        raise LookupError("Không có sản phẩm nào thiếu link rút gọn")
    body = batch.build_workbook(links, batch.default_template())
    return body, batch.EXPORT_NAME, batch.XLSX_TYPE, len(links)


def import_short_links_csv(payload):
    batch = _short_link_batch()
    raw = _load_catalog()
    result = batch.apply_csv(raw.get("products") or [], payload)
    if result["updated"]:
        raw["updated_at"] = now_str()
        _save_catalog(raw)
    return result


def short_link_job_status():
    link = _user_jobs()["link"]
    with _JOBS_LOCK:
        return dict(link)


def _set_short_link_job(**kwargs):
    link = _user_jobs()["link"]
    with _JOBS_LOCK:
        link.update(kwargs)


def start_short_link_job():
    """Tạo short_link cho sản phẩm còn thiếu, qua trang Custom Link."""
    refresh = _user_jobs()["refresh"]
    link = _user_jobs()["link"]
    with _JOBS_LOCK:
        if refresh["status"] == "running":
            raise RuntimeError("Danh sách đang được cập nhật. Hãy đợi xong rồi tạo link.")
        if link["status"] == "running":
            return dict(link)
        link.update({
            "status": "running",
            "message": "Đang mở trang Custom Link",
            "updated": 0,
            "failed": 0,
            "total": 0,
            "done": 0,
        })
    _run_in_workspace("short-link", _short_link_worker)
    return short_link_job_status()


def _short_link_worker():
    updated = 0
    failed = 0
    try:
        batch = _short_link_batch()
        links = batch.missing_links(_load_catalog().get("products") or [])
        if not links:
            _set_short_link_job(status="done", message="Mọi sản phẩm đã có link rút gọn", total=0)
            return
        _set_short_link_job(total=len(links), message=f"Đang chuyển 0/{len(links)} link")

        def on_batch(done, total, rows):
            nonlocal updated, failed
            raw = _load_catalog()
            result = batch.apply_custom_rows(raw.get("products") or [], rows)
            if result["updated"]:
                raw["updated_at"] = now_str()
                _save_catalog(raw)
            updated += result["updated"]
            failed += result["failed"]
            _set_short_link_job(
                done=done,
                updated=updated,
                failed=failed,
                message=f"Đang chuyển {done}/{total} link",
            )

        batch.fetch_custom_link_rows(links, on_batch=on_batch)
        parts = [f"Đã gán {updated} link rút gọn"]
        if failed:
            parts.append(f"{failed} link lỗi")
        _set_short_link_job(status="done", message=". ".join(parts), updated=updated, failed=failed)
    except Exception as exc:
        text = str(exc).strip()[:240] or "Không tạo được link rút gọn"
        if updated:
            text = f"Đã gán {updated} link rồi dừng. {text}"
        _set_short_link_job(status="error", message=text, updated=updated, failed=failed)


def _page_tokens():
    try:
        from . import config as cfgmod
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool import config as cfgmod
    cfg = cfgmod.load()
    version = (cfg.get("facebook") or {}).get("api_version") or "v25.0"
    tokens = {}
    for page in cfg.get("pages") or []:
        if page.get("id") and page.get("token") and page.get("enabled", True):
            tokens[str(page["id"])] = page["token"]
    return version, tokens


def _graph_video(version, video_id, token):
    query = urllib.parse.urlencode({
        "fields": "id,permalink_url,published,created_time,status",
        "access_token": token,
    })
    url = f"https://graph.facebook.com/{version}/{video_id}?{query}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": {"message": f"HTTP {e.code}", "code": e.code}}


def _facebook_state(payload):
    if not isinstance(payload, dict):
        return "error", "", "Phản hồi Facebook không hợp lệ"
    if payload.get("error"):
        err = payload["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return "error", "", (msg or "Facebook từ chối kiểm tra")[:180]
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    video_status = status.get("video_status") or ""
    publishing = status.get("publishing_phase") if isinstance(status.get("publishing_phase"), dict) else {}
    publish_status = publishing.get("publish_status") or ""
    if publish_status == "scheduled":
        state = "scheduled"
    elif payload.get("published") is True or publish_status == "published":
        state = "published"
    elif video_status in ("processing", "uploading") or publish_status == "draft":
        state = "processing"
    elif video_status == "ready":
        state = "published"
    elif video_status == "error" or publish_status == "error":
        state = "error"
    else:
        state = "processing" if video_status else "error"
    permalink = payload.get("permalink_url") or ""
    if permalink.startswith("/"):
        permalink = "https://www.facebook.com" + permalink
    detail = ""
    if state == "error":
        detail = video_status or publish_status or "Không rõ trạng thái"
    return state, permalink, detail


def refresh_facebook(item_id=None):
    """Hỏi Graph API trạng thái các video đã đăng và ghi lại vào JSON."""
    raw = _load_catalog()
    version, tokens = _page_tokens()
    if not tokens:
        raise RuntimeError("Chưa có token Page trong cấu hình Facebook")
    fallback = next(iter(tokens.values()))
    now = now_str()
    checked = []
    for item in raw["products"]:
        if not isinstance(item, dict):
            continue
        if item_id and str(item.get("item_id") or "") != str(item_id):
            continue
        video_id = str(item.get("facebook_video_id") or "").strip()
        if not video_id:
            continue
        token = tokens.get(str(item.get("facebook_page_id") or "")) or fallback
        state, permalink, detail = _facebook_state(_graph_video(version, video_id, token))
        item["facebook_status"] = state
        item["facebook_permalink"] = permalink
        item["facebook_error"] = detail
        item["facebook_checked_at"] = now
        _social().remember_publication(item, {
            "platform": "facebook",
            "page_id": item.get("facebook_page_id") or "",
            "page_name": item.get("facebook_page_name") or "",
            "video_id": video_id,
            "status": state,
            "permalink": permalink,
            "scheduled_at": item.get("facebook_scheduled_at") or "",
            "error": detail,
            "checked_at": now,
            "comment_id": item.get("facebook_comment_id") or "",
        })
        checked.append({
            "item_id": item.get("item_id"),
            "facebook_status": state,
            "facebook_permalink": permalink,
            "facebook_error": detail,
        })
    if not checked:
        raise LookupError("Chưa có sản phẩm nào đã đăng để kiểm tra")
    _save_catalog(raw)
    return {"checked_at": now, "checked": checked}


def _facebook_tools(page_id=""):
    try:
        from .facebook import FATAL_CODES, FBError, hint_for, post_comment, upload_video
    except (ImportError, ValueError):
        _bootstrap()
        from shopeetool.facebook import FATAL_CODES, FBError, hint_for, post_comment, upload_video
    social = _social()
    cfg = social.load_cfg()
    facebook = cfg.get("facebook") or {}
    if page_id:
        page = social.find_page(cfg, "facebook", page_id)
    else:
        page = next(
            (p for p in cfg["networks"]["facebook"]["pages"] if p.get("enabled", True) and p.get("token")),
            None,
        )
    if page and (not page.get("enabled", True) or not page.get("token")):
        page = None
    return {
        "version": facebook.get("api_version") or "v25.0",
        "prefix": facebook.get("link_prefix") or "Mua tại: ",
        "page": page,
        "upload_video": upload_video,
        "post_comment": post_comment,
        "FBError": FBError,
        "FATAL_CODES": FATAL_CODES,
        "hint_for": hint_for,
    }


def _parse_schedule(value):
    """Giờ hẹn theo giờ Việt Nam. Facebook nhận unix time, trong khoảng 12 phút đến 29 ngày."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("Chọn giờ đăng")
    try:
        when = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValueError("Giờ đăng không đúng") from e
    if when.tzinfo is None:
        when = when.replace(tzinfo=VN_TZ)
    else:
        when = when.astimezone(VN_TZ)
    lead = (when - datetime.now(VN_TZ)).total_seconds()
    if lead < 12 * 60:
        raise ValueError("Giờ hẹn phải cách hiện tại ít nhất 12 phút")
    if lead > 29 * 24 * 3600:
        raise ValueError("Giờ hẹn phải trong vòng 29 ngày")
    return int(when.timestamp()), when.strftime("%Y-%m-%d %H:%M")


_TAG_STOP = {
    "và", "của", "cho", "với", "các", "những", "một", "được", "trong", "trên", "dưới",
    "từ", "để", "khi", "này", "đó", "có", "là", "hoặc", "theo", "bằng", "đến", "tới",
    "về", "ra", "vào", "không", "đang", "sẽ", "đã", "rất", "hơn", "nhất", "kèm",
    "loại", "mẫu", "mới", "chính", "hãng", "bán", "giá", "sỉ", "lẻ",
}


def _unaccent(text):
    """Bỏ dấu tiếng Việt. Chữ đ/Đ không phải dấu kết hợp nên đổi riêng thành d/D."""
    text = unicodedata.normalize("NFC", text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _word_token(word):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFC", word or ""), flags=re.UNICODE)


def _hashtag(phrase):
    parts = []
    for word in re.split(r"\s+", unicodedata.normalize("NFC", phrase or "").strip()):
        token = _unaccent(_word_token(word))
        if token:
            parts.append(token[:1].upper() + token[1:])
    return "".join(parts)


def product_tags(name, category, limit=8):
    """Tag tìm kiếm từ tên sản phẩm và mục, bỏ từ nối, viết không dấu, không trùng."""
    tags = []
    seen = set()

    def add(phrase):
        if len(tags) >= limit:
            return
        kept = []
        for word in re.split(r"\s+", unicodedata.normalize("NFC", phrase or "").strip()):
            token = _word_token(word)
            if len(token) < 2 or token.casefold() in _TAG_STOP:
                continue
            kept.append(token)
        token = _hashtag(" ".join(kept))
        key = token.casefold()
        if len(token) < 2 or key in seen:
            return
        seen.add(key)
        tags.append("#" + token)

    cleaned = re.sub(r"\[[^\]]*\]", " ", name or "")
    words = []
    for word in re.split(r"\s+", cleaned):
        token = _word_token(word)
        if len(token) < 2 or token.casefold() in _TAG_STOP:
            continue
        words.append(token)
    if words:
        add(" ".join(words[:4]))
    for part in re.split(r"[&,/|]+", category or ""):
        add(part)
    for word in words:
        add(word)
    return tags


def _caption(name, _link="", _prefix="", tags=None):
    """Nội dung bài và tag. Link Shopee chỉ gửi trong bình luận."""
    from .qwen_skills import hide_prices
    parts = []
    text = hide_prices(name)
    if text:
        parts.append(text)
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)


_ICON = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _caption_draft_ok(text):
    prose = (text or "").strip()
    if len(prose) < 40 or len(prose) > 420:
        return False
    if not _ICON.search(prose):
        return False
    if not re.search(r"[.!?…]", prose):
        return False
    if prose.count(".") + prose.count("!") + prose.count("?") + prose.count("…") > 4:
        return False
    if re.search(r"https?://|www\.|#\w", prose, re.I):
        return False
    from .qwen_skills import mentions_price
    if mentions_price(prose):
        return False
    if not re.search(r"[à-ỹÀ-Ỹ]", prose):
        return False
    folded = prose.casefold()
    banned = (
        "okay", "i need", "the user", "as an ai", "hoa hồng", "affiliate",
        "quảng cáo", "mua tại", "câu 1", "yêu cầu", "viết tiếp",
    )
    return not any(word in folded for word in banned)


_CAPTION_FALLBACK = (
    "Viết tiếp caption tiếng Việt cho video bán hàng, giọng mềm và gần. "
    "Đúng 2 câu ngắn. Nhắc tên ngắn một lần, đừng chép nguyên tiêu đề. "
    "Thêm 2 hoặc 3 icon mềm như 🤍 🌿 ☁️ 🌸 🫧. "
    "Chỉ nói điều có trong tiêu đề. Không bịa mẫu, size, chất liệu hay công dụng. "
    "Không hashtag, không URL, không nhắc giá hay số tiền, không kể lại yêu cầu."
)


def _draft_caption(name, category, _price=""):
    """qwen3:4b viết đoạn mở. Tag gắn sau; link Shopee chỉ để trong bình luận."""
    from .fb_group import _ollama_base, _spoken_product, _strip_model_text
    from .qwen_skills import chat_prompt, hide_prices, skill_text
    title = hide_prices(re.sub(r"\s+", " ", name or "").strip())[:180]
    short = _spoken_product(title)
    facts = f"Tên ngắn: {short}. Tiêu đề gốc: {title}."
    label = re.sub(r"\s+", " ", category or "").strip()[:80]
    if label:
        facts += f" Mục: {label}."
    starter = "✨ "
    prompt = chat_prompt(skill_text("caption.md", _CAPTION_FALLBACK), facts, starter)
    payload = {
        "model": os.environ.get("OLLAMA_CAPTION_MODEL", "qwen3:4b"),
        "stream": False,
        "raw": True,
        "prompt": prompt,
        "options": {
            "temperature": 0.85,
            "num_predict": 160,
            "stop": ["<|im_end|>", "<|im_start|>", "</think>"],
        },
    }
    req = urllib.request.Request(
        _ollama_base() + "/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    text = _strip_model_text(starter + str(data.get("response") or ""))
    text = re.sub(r"#\S+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", text).strip()


def post_message(item, link="", prefix=""):
    """Caption mềm do qwen viết, không kèm link. Hỏng thì dùng tên sản phẩm."""
    name = item.get("name") or ""
    tags = product_tags(name, item.get("category_name") or "")
    plain = _caption(name, link, prefix, tags)
    for _ in range(2):
        try:
            draft = _draft_caption(name, item.get("category_name") or "", item.get("price_formatted") or "")
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
            break
        if _caption_draft_ok(draft):
            return _caption(draft, link, prefix, tags)
    return plain


def _buyer_link(item):
    return (item.get("short_link") or item.get("long_link") or "").strip()


def _image_path(item):
    rel = str(item.get("image_file") or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return ""
    path = os.path.join(data_dir(), rel)
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        return ""
    return path


def _comment_not_ready(error):
    text = str(error or "").lower()
    return any(piece in text for piece in ("scheduled", "not published", "isn't available", "unpublished"))


def _comment_due(item, now):
    when = str(item.get("facebook_scheduled_at") or "").strip()
    if not when:
        return True
    try:
        scheduled = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=VN_TZ)
    except ValueError:
        return True
    return now >= scheduled


def deliver_pending_comments():
    """Gửi bình luận ảnh kèm link cho bài hẹn giờ sau khi đến giờ đăng."""
    try:
        raw = _load_catalog()
    except (OSError, ValueError, FileNotFoundError):
        return 0
    now = datetime.now(VN_TZ)
    changed = False
    sent = 0
    for item in raw.get("products") or []:
        if not isinstance(item, dict) or not item.get("facebook_comment_pending"):
            continue
        if item.get("facebook_comment_id") or not _comment_due(item, now):
            if item.get("facebook_comment_id"):
                item["facebook_comment_pending"] = False
                changed = True
            continue
        video_id = str(item.get("facebook_video_id") or "").strip()
        image = _image_path(item)
        link = _buyer_link(item)
        page_id = str(item.get("facebook_page_id") or "").strip()
        if not video_id or not image or not link or not page_id:
            continue
        tools = _facebook_tools(page_id)
        page = tools["page"]
        if not page:
            continue
        prefix = tools["prefix"]
        try:
            comment_id = tools["post_comment"](page, video_id, f"{prefix}{link}", tools["version"], image)
        except tools["FBError"] as exc:
            if _comment_not_ready(exc):
                continue
            tries = int(item.get("facebook_comment_tries") or 0) + 1
            item["facebook_comment_tries"] = tries
            if tries >= 5:
                item["facebook_comment_pending"] = False
                item["facebook_error"] = f"Không gửi được ảnh bình luận: {exc}"[:180]
            changed = True
            continue
        item["facebook_comment_pending"] = False
        item["facebook_comment_tries"] = 0
        _social().remember_publication(item, {
            "platform": "facebook",
            "page_id": page_id,
            "page_name": page.get("name") or item.get("facebook_page_name") or "",
            "video_id": video_id,
            "status": item.get("facebook_status") or "published",
            "permalink": item.get("facebook_permalink") or "",
            "scheduled_at": item.get("facebook_scheduled_at") or "",
            "error": "",
            "comment_id": comment_id or "",
        })
        changed = True
        sent += 1
    if changed:
        raw["updated_at"] = now_str()
        _save_catalog(raw)
    return sent


def post_products(item_ids, mode, schedule_at=None, platform="facebook", page_id=""):
    """Đăng các sản phẩm đã chọn lên Page. Caption có tag; ảnh và link nằm trong bình luận."""
    if mode not in ("now", "schedule"):
        raise ValueError("Chọn đăng ngay hoặc hẹn giờ")
    ids = []
    for raw_id in item_ids or []:
        item_id = str(raw_id or "").strip()
        if item_id and item_id not in ids:
            ids.append(item_id)
    if not ids:
        raise ValueError("Chưa chọn sản phẩm")
    if len(ids) > 20:
        raise ValueError("Mỗi lần đăng tối đa 20 sản phẩm")
    schedule_ts, schedule_label = (None, "")
    if mode == "schedule":
        schedule_ts, schedule_label = _parse_schedule(schedule_at)

    social = _social()
    info = social.platform_info(str(platform or "").strip())
    if not info:
        raise ValueError("Mạng xã hội không hỗ trợ")
    if not info["posting"]:
        raise ValueError(f"{info['label']} chưa có API đăng bài. Trang vẫn được lưu để quản lý.")
    tools = _facebook_tools(str(page_id or "").strip())
    page = tools["page"]
    if not page:
        raise RuntimeError("Chưa chọn Page Facebook đang bật và có token")
    target = (info["id"], str(page["id"]))
    results = []
    stopped = False
    for item_id in ids:
        if stopped:
            results.append({"item_id": item_id, "ok": False, "error": "Dừng vì Facebook đang giới hạn tốc độ"})
            continue
        with _POST_LOCK:
            claim = f"{_job_key()}:{target[0]}:{target[1]}:{item_id}"
            if claim in _POSTING:
                results.append({
                    "item_id": item_id,
                    "ok": False,
                    "duplicate": True,
                    "error": "Sản phẩm này đang được đăng lên trang đã chọn, không gửi thêm",
                })
                continue
            raw = _load_catalog()
            item = _find_product(raw, item_id)
            if item is not None and social.already_posted(item, target[0], target[1]):
                results.append({
                    "item_id": item_id,
                    "ok": False,
                    "duplicate": True,
                    "error": f"Đã đăng lên {page.get('name') or 'trang này'}, không đăng lại",
                })
                continue
            _POSTING.add(claim)
        try:
            outcome = _post_one(raw, item, item_id, mode, schedule_ts, schedule_label, tools)
            if outcome.get("fatal"):
                stopped = True
            outcome.pop("changed", None)
            outcome.pop("fatal", None)
            results.append(outcome)
        finally:
            with _POST_LOCK:
                _POSTING.discard(claim)
    return {
        "platform": target[0],
        "page_id": target[1],
        "page_name": page.get("name") or "",
        "mode": mode,
        "results": results,
    }


def _post_one(raw, item, item_id, mode, schedule_ts, schedule_label, tools):
    if item is None:
        return {"item_id": item_id, "ok": False, "error": "Không thấy sản phẩm"}
    page = tools["page"]
    if _social().already_posted(item, "facebook", page["id"]):
        return {
            "item_id": item_id,
            "ok": False,
            "duplicate": True,
            "error": f"Đã đăng lên {page.get('name') or 'trang này'}, không đăng lại",
        }
    link = _buyer_link(item)
    if not link:
        return {"item_id": item_id, "ok": False, "error": "Chưa có link hoa hồng"}
    rel = item.get("video_file") or ""
    video_path = os.path.join(data_dir(), rel) if rel else ""
    if not video_path or not os.path.isfile(video_path) or os.path.getsize(video_path) <= 0:
        return {"item_id": item_id, "ok": False, "error": "Chưa có file video"}

    message = post_message(item, link, tools["prefix"])
    try:
        video_id = tools["upload_video"](
            page, video_path, message, tools["version"],
            schedule_ts=schedule_ts if mode == "schedule" else None,
        )
    except tools["FBError"] as e:
        hint = tools["hint_for"](e)
        text = f"Facebook báo lỗi {e.code}: {e}"
        if hint:
            text = f"{text} {hint}"
        return {
            "item_id": item_id,
            "ok": False,
            "error": text[:300],
            "fatal": e.code in tools["FATAL_CODES"],
        }
    except OSError as e:
        return {"item_id": item_id, "ok": False, "error": f"Không đọc được video: {e}"}

    warning = ""
    comment_id = ""
    image = _image_path(item)
    if image:
        if mode == "schedule":
            item["facebook_comment_pending"] = True
        else:
            try:
                comment_id = tools["post_comment"](
                    page, video_id, f"{tools['prefix']}{link}", tools["version"], image,
                ) or ""
                item["facebook_comment_pending"] = False
            except tools["FBError"] as e:
                item["facebook_comment_pending"] = True
                warning = f"Đã đăng video, chưa gửi được ảnh vào bình luận: {e}"[:300]
    else:
        item["facebook_comment_pending"] = False

    status = "scheduled" if mode == "schedule" else "published"
    _social().remember_publication(item, {
        "platform": "facebook",
        "page_id": str(page["id"]),
        "page_name": page.get("name") or "",
        "video_id": video_id,
        "status": status,
        "scheduled_at": schedule_label if mode == "schedule" else "",
        "error": "",
        "permalink": item.get("facebook_permalink") or "",
        "comment_id": comment_id,
    })
    _save_catalog(raw)
    return {
        "item_id": item_id,
        "ok": True,
        "changed": True,
        "facebook_video_id": video_id,
        "facebook_status": item["facebook_status"],
        "warning": warning,
    }


def _safe_media(rel):
    """Chỉ phục vụ ảnh/video trong data/affiliate và data/fb_group_media."""
    rel = unquote(rel).lstrip("/")
    parts = [part for part in rel.split("/") if part]
    if not parts or parts[0] not in {"affiliate", "fb_group_media"} or ".." in parts:
        return None
    root = os.path.realpath(os.path.join(data_dir(), parts[0]))
    path = os.path.realpath(os.path.join(data_dir(), *parts))
    if path != root and not path.startswith(root + os.sep):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXT + VIDEO_EXT or not os.path.isfile(path):
        return None
    return path


def _web_file(url_path):
    """Chỉ phục vụ file tĩnh do bản build React tạo trong shopeetool/web."""
    rel = unquote(url_path).lstrip("/")
    if not rel or rel in ("index.html",) or ".." in rel.split("/"):
        return None
    root = os.path.realpath(web_dir())
    path = os.path.realpath(os.path.join(root, rel))
    if path != root and not path.startswith(root + os.sep):
        return None
    if not os.path.isfile(path):
        return None
    return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type, extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, payload, extra=None):
        self._send(code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8", extra)

    def _auth_mod(self):
        try:
            from . import auth
        except (ImportError, ValueError):
            _bootstrap()
            from shopeetool import auth
        return auth

    def _current_session(self):
        auth = self._auth_mod()
        token = auth.cookie_token(self.headers)
        user = auth.session_user(token) if token else None
        return auth, token, user

    def _require_user(self):
        auth, token, user = self._current_session()
        if not user:
            self._json(401, {"ok": False, "error": "Chưa đăng nhập", "auth": False})
            return None, None, None
        return auth, token, user

    def _enter_user(self, username):
        auth = self._auth_mod()
        from .paths import use_workspace
        auth.ensure_workspace(username)
        user_token = auth.set_current_user(username)
        ws_token = use_workspace(auth.workspace_dir(username))
        return user_token, ws_token

    def _leave_user(self, user_token, ws_token):
        auth = self._auth_mod()
        from .paths import reset_workspace
        if user_token is not None:
            auth.reset_current_user(user_token)
        if ws_token is not None:
            reset_workspace(ws_token)

    def _serve_static(self, path):
        if path in ("/", "/index.html"):
            page = os.path.join(web_dir(), "index.html")
            with open(page, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return True
        web_file = _web_file(path)
        if not web_file:
            return False
        ext = os.path.splitext(web_file)[1].lower()
        ctype = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
            ".woff2": "font/woff2",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(web_file, "rb") as f:
            self._send(200, f.read(), ctype)
        return True

    def _handle_auth_get(self, path):
        auth, _token, user = self._current_session()
        if path == "/api/auth/me":
            if not user:
                self._json(200, {"ok": True, "authenticated": False})
                return True
            self._json(200, {
                "ok": True,
                "authenticated": True,
                "username": user["username"],
                "role": user["role"],
            })
            return True
        if path == "/api/auth/users":
            if not user:
                self._json(401, {"ok": False, "error": "Chưa đăng nhập", "auth": False})
                return True
            if user["role"] != "admin":
                self._json(403, {"ok": False, "error": "Chỉ admin mới xem được danh sách tài khoản"})
                return True
            self._json(200, {"ok": True, "users": auth.list_users()})
            return True
        return False

    def _handle_config_get(self):
        try:
            from . import config as cfgmod
        except (ImportError, ValueError):
            _bootstrap()
            from shopeetool import config as cfgmod
        cfg = cfgmod.load()
        facebook = cfg.get("facebook") or {}
        sheet = cfg.get("sheet") or {}
        self._json(200, {
            "ok": True,
            "config": {
                "facebook": {
                    "app_id": facebook.get("app_id") or "",
                    "app_secret": facebook.get("app_secret") or "",
                    "api_version": facebook.get("api_version") or "v25.0",
                    "has_app_secret": bool(facebook.get("app_secret")),
                },
                "sheet": {
                    "url": sheet.get("url") or "",
                    "has_token": bool(sheet.get("token")),
                    "tab": sheet.get("tab") or "",
                },
                "workspace": data_dir(),
            },
        })

    def _api_get(self, path):
        if path == "/api/config":
            self._handle_config_get()
            return
        if path == "/api/networks":
            social = _social()
            cfg = social.load_cfg()
            self._send(200, json.dumps({"platforms": social.public_networks(cfg)}, ensure_ascii=False), "application/json; charset=utf-8")
            return
        if path == "/api/board":
            try:
                self._send(200, board_response(), "application/json; charset=utf-8")
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                self._json(503, {"ok": False, "error": "Danh sách đang được ghi. Hãy tải lại."})
            return
        if path == "/api/products/refresh":
            self._json(200, {"ok": True, **catalog_refresh_status()})
            return
        if path == "/api/short-link/generate":
            self._json(200, {"ok": True, **short_link_job_status()})
            return
        if path == "/api/short-link/export":
            try:
                body, filename, ctype, count = export_missing_short_links()
            except LookupError as e:
                self._json(404, {"ok": False, "error": str(e)})
                return
            except (ValueError, FileNotFoundError, OSError) as e:
                self._json(400, {"ok": False, "error": str(e)})
                return
            quoted = urllib.parse.quote(filename)
            self._send(200, body, ctype, {
                "Content-Disposition": f"attachment; filename=\"Batch-Custom-Links.xlsx\"; filename*=UTF-8''{quoted}",
                "X-Link-Count": str(count),
                "Cache-Control": "no-store",
            })
            return
        if path == "/api/auto-post":
            from . import auto_post
            self._json(200, {"ok": True, **auto_post.public_status()})
            return
        if path == "/api/groups":
            groups = _fb_groups()
            self._json(200, {
                "groups": groups.load_groups(),
                "facebook_session": groups.facebook_session_ready(),
                "facebook_accounts": groups.facebook_accounts(),
            })
            return
        if path == "/api/facebook/login/status":
            self._json(200, {"ok": True, **_fb_login().login_status()})
            return
        if path == "/api/facebook/login/frame":
            frame = _fb_login().login_frame()
            if not frame:
                self._send(204, b"", "image/jpeg", {"Cache-Control": "no-store"})
                return
            self._send(200, frame, "image/jpeg", {"Cache-Control": "no-store"})
            return
        self._json(404, {"ok": False, "error": "Không thấy trang"})

    def do_GET(self):
        path = urlparse(self.path).path
        if self._serve_static(path):
            return
        if path.startswith("/api/auth/"):
            if self._handle_auth_get(path):
                return
            self._json(404, {"ok": False, "error": "Không thấy trang"})
            return
        if path.startswith("/api/") or path.startswith("/media/"):
            auth, _token, user = self._require_user()
            if not user:
                return
            user_token, ws_token = self._enter_user(user["username"])
            try:
                if path.startswith("/media/"):
                    file_path = _safe_media(path[len("/media/"):])
                    if not file_path:
                        self._send(404, "Không thấy file", "text/plain; charset=utf-8")
                        return
                    ext = os.path.splitext(file_path)[1].lower()
                    ctype = {
                        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                        ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
                    }.get(ext, "application/octet-stream")
                    with open(file_path, "rb") as f:
                        self._send(200, f.read(), ctype)
                    return
                self._api_get(path)
            finally:
                self._leave_user(user_token, ws_token)
            return
        self._send(404, "Không thấy trang", "text/plain; charset=utf-8")

    def _read_body(self, limit):
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > limit:
            raise ValueError("Dữ liệu gửi lên không hợp lệ")
        return self.rfile.read(length)

    def _read_json(self):
        raw = self._read_body(100_000)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu gửi lên không hợp lệ")
        return data

    def _read_csv_upload(self):
        raw = self._read_body(5_000_000)
        ctype = self.headers.get("Content-Type") or ""
        if "multipart/form-data" not in ctype:
            return raw
        match = re.search(r'boundary="?([^";]+)"?', ctype)
        if not match:
            raise ValueError("File tải lên không hợp lệ")
        marker = b"--" + match.group(1).encode("utf-8", errors="replace")
        for part in raw.split(marker):
            if b'name="file"' not in part and b"filename=" not in part.lower():
                continue
            if b"\r\n\r\n" not in part:
                continue
            _head, data = part.split(b"\r\n\r\n", 1)
            if data.endswith(b"\r\n"):
                data = data[:-2]
            return data
        raise ValueError("Thiếu file CSV")

    def _handle_auth_post(self, path, body):
        auth = self._auth_mod()
        if path == "/api/auth/login":
            result = auth.authenticate(body.get("username") or "", body.get("password") or "")
            self._json(200, {
                "ok": True,
                "authenticated": True,
                "username": result["username"],
                "role": result["role"],
            }, {"Set-Cookie": auth.session_cookie(result["token"])})
            return True
        if path == "/api/auth/logout":
            token = auth.cookie_token(self.headers)
            auth.destroy_session(token)
            self._json(200, {"ok": True, "authenticated": False}, {"Set-Cookie": auth.session_cookie("", clear=True)})
            return True
        _auth, _token, user = self._require_user()
        if not user:
            return True
        if path == "/api/auth/password":
            current = str(body.get("current_password") or "")
            new_password = str(body.get("new_password") or "")
            auth.check_password(user["username"], current)
            auth.change_password(user["username"], new_password)
            self._json(200, {"ok": True, "message": "Đã đổi mật khẩu"})
            return True
        if path == "/api/auth/users":
            if user["role"] != "admin":
                self._json(403, {"ok": False, "error": "Chỉ admin mới tạo được tài khoản"})
                return True
            created = auth.create_user(
                body.get("username") or "",
                body.get("password") or "",
                body.get("role") or "user",
            )
            self._json(200, {"ok": True, "user": created, "users": auth.list_users()})
            return True
        if path == "/api/auth/users/delete":
            if user["role"] != "admin":
                self._json(403, {"ok": False, "error": "Chỉ admin mới xóa được tài khoản"})
                return True
            auth.delete_user(body.get("username") or "", user["username"])
            self._json(200, {"ok": True, "users": auth.list_users()})
            return True
        return False

    def _handle_config_post(self, body):
        try:
            from . import config as cfgmod
        except (ImportError, ValueError):
            _bootstrap()
            from shopeetool import config as cfgmod
        cfg = cfgmod.load()
        facebook = body.get("facebook") if isinstance(body.get("facebook"), dict) else {}
        sheet = body.get("sheet") if isinstance(body.get("sheet"), dict) else {}
        if "app_id" in facebook:
            cfg.setdefault("facebook", {})["app_id"] = str(facebook.get("app_id") or "").strip()
        if "app_secret" in facebook:
            secret = str(facebook.get("app_secret") or "").strip()
            if secret:
                cfg.setdefault("facebook", {})["app_secret"] = secret
        if "api_version" in facebook:
            version = str(facebook.get("api_version") or "").strip() or "v25.0"
            cfg.setdefault("facebook", {})["api_version"] = version
        if "url" in sheet:
            cfg.setdefault("sheet", {})["url"] = str(sheet.get("url") or "").strip()
        if "token" in sheet:
            token = str(sheet.get("token") or "").strip()
            if token:
                cfg.setdefault("sheet", {})["token"] = token
        if "tab" in sheet:
            cfg.setdefault("sheet", {})["tab"] = str(sheet.get("tab") or "").strip()
        cfgmod.save(cfg)
        self._handle_config_get()

    def _api_post(self, path):
        if path == "/api/short-link/import":
            result = import_short_links_csv(self._read_csv_upload())
            self._json(200, {"ok": True, **result})
            return
        body = self._read_json()
        if path == "/api/config":
            self._handle_config_post(body)
            return
        if path == "/api/short-link/generate":
            self._json(200, {"ok": True, **start_short_link_job()})
            return
        if path == "/api/short-link":
            item_id = str(body.get("item_id") or "").strip()
            if not item_id:
                raise ValueError("Thiếu mã sản phẩm")
            saved = set_short_link(item_id, body.get("short_link") or "")
            self._json(200, {"ok": True, "item_id": item_id, "short_link": saved})
            return
        if path == "/api/facebook/check":
            item_id = str(body.get("item_id") or "").strip() or None
            result = refresh_facebook(item_id)
            self._json(200, {"ok": True, **result})
            return
        if path == "/api/auto-post":
            from . import auto_post
            result = auto_post.update_settings(
                bool(body.get("enabled")),
                body.get("per_day"),
                body.get("page_id") or "",
                body.get("categories") if "categories" in body else None,
                body.get("dates") if "dates" in body else None,
                body.get("date_mode"),
            )
            self._json(200, {"ok": True, **result})
            return
        if path == "/api/products/refresh":
            self._json(200, {"ok": True, **start_catalog_refresh(body.get("category") or "")})
            return
        if path == "/api/facebook/post":
            result = post_products(
                body.get("item_ids") or [],
                body.get("mode") or "",
                body.get("schedule_at"),
                body.get("platform") or "facebook",
                body.get("page_id") or "",
            )
            self._json(200, {"ok": True, **result})
            return
        if path == "/api/facebook/login/start":
            self._json(200, {"ok": True, **_fb_login().login_start()})
            return
        if path == "/api/facebook/login/event":
            self._json(200, {"ok": True, **_fb_login().login_event(body)})
            return
        if path == "/api/facebook/login/cancel":
            self._json(200, {"ok": True, **_fb_login().login_cancel()})
            return
        if path == "/api/facebook/accounts/use":
            result = _fb_groups().use_facebook_account(body.get("id") or "")
            self._json(200, {"ok": True, "facebook_accounts": result, "facebook_session": True})
            return
        if path == "/api/facebook/accounts/remove":
            result = _fb_groups().remove_facebook_account(body.get("id") or "")
            self._json(200, {
                "ok": True,
                "facebook_accounts": result,
                "facebook_session": _fb_groups().facebook_session_ready(),
            })
            return
        if path == "/api/facebook/accounts/identify":
            result = _fb_groups().identify_facebook_accounts()
            self._json(200, {
                "ok": True,
                "facebook_accounts": result,
                "facebook_session": _fb_groups().facebook_session_ready(),
            })
            return
        if path == "/api/groups":
            groups = _fb_groups()
            limit = body.get("limit") if body.get("limit") not in (None, "") else 10
            record = groups.upsert_group(body.get("url") or "", limit)
            self._json(200, {
                "ok": True,
                "group": record,
                "facebook_session": groups.facebook_session_ready(),
            })
            return
        if path == "/api/groups/comment/draft":
            result = _fb_groups().draft_post_comment(body.get("permalink") or "")
            self._json(200, {"ok": True, **result})
            return
        if path == "/api/groups/comment":
            result = _fb_groups().publish_post_comment(
                body.get("permalink") or "",
                body.get("comment") or "",
            )
            self._json(200, {"ok": True, **result})
            return
        if path == "/api/networks/page":
            social = _social()
            cfg = social.load_cfg()
            page = social.upsert_page(
                cfg,
                str(body.get("platform") or ""),
                body.get("id") or "",
                body.get("name") or "",
                body.get("token") or "",
                body.get("enabled", True),
            )
            social.save_cfg(cfg)
            self._json(200, {"ok": True, "page": {
                "id": page["id"],
                "name": page["name"],
                "enabled": page["enabled"],
                "has_token": bool(page.get("token")),
            }})
            return
        self._json(404, {"ok": False, "error": "Không thấy trang"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/auth/"):
                if path == "/api/auth/login":
                    body = self._read_json()
                    if self._handle_auth_post(path, body):
                        return
                elif path == "/api/auth/logout":
                    if self._handle_auth_post(path, {}):
                        return
                else:
                    body = self._read_json()
                    auth, _token, user = self._require_user()
                    if not user:
                        return
                    user_token, ws_token = self._enter_user(user["username"])
                    try:
                        if self._handle_auth_post(path, body):
                            return
                        self._json(404, {"ok": False, "error": "Không thấy trang"})
                    finally:
                        self._leave_user(user_token, ws_token)
                    return
                self._json(404, {"ok": False, "error": "Không thấy trang"})
                return

            auth, _token, user = self._require_user()
            if not user:
                return
            user_token, ws_token = self._enter_user(user["username"])
            try:
                self._api_post(path)
            finally:
                self._leave_user(user_token, ws_token)
        except LookupError as e:
            self._json(404, {"ok": False, "error": str(e)})
        except (ValueError, json.JSONDecodeError, FileNotFoundError, RuntimeError, _fb_groups().FBGroupError) as e:
            self._json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)[:180]})


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from . import auth, auto_post
    info = auth.bootstrap()
    auto_post.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Trang quản trị: http://{HOST}:{PORT}")
    if info.get("created"):
        print("Đã tạo tài khoản admin. Mật khẩu mặc định: admin123 (đổi ngay trong Cấu hình).")
        print("Hoặc đặt biến môi trường SHOPEE_ADMIN_PASSWORD trước khi khởi động.")
    if info.get("migrated"):
        print(f"Đã chuyển dữ liệu cũ vào workspace của '{info['migrated']}'.")
    print("Nhấn Ctrl+C để dừng.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
