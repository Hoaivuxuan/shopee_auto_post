"""Facebook Graph API: token, danh sách Page, đăng video, bình luận."""
import os
import unicodedata

import requests

GRAPH = "https://graph.facebook.com"
# Mã lỗi liên quan giới hạn tốc độ / bị chặn tạm thời: nên dừng cả lượt chạy
FATAL_CODES = {4, 17, 32, 341, 368, 613}


class FBError(Exception):
    def __init__(self, message, code=None, subcode=None, http=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http = http


def hint_for(e):
    """Gợi ý cách xử lý bằng tiếng Việt cho một số mã lỗi hay gặp."""
    c = getattr(e, "code", None)
    if c == 190:
        return "Token hết hạn hoặc không hợp lệ: vào Cấu hình > Facebook, lấy lại token và bấm 'Lấy Page'."
    if c in (10, 200, 283):
        return ("Thiếu quyền: kiểm tra app đã thêm pages_manage_posts, publish_video (và pages_manage_metadata nếu cần), "
                "token được tạo SAU khi thêm quyền, và tài khoản là quản trị viên của Page.")
    if c in FATAL_CODES:
        return "Facebook đang giới hạn tốc độ hoặc chặn tạm thời: dừng và thử lại sau vài giờ, nên tăng thời gian nghỉ giữa các bài."
    if c == 100:
        return "Facebook báo tham số không hợp lệ (video không đúng định dạng/quá giới hạn hoặc Page ID sai)."
    return ""


def fb_check(resp):
    try:
        data = resp.json()
    except ValueError as e:
        raise FBError(f"Phản hồi không hợp lệ (HTTP {resp.status_code})", http=resp.status_code) from e
    if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise FBError(err.get("message", f"HTTP {resp.status_code}"),
                      err.get("code"), err.get("error_subcode"), resp.status_code)
    return data


def norm(s):
    return " ".join(unicodedata.normalize("NFC", str(s)).split()).lower()


def find_page(pages, key):
    k = norm(key)
    for p in pages:
        if str(p.get("id", "")).strip() == key.strip() or norm(p.get("name", "")) == k:
            return p
    return None


def exchange_token(app_id, app_secret, short_token, version):
    resp = requests.get(
        f"{GRAPH}/{version}/oauth/access_token",
        params={"grant_type": "fb_exchange_token", "client_id": app_id,
                "client_secret": app_secret, "fb_exchange_token": short_token},
        timeout=60,
    )
    data = fb_check(resp)
    return data["access_token"], data.get("expires_in")


def fetch_pages(user_token, version):
    """Lấy tất cả Page mà token người dùng quản trị: [{'id','name','access_token'}]."""
    url = f"{GRAPH}/{version}/me/accounts"
    params = {"fields": "id,name,access_token", "limit": 100, "access_token": user_token}
    found = []
    while url:
        data = fb_check(requests.get(url, params=params, timeout=60))
        found += data.get("data", [])
        url = data.get("paging", {}).get("next")
        params = None
    return found


def check_page(page, version):
    """Kiểm tra token của Page còn dùng được không; trả về tên Page theo Facebook."""
    resp = requests.get(f"{GRAPH}/{version}/{page['id']}",
                        params={"fields": "id,name", "access_token": page["token"]}, timeout=30)
    return fb_check(resp).get("name", "")


def upload_video(page, path, message, version, schedule_ts=None):
    """Đăng video lên Page bằng một request multipart (phù hợp video nhỏ hơn ~1GB).
    Nếu có schedule_ts (unix time) thì nhờ Facebook hẹn giờ đăng."""
    url = f"{GRAPH}/{version}/{page['id']}/videos"
    data = {"description": message, "access_token": page["token"]}
    if schedule_ts:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(int(schedule_ts))
    with open(path, "rb") as f:
        resp = requests.post(url, data=data,
                             files={"source": (os.path.basename(path), f, "video/mp4")},
                             timeout=3600)
    return fb_check(resp)["id"]


def post_comment(page, video_id, text, version):
    resp = requests.post(f"{GRAPH}/{version}/{video_id}/comments",
                         data={"message": text, "access_token": page["token"]}, timeout=60)
    return fb_check(resp).get("id")
