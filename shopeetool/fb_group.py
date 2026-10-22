"""Đọc bài trong một nhóm Facebook, khớp sản phẩm affiliate, bình luận link hoa hồng.

Graph API của Page chỉ bình luận được trên video do chính Page đăng.
Bài của người khác trong nhóm phải đọc bằng trình duyệt đã đăng nhập Facebook.
Phiên lưu tại data/facebook_state.json.
"""
import argparse
import json
import math
import os
import re
import shutil
import sys
import threading
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

from .paths import data_dir
from .shopee_affiliate import load_saved_products

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GROUP_DEFAULT = "https://www.facebook.com/groups/1466647950256964"
POST_DEFAULT = "https://www.facebook.com/share/p/19j3N5DBKX/"
STOPWORDS = {
    "anh", "bạn", "các", "cái", "cho", "chưa", "của", "đang", "đây", "được",
    "em", "hôm", "không", "làm", "mình", "mới", "một", "nay", "nếu", "nha",
    "những", "rất", "thì", "tôi", "trong", "trên", "vào", "với", "hay", "nhé",
    "nè", "ơi", "ạ", "nhé", "luôn", "thôi", "và", "các", "cái", "này", "kia",
    "hình", "như", "ảnh", "mẫu", "size", "combo", "set", "chính", "hãng",
    "hàng", "loại", "sale", "freeship", "ship", "đẹp", "xịn", "hot",
}
_TOKEN_RE = re.compile(r"[0-9a-zA-Zà-ỹÀ-Ỹ]+", re.UNICODE)
# Cụm từ trong caption không được tách ra từng chữ, kẻo "trái tim" khớp nhầm "cây cho trái".
IDIOMS = ("trái tim", "dễ thương", "xinh xắn", "thả tim")


class FBGroupError(Exception):
    pass


_GROUP_RE = re.compile(r"facebook\.com/groups/([^/?#]+)", re.I)
_FETCH_LOCK = threading.Lock()
_ACCOUNT_LOCK = threading.Lock()
DEFAULT_POST_LIMIT = 10
MAX_POST_LIMIT = 100
_NAME_SKIP = {"facebook", "đăng nhập", "log in", "log into facebook", "meta"}
_VN_TZ = timezone(timedelta(hours=7))


def fetch_in_progress() -> bool:
    return _FETCH_LOCK.locked()


def clamp_post_limit(value, default: int = DEFAULT_POST_LIMIT) -> int:
    """Số bài mới lấy về: tối thiểu 1, tối đa MAX_POST_LIMIT. Giá trị trống dùng mặc định."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number < 1:
        number = default
    return min(number, MAX_POST_LIMIT)


def session_path() -> str:
    return os.path.join(data_dir(), "facebook_state.json")


def accounts_catalog_path() -> str:
    return os.path.join(data_dir(), "facebook_accounts.json")


def account_state_path(account_id: str) -> str:
    safe = _account_id(account_id)
    return os.path.join(data_dir(), "facebook_accounts", f"{safe}.json")


def groups_path() -> str:
    return os.path.join(data_dir(), "fb_groups.json")


def parse_group_url(url: str) -> Dict[str, str]:
    """Chuẩn hóa link nhóm thành mã và URL https://www.facebook.com/groups/<mã>."""
    raw = (url or "").strip()
    if not raw:
        raise FBGroupError("Thiếu link nhóm")
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw
    match = _GROUP_RE.search(raw)
    if not match:
        raise FBGroupError("Link phải là nhóm Facebook, dạng facebook.com/groups/...")
    group_id = unquote(match.group(1)).strip().strip("/")
    if not group_id or group_id.lower() in {"feed", "discover", "joins"}:
        raise FBGroupError("Không đọc được mã nhóm từ link")
    return {"id": group_id, "url": f"https://www.facebook.com/groups/{group_id}"}


def facebook_session_ready() -> bool:
    path = session_path()
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    return bool(_user_id_in_file(path))


def _account_id(value: str) -> str:
    account_id = str(value or "").strip()
    if not re.fullmatch(r"[0-9]{5,20}", account_id):
        raise FBGroupError("Mã tài khoản Facebook không hợp lệ")
    return account_id


def _user_id_in_file(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    for cookie in data.get("cookies") or []:
        if isinstance(cookie, dict) and cookie.get("name") == "c_user" and cookie.get("value"):
            user_id = str(cookie.get("value"))
            return user_id if re.fullmatch(r"[0-9]{5,20}", user_id) else ""
    return ""


def _read_catalog() -> Dict[str, Any]:
    path = accounts_catalog_path()
    if not os.path.isfile(path):
        return {"active_id": "", "accounts": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"active_id": "", "accounts": []}
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        accounts = []
    clean = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        user_id = str(item.get("id") or "")
        if not re.fullmatch(r"[0-9]{5,20}", user_id):
            continue
        clean.append({
            "id": user_id,
            "name": str(item.get("name") or "")[:80],
            "saved_at": str(item.get("saved_at") or ""),
        })
    active_id = str((data or {}).get("active_id") or "")
    if not re.fullmatch(r"[0-9]{5,20}", active_id):
        active_id = ""
    return {"active_id": active_id, "accounts": clean}


def _write_catalog(catalog: Dict[str, Any]) -> None:
    path = accounts_catalog_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=2)


def _copy_session(source: str, target: str) -> None:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(source, target)


def _adopt_current_session(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Phiên cũ chỉ có một file. Đưa nó vào danh sách tài khoản để trang quản trị hiện tên."""
    user_id = _user_id_in_file(session_path())
    if not user_id:
        return catalog
    accounts = catalog["accounts"]
    if not any(item["id"] == user_id for item in accounts):
        saved = ""
        try:
            saved = datetime.fromtimestamp(os.path.getmtime(session_path()), _VN_TZ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            saved = datetime.now(_VN_TZ).strftime("%Y-%m-%d %H:%M")
        accounts.append({"id": user_id, "name": "", "saved_at": saved})
        _copy_session(session_path(), account_state_path(user_id))
    catalog["active_id"] = user_id
    return catalog


def facebook_accounts() -> Dict[str, Any]:
    with _ACCOUNT_LOCK:
        catalog = _adopt_current_session(_read_catalog())
        _write_catalog(catalog)
    active_id = catalog.get("active_id") or ""
    accounts = []
    for item in catalog.get("accounts") or []:
        accounts.append({
            "id": item["id"],
            "name": item.get("name") or "",
            "saved_at": item.get("saved_at") or "",
            "active": item["id"] == active_id,
        })
    accounts.sort(key=lambda item: (not item["active"], item.get("saved_at") or ""))
    return {"active_id": active_id, "accounts": accounts}


def remember_account(name: str = "") -> Dict[str, str]:
    """Ghi phiên vừa đăng nhập thành một tài khoản và đặt nó là tài khoản đang dùng."""
    user_id = _user_id_in_file(session_path())
    if not user_id:
        raise FBGroupError("Chưa thấy tài khoản Facebook sau khi đăng nhập")
    label = str(name or "").strip()[:80]
    now = datetime.now(_VN_TZ).strftime("%Y-%m-%d %H:%M")
    with _ACCOUNT_LOCK:
        catalog = _read_catalog()
        _copy_session(session_path(), account_state_path(user_id))
        found = False
        for item in catalog["accounts"]:
            if item["id"] != user_id:
                continue
            found = True
            item["saved_at"] = now
            if label:
                item["name"] = label
        if not found:
            catalog["accounts"].append({"id": user_id, "name": label, "saved_at": now})
        catalog["active_id"] = user_id
        _write_catalog(catalog)
    return {"id": user_id, "name": label}


def use_facebook_account(account_id: str) -> Dict[str, Any]:
    if fetch_in_progress():
        raise FBGroupError("Đang lấy bài nhóm. Hãy đợi xong rồi đổi tài khoản.")
    user_id = _account_id(account_id)
    source = account_state_path(user_id)
    if _user_id_in_file(source) != user_id:
        raise FBGroupError("Không còn phiên của tài khoản này. Hãy đăng nhập lại.")
    with _ACCOUNT_LOCK:
        catalog = _read_catalog()
        if not any(item["id"] == user_id for item in catalog["accounts"]):
            raise FBGroupError("Không thấy tài khoản này trong danh sách.")
        _copy_session(source, session_path())
        catalog["active_id"] = user_id
        _write_catalog(catalog)
    return facebook_accounts()


def remove_facebook_account(account_id: str) -> Dict[str, Any]:
    if fetch_in_progress():
        raise FBGroupError("Đang lấy bài nhóm. Hãy đợi xong rồi gỡ tài khoản.")
    user_id = _account_id(account_id)
    with _ACCOUNT_LOCK:
        catalog = _read_catalog()
        catalog["accounts"] = [item for item in catalog["accounts"] if item["id"] != user_id]
        try:
            os.remove(account_state_path(user_id))
        except OSError:
            pass
        if catalog.get("active_id") == user_id:
            nxt = catalog["accounts"][-1]["id"] if catalog["accounts"] else ""
            catalog["active_id"] = nxt
            if nxt and _user_id_in_file(account_state_path(nxt)) == nxt:
                _copy_session(account_state_path(nxt), session_path())
            elif os.path.isfile(session_path()):
                os.remove(session_path())
        _write_catalog(catalog)
    return facebook_accounts()


def profile_name_from_page(page) -> str:
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass
    raw = ""
    try:
        raw = page.evaluate(
            """() => {
                const skip = /^(edit|add |share |find |see |more$|all$|follow|message|people|highlights|posts|about|reels|photos)/i;
                let best = '';
                let bestSize = 0;
                for (const el of document.querySelectorAll('span, h1, h2')) {
                    const own = [...el.childNodes].filter((node) => node.nodeType === 3).map((node) => node.textContent.trim()).join(' ').trim();
                    if (!own || own.length > 60 || skip.test(own)) continue;
                    const size = parseFloat(getComputedStyle(el).fontSize) || 0;
                    const top = el.getBoundingClientRect().top;
                    if (top < 0 || top > 520 || size < 18) continue;
                    if (size > bestSize) {
                        bestSize = size;
                        best = own;
                    }
                }
                if (best) return best;
                return (document.title || '').trim();
            }"""
        ) or ""
    except Exception:
        try:
            raw = page.title() or ""
        except Exception:
            return ""
    raw = re.sub(r"^\(\d+\+?\)\s*", "", str(raw)).strip()
    name = re.split(r"\s*\|\s*", raw)[0].strip()
    folded = name.casefold()
    if not name or folded in _NAME_SKIP or "facebook" in folded:
        return ""
    return name[:80]


def identify_facebook_accounts() -> Dict[str, Any]:
    """Đọc tên hiển thị cho tài khoản đã lưu nhưng chưa có tên. Không gửi cookie ra ngoài file phiên."""
    if fetch_in_progress():
        return facebook_accounts()
    pending = [item["id"] for item in facebook_accounts()["accounts"] if not item.get("name")]
    found: Dict[str, str] = {}
    if pending:
        sync_playwright = _import_playwright()
        with sync_playwright() as playwright:
            browser = _launch(playwright, headless=True)
            try:
                for user_id in pending:
                    storage = account_state_path(user_id)
                    if _user_id_in_file(storage) != user_id:
                        continue
                    context = _new_context(browser, storage, {"width": 1100, "height": 720})
                    page = context.new_page()
                    try:
                        page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=20000)
                        name = profile_name_from_page(page)
                        if name:
                            found[user_id] = name
                    except Exception:
                        pass
                    try:
                        context.close()
                    except Exception:
                        pass
            finally:
                browser.close()
    if found:
        with _ACCOUNT_LOCK:
            catalog = _read_catalog()
            for item in catalog["accounts"]:
                if item["id"] in found:
                    item["name"] = found[item["id"]]
            _write_catalog(catalog)
    return facebook_accounts()


def load_groups() -> List[Dict[str, Any]]:
    path = groups_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    groups = data.get("groups") if isinstance(data, dict) else None
    return groups if isinstance(groups, list) else []


def save_groups(groups: List[Dict[str, Any]]) -> None:
    path = groups_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"groups": groups}, f, ensure_ascii=False, indent=2)


def report_path() -> str:
    return os.path.join(data_dir(), "fb_group_report.json")


def media_dir() -> str:
    path = os.path.join(data_dir(), "fb_group_media")
    os.makedirs(path, exist_ok=True)
    return path


def fold(text: str) -> str:
    """Giữ dấu tiếng Việt. Bỏ dấu sẽ biến 'tím' thành 'tim' và khớp nhầm 'trái tim'."""
    return unicodedata.normalize("NFC", text or "").lower()


def tokens(text: str) -> List[str]:
    words = _TOKEN_RE.findall(fold(text))
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def content_tokens(text: str) -> set:
    raw = fold(text)
    phrases = []
    for idiom in IDIOMS:
        if idiom in raw:
            phrases.append(idiom.replace(" ", "_"))
            raw = raw.replace(idiom, " ")
    return set(tokens(raw)) | set(phrases)


def offer_link(product: Dict[str, Any]) -> str:
    return (product.get("short_link") or product.get("long_link") or "").strip()


def _ahash_bits(image_path: str, size: int = 8) -> Optional[Tuple[int, ...]]:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("L").resize((size, size))
    except OSError:
        return None
    pixels = list(img.getdata())
    if not pixels:
        return None
    avg = sum(pixels) / len(pixels)
    return tuple(1 if px >= avg else 0 for px in pixels)


def _hamming(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    return sum(x != y for x, y in zip(a, b))


def _product_image_path(product: Dict[str, Any]) -> str:
    rel = product.get("image_file") or ""
    if not rel:
        return ""
    path = rel if os.path.isabs(rel) else os.path.join(data_dir(), rel)
    return path if os.path.isfile(path) else ""


class ProductIndex:
    def __init__(self, products: List[Dict[str, Any]]):
        self.products = [p for p in products if offer_link(p)]
        self.docs: List[set] = []
        df: Counter = Counter()
        for product in self.products:
            words = content_tokens(product.get("name") or "")
            self.docs.append(words)
            df.update(words)
        total = max(1, len(self.products))
        self.idf = {word: math.log((total + 1) / (count + 1)) + 1.0 for word, count in df.items()}
        self.hashes: List[Optional[Tuple[int, ...]]] = [
            _ahash_bits(_product_image_path(p)) for p in self.products
        ]

    def match(self, caption: str, image_paths: Optional[List[str]] = None, limit: int = 3) -> List[Dict[str, Any]]:
        query = content_tokens(caption)
        post_hashes = [h for h in (_ahash_bits(p) for p in (image_paths or [])) if h]
        ranked: List[Dict[str, Any]] = []
        for idx, product in enumerate(self.products):
            overlap = query & self.docs[idx]
            text_score = sum(self.idf.get(word, 1.2) for word in overlap)
            visual = 64
            if post_hashes and self.hashes[idx]:
                visual = min(_hamming(post_hash, self.hashes[idx]) for post_hash in post_hashes)
            visual_score = (12 - visual) * 2.0 if visual <= 8 else 0.0
            score = text_score + visual_score
            if score <= 0:
                continue
            ranked.append({
                "score": round(score, 2),
                "text_score": round(text_score, 2),
                "visual_distance": visual if visual_score else None,
                "overlap": sorted(overlap),
                "item_id": product.get("item_id"),
                "name": product.get("name"),
                "price_formatted": product.get("price_formatted") or "",
                "link": offer_link(product),
                "short_link": product.get("short_link") or "",
                "sold": int(product.get("historical_sold") or product.get("sold") or 0),
                "density": round(len(overlap) / max(1, len(self.docs[idx])), 3),
            })
        # Cùng điểm thì ưu tiên tên sản phẩm tập trung vào từ khóa, không phải câu mô tả dài có nhắc qua.
        ranked.sort(key=lambda row: (
            -row["score"], -row["density"], 0 if row["short_link"] else 1, -row["sold"], len(row["name"] or ""),
        ))
        return ranked[:limit]


def comment_text(product_name: str, link: str, prefix: str = "Mua tại: ") -> str:
    from .qwen_skills import hide_prices
    name = hide_prices(re.sub(r"\s+", " ", product_name or "").strip())
    if len(name) > 80:
        name = name[:77].rstrip() + "..."
    return f"{name}\n{prefix}{link}"


_LINK_MARK = "LINKHERE"


def _strip_model_text(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    cleaned = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", cleaned.strip())
    cleaned = cleaned.strip().strip('"').strip("“”")
    return re.sub(r"[ \t]*\n[ \t]*", "\n", cleaned).strip()


def _ollama_base() -> str:
    configured = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    return configured.rsplit("/api/", 1)[0]


def _spoken_product(name: str) -> str:
    spoken = re.sub(r"\d+\s*k(?:\s*/\s*\d+\s*c)?", "", name or "", flags=re.I)
    spoken = re.sub(r"\d[\d.\s]*₫", "", spoken)
    spoken = re.split(r"[,|/]", spoken)[0]
    spoken = re.sub(r"\s+", " ", spoken).strip(" -–.")
    if len(spoken) > 42:
        spoken = spoken[:42].rsplit(" ", 1)[0].strip()
    return spoken or "món này"


_COMMENT_FALLBACK = (
    "Viết một comment tiếng Việt, một hoặc hai câu, giọng mềm như người nhà góp đúng chuyện trong bài. "
    "Nhắc món gợi ý một lần. Thêm một hoặc hai icon mềm như 🤍 🌿 ☁️ 🌸. "
    "Đừng mở đầu bằng một câu than phiền có sẵn. Không URL, không nhắc giá hay số tiền. "
    f"Kết thúc bằng {_LINK_MARK}."
)


def _draft_comment(caption: str, product_name: str, _price: str = "") -> str:
    """qwen3 luôn mở khối suy nghĩ. Gọi raw và đóng khối đó để model viết thẳng tiếng Việt.

    Model 4B hay sửa URL, nên chỗ link chỉ là LINKHERE, gắn link thật ở ngoài.
    """
    from .qwen_skills import chat_prompt, hide_prices, skill_text
    caption = hide_prices(re.sub(r"\s+", " ", caption or "").strip())[:400]
    name = _spoken_product(hide_prices(product_name))[:80]
    icons = ("🤍 ", "🌿 ", "🌸 ", "☁️ ")
    starter = icons[sum(ord(ch) for ch in name) % len(icons)]
    user = f"Bài: {caption}\nMón gợi ý: {name}."
    prompt = chat_prompt(skill_text("comment.md", _COMMENT_FALLBACK), user, starter)
    payload = {
        "model": os.environ.get("OLLAMA_COMMENT_MODEL", "qwen3:4b"),
        "stream": False,
        "raw": True,
        "prompt": prompt,
        "options": {"temperature": 0.85, "num_predict": 120, "stop": ["<|im_end|>", "<|im_start|>", "</think>"]},
    }
    req = urllib.request.Request(
        _ollama_base() + "/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    text = _strip_model_text(starter + str(data.get("response") or ""))
    if _LINK_MARK not in text and re.search(r"[.!?…]$", text.strip()):
        text = text.strip() + " " + _LINK_MARK
    return text


def _draft_ok(text: str) -> bool:
    if not text or text.count(_LINK_MARK) != 1:
        return False
    prose = text.replace(_LINK_MARK, "").strip()
    if len(prose) < 30 or len(prose) > 320:
        return False
    if prose.count(".") + prose.count("!") + prose.count("?") > 3:
        return False
    if re.search(r"https?://|www\.", prose, re.I):
        return False
    from .qwen_skills import mentions_price
    if mentions_price(prose):
        return False
    folded = prose.casefold()
    banned = (
        "okay", "i need", "the user", "hoa hồng", "affiliate", "quảng cáo",
        "mua tại", "as an ai", "câu 1", "yêu cầu", "viết tiếp", "nội dung",
        "mình cũng gặp vụ này",
    )
    if any(word in folded for word in banned):
        return False
    return bool(re.search(r"[à-ỹÀ-Ỹ]", prose))


def natural_comment(caption: str, product_name: str, link: str, price: str = "") -> str:
    """Nhờ qwen viết góp ý, rồi gắn nguyên văn link hoa hồng. Giữ câu mẫu nếu model lỗi."""
    link = (link or "").strip()
    if not link:
        return comment_text(product_name, link)
    for _ in range(3):
        try:
            draft = _draft_comment(caption, product_name, price)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
            break
        if not _draft_ok(draft):
            continue
        return re.sub(r"\s*" + _LINK_MARK + r"\s*", " " + link, draft).strip()
    return comment_text(product_name, link)


def _post_key(url: str) -> str:
    return (url or "").split("?")[0].rstrip("/")


def find_saved_post(permalink: str) -> Dict[str, Any]:
    wanted = _post_key(permalink)
    if not wanted:
        raise FBGroupError("Thiếu link bài viết")
    for group in load_groups():
        for post in group.get("posts") or []:
            if _post_key(str(post.get("permalink") or "")) == wanted:
                return post
    raise FBGroupError("Không thấy bài này trong các nhóm đã lưu. Hãy lấy bài mới rồi thử lại.")


def draft_post_comment(permalink: str) -> Dict[str, Any]:
    """Viết nháp comment bằng qwen cho một bài đã lưu. Chưa gửi lên Facebook."""
    post = find_saved_post(permalink)
    match = post.get("match") if isinstance(post.get("match"), dict) else {}
    name = str(match.get("name") or "").strip()
    link = str(match.get("link") or "").strip()
    if not name or not link:
        raise FBGroupError("Bài này chưa khớp sản phẩm có link hoa hồng")
    plain = comment_text(name, link)
    text = natural_comment(
        str(post.get("caption") or ""),
        name,
        link,
        str(match.get("price_formatted") or ""),
    )
    return {
        "permalink": post.get("permalink") or permalink,
        "comment": text,
        "product_name": name,
        "fallback": text == plain,
    }


def publish_post_comment(permalink: str, message: str) -> Dict[str, str]:
    """Gửi đúng nội dung đã xác nhận lên bài Facebook."""
    text = re.sub(r"\r\n?", "\n", str(message or "")).strip()
    if not text or len(text) > 2000:
        raise FBGroupError("Nội dung bình luận không hợp lệ")
    post = find_saved_post(permalink)
    url = str(post.get("permalink") or "").strip()
    if not url:
        raise FBGroupError("Bài này không có link")
    if not _FETCH_LOCK.acquire(blocking=False):
        raise FBGroupError("Đang lấy bài hoặc gửi bình luận khác. Hãy đợi xong rồi thử lại.")
    try:
        sync_playwright = _import_playwright()
        with sync_playwright() as playwright:
            browser = _launch(playwright, headless=True)
            storage = session_path()
            context = _new_context(browser, storage if os.path.isfile(storage) else None)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                _require_login(page, context)
                post_comment(page, text)
                _save_state(context, storage)
            finally:
                browser.close()
        return {"permalink": url, "comment": text}
    finally:
        _FETCH_LOCK.release()


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise FBGroupError("Thiếu playwright. Chạy ./scripts/ubuntu/setup.sh trước.") from e
    return sync_playwright


def _logged_in(context) -> bool:
    return any(cookie.get("name") == "c_user" and cookie.get("value") for cookie in context.cookies())


def _launch(playwright, headless: bool):
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    try:
        return playwright.chromium.launch(headless=headless, args=args)
    except Exception:
        if headless:
            raise
        return playwright.chromium.launch(headless=True, args=args)


def _new_context(browser, storage: Optional[str], viewport: Optional[dict] = None):
    kwargs = {"locale": "vi-VN", "viewport": viewport or {"width": 1400, "height": 900}}
    if storage and os.path.isfile(storage):
        kwargs["storage_state"] = storage
    return browser.new_context(**kwargs)


def _save_state(context, storage: str) -> None:
    os.makedirs(os.path.dirname(storage), exist_ok=True)
    context.storage_state(path=storage)


_FEED_POSTS_JS = """
() => {
  const commentRe = /^(comment by|reply by|bình luận của|bình luận bởi|trả lời của)/i;
  function inComment(el) {
    let node = el;
    while (node) {
      const role = node.getAttribute && node.getAttribute("role");
      const label = (node.getAttribute && node.getAttribute("aria-label")) || "";
      if (role === "article" && commentRe.test(label)) return true;
      node = node.parentElement;
    }
    return false;
  }
  function postId(href) {
    const value = String(href || "");
    const match = value.match(/\\/posts\\/(\\d+)/)
      || value.match(/set=gm\\.(\\d+)/)
      || value.match(/[?&]story_fbid=(\\d+)/)
      || value.match(/\\/permalink\\/(\\d+)/)
      || value.match(/multi_permalinks=(\\d+)/);
    return match ? match[1] : "";
  }
  function clean(text) {
    return String(text || "")
      .replace(/\\s+/g, " ")
      .replace(/\\s*(?:…|\\.\\.\\.)?\\s*(?:See more|Xem thêm)\\s*$/i, "")
      .trim();
  }
  function permalink(id) {
    const group = (location.pathname.match(/\\/groups\\/([^/?#]+)/) || [])[1] || "";
    if (!group || !id) return "";
    return "https://www.facebook.com/groups/" + group + "/posts/" + id + "/";
  }
  const messages = [...document.querySelectorAll('[data-ad-rendering-role="story_message"]')]
    .filter((el) => !inComment(el));
  if (!messages.length) {
    document.querySelectorAll('[data-ad-preview="message"]').forEach((el) => {
      if (!inComment(el)) messages.push(el);
    });
  }
  const found = [];
  const seen = new Set();
  for (const msg of messages) {
    let node = msg;
    let id = "";
    let card = msg.parentElement || msg;
    for (let i = 0; i < 14 && node; i++) {
      const link = [...node.querySelectorAll("a")].find((anchor) => !inComment(anchor) && postId(anchor.href));
      if (link) {
        id = postId(link.href);
        card = node;
        break;
      }
      node = node.parentElement;
    }
    if (!id) {
      node = msg;
      for (let i = 0; i < 16 && node; i++) {
        const link = [...node.querySelectorAll("a")].find((anchor) => postId(anchor.href));
        if (link) {
          id = postId(link.href);
          break;
        }
        node = node.parentElement;
      }
    }
    const key = id || clean(msg.innerText).slice(0, 180);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const images = [...card.querySelectorAll("img")]
      .filter((img) => !inComment(img))
      .map((img) => ({src: img.currentSrc || img.src || "", alt: img.alt || ""}))
      .filter((img) => img.src && (img.src.includes("scontent") || img.src.includes("fbcdn")))
      .slice(0, 4);
    found.push({
      permalink: permalink(id),
      caption: clean(msg.innerText),
      image_alts: images.map((img) => img.alt).filter(Boolean),
      image_urls: images.map((img) => img.src).filter(Boolean),
    });
  }
  return found;
}
"""


def _posts_in_view(page) -> List[Dict[str, Any]]:
    """Đọc caption của bài đăng. Bỏ khối bình luận (role=article 'Comment by ...')."""
    try:
        rows = page.evaluate(_FEED_POSTS_JS) or []
    except Exception:
        return []
    posts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        posts.append({
            "permalink": row.get("permalink") or "",
            "caption": row.get("caption") or "",
            "image_alts": row.get("image_alts") or [],
            "image_urls": row.get("image_urls") or [],
        })
    return posts


def _download(context, url: str, dest: str) -> bool:
    try:
        resp = context.request.get(url, timeout=30000)
        if not resp.ok:
            return False
        body = resp.body()
        if len(body) < 1000:
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(body)
        return True
    except Exception:
        return False


def collect_group_posts(page, limit: int) -> List[Dict[str, Any]]:
    """Lấy tối đa `limit` bài mới nhất. Chỉ lấy caption bài đăng, không lấy bình luận."""
    page.wait_for_timeout(2500)
    found: List[Dict[str, Any]] = []
    seen = set()
    stalled = 0
    rounds = max(8, min(int(limit) + 2, 80))
    for _ in range(rounds):
        before = len(found)
        for post in _posts_in_view(page):
            key = post.get("permalink") or (post.get("caption") or "")[:180]
            if not key or key in seen:
                continue
            if not post.get("caption") and not post.get("permalink"):
                continue
            seen.add(key)
            found.append(post)
            if len(found) >= limit:
                return found
        if len(found) == before:
            stalled += 1
            if stalled >= 3:
                break
        else:
            stalled = 0
        page.mouse.wheel(0, 2800)
        page.wait_for_timeout(1600)
    return found


def read_open_post(page) -> Dict[str, Any]:
    page.wait_for_timeout(2000)
    posts = _posts_in_view(page)
    wanted = ""
    match = re.search(r"/posts/(\d+)", page.url) or re.search(r"set=gm\.(\d+)", page.url)
    if match:
        wanted = match.group(1)
    if wanted:
        for post in posts:
            if wanted in (post.get("permalink") or ""):
                post["permalink"] = post.get("permalink") or page.url.split("?")[0]
                return post
    if posts:
        post = posts[0]
        post["permalink"] = post.get("permalink") or page.url.split("?")[0]
        return post
    body = ""
    try:
        body = page.locator("body").inner_text()[:500]
    except Exception:
        pass
    raise FBGroupError(f"Không thấy bài viết. Trang hiện tại: {page.url}. {body[:180]}")


def _safe_folder(group_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", group_id)[:80] or "group"


def _rel_media(path: str) -> str:
    if not path:
        return ""
    rel = os.path.relpath(path, data_dir()).replace("\\", "/")
    if rel.startswith(".."):
        return ""
    return rel


def attach_local_images(context, posts: List[Dict[str, Any]], folder: str = "") -> None:
    root = os.path.join(media_dir(), folder) if folder else media_dir()
    for i, post in enumerate(posts, 1):
        files = []
        for j, url in enumerate(post.get("image_urls") or [], 1):
            dest = os.path.join(root, f"post_{i}_{j}.jpg")
            if _download(context, url, dest):
                files.append(dest)
        post["image_files"] = files


def _comment_box(page):
    labels = (
        "Viết bình luận",
        "Viết bình luận công khai",
        "Write a comment",
        "Write a public comment",
    )
    for label in labels:
        loc = page.locator(f'div[role="textbox"][aria-label*="{label}"]')
        if loc.count():
            return loc.first
    loc = page.locator('div[contenteditable="true"][role="textbox"]')
    if loc.count():
        return loc.last
    return None


def post_comment(page, message: str) -> None:
    box = _comment_box(page)
    if box is None:
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(1000)
        box = _comment_box(page)
    if box is None:
        raise FBGroupError("Không thấy ô bình luận. Tài khoản có thể chưa vào được nhóm, hoặc Facebook chặn ô nhập.")
    box.click(timeout=10000)
    page.keyboard.insert_text(message)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    snippet = message.split("\n")[-1][:40]
    if snippet and snippet not in (page.locator("body").inner_text() or ""):
        button = page.get_by_role("button", name=re.compile(r"Bình luận|Comment", re.I))
        if button.count():
            button.first.click()
            page.wait_for_timeout(2500)


def ensure_short_link(match: Dict[str, Any], products: List[Dict[str, Any]]) -> str:
    """Lấy link s.shopee.vn cho sản phẩm sắp bình luận. Giữ link dài nếu API không trả về."""
    if match.get("short_link"):
        return match["short_link"]
    item_id = str(match.get("item_id") or "")
    product = next((p for p in products if str(p.get("item_id")) == item_id), None)
    if not product:
        return match.get("link") or ""
    try:
        from .shopee_affiliate import app_dir, fetch_short_links_live
    except ImportError:
        from shopeetool.shopee_affiliate import app_dir, fetch_short_links_live
    curl_file = os.path.join(app_dir(), "api_shopee", "curl_productOfferLinks.txt")
    mapping = fetch_short_links_live([product], curl_file, batch_size=1)
    link = mapping.get(item_id) or ""
    if link:
        match["short_link"] = link
        match["link"] = link
        product["short_link"] = link
        return link
    return match.get("link") or ""


def analyze_posts(posts: List[Dict[str, Any]], index: ProductIndex, min_score: float) -> List[Dict[str, Any]]:
    rows = []
    for post in posts:
        blob = " ".join([post.get("caption") or "", " ".join(post.get("image_alts") or [])])
        matches = index.match(blob, post.get("image_files") or [])
        best = matches[0] if matches else None
        rows.append({
            "permalink": post.get("permalink") or "",
            "caption": post.get("caption") or "",
            "image_alts": post.get("image_alts") or [],
            "image_files": post.get("image_files") or [],
            "matches": matches,
            "comment": comment_text(best["name"], best["link"]) if best and best["score"] >= min_score else "",
        })
    return rows


def _require_login(page, context) -> None:
    page.wait_for_timeout(1500)
    if _logged_in(context) and "login" not in page.url:
        return
    raise FBGroupError(
        "Chưa đăng nhập Facebook. Trên trang quản trị, mục Nhóm Facebook, bấm "
        "Đăng nhập Facebook và đăng nhập trong khung hình từ laptop của bạn."
    )


def _group_title(page, fallback: str) -> str:
    title = re.sub(r"\s*[|–-]\s*Facebook\s*$", "", (page.title() or "")).strip()
    if not title or title.lower() in {"facebook", "log in", "log into facebook", "đăng nhập"}:
        return fallback
    return title[:120]


def _public_posts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    public = []
    for row in rows:
        files = [rel for rel in (_rel_media(path) for path in (row.get("image_files") or [])) if rel]
        best = (row.get("matches") or [None])[0]
        match = None
        if best:
            match = {
                "item_id": best.get("item_id") or "",
                "name": best.get("name") or "",
                "score": best.get("score") or 0,
                "link": best.get("link") or "",
                "price_formatted": best.get("price_formatted") or "",
            }
        public.append({
            "permalink": row.get("permalink") or "",
            "caption": row.get("caption") or "",
            "image_files": files,
            "match": match,
            "comment": row.get("comment") or "",
        })
    return public


def fetch_group_feed(group_url: str, limit: int = DEFAULT_POST_LIMIT, catalog: str = "products_affiliate.json") -> Dict[str, Any]:
    """Mở nhóm bằng phiên Facebook đã lưu và lấy các bài mới nhất."""
    info = parse_group_url(group_url)
    limit = clamp_post_limit(limit)
    if not _FETCH_LOCK.acquire(blocking=False):
        raise FBGroupError("Đang lấy bài của một nhóm khác. Hãy đợi xong rồi thử lại.")
    try:
        products = load_saved_products(catalog) or []
        index = ProductIndex(products) if products else None
        sync_playwright = _import_playwright()
        with sync_playwright() as p:
            browser = _launch(p, headless=True)
            storage = session_path()
            context = _new_context(browser, storage if os.path.isfile(storage) else None)
            page = context.new_page()
            page.goto(info["url"], wait_until="domcontentloaded", timeout=60000)
            _require_login(page, context)
            name = _group_title(page, info["id"])
            posts = collect_group_posts(page, limit)
            attach_local_images(context, posts, _safe_folder(info["id"]))
            _save_state(context, storage)
            browser.close()
        analyzed = analyze_posts(posts, index, 2.0) if index else [
            {
                "permalink": post.get("permalink") or "",
                "caption": post.get("caption") or "",
                "image_files": post.get("image_files") or [],
                "matches": [],
                "comment": "",
            }
            for post in posts
        ]
        return {"id": info["id"], "url": info["url"], "name": name, "posts": _public_posts(analyzed)}
    finally:
        _FETCH_LOCK.release()


def upsert_group(url: str, limit: int = DEFAULT_POST_LIMIT) -> Dict[str, Any]:
    """Lưu nhóm theo link và lấy bài mới nhất. Lỗi đăng nhập vẫn giữ nhóm để quản lý."""
    info = parse_group_url(url)
    limit = clamp_post_limit(limit)
    groups = load_groups()
    record = next((group for group in groups if group.get("id") == info["id"]), None)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if record is None:
        record = {
            "id": info["id"],
            "url": info["url"],
            "name": info["id"],
            "added_at": now,
            "fetched_at": "",
            "fetch_error": "",
            "posts": [],
        }
        groups.insert(0, record)
    else:
        record["url"] = info["url"]
    try:
        fetched = fetch_group_feed(info["url"], limit=limit)
        record["name"] = fetched.get("name") or record.get("name") or info["id"]
        record["posts"] = fetched.get("posts") or []
        record["fetched_at"] = now
        record["fetch_error"] = ""
    except FBGroupError as e:
        record["fetch_error"] = str(e)
    save_groups(groups)
    return record


def login_facebook(storage: str, timeout: int = 600) -> None:
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        browser = _launch(p, headless=False)
        context = _new_context(browser, storage if os.path.isfile(storage) else None)
        page = context.new_page()
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=60000)
        print("[*] Hãy đăng nhập Facebook trong cửa sổ Chrome. Cửa sổ sẽ tự đóng sau khi thấy phiên.")
        elapsed = 0
        while elapsed < timeout:
            page.wait_for_timeout(1000)
            elapsed += 1
            if _logged_in(context):
                _save_state(context, storage)
                print(f"[+] Đã lưu phiên Facebook: {storage}")
                browser.close()
                return
        browser.close()
    raise FBGroupError("Hết thời gian chờ đăng nhập Facebook.")


def run(
    group_url: str,
    post_url: str,
    limit: int,
    do_comment: bool,
    min_score: float,
    catalog: str,
    storage: str,
    headless: bool,
) -> Dict[str, Any]:
    products = load_saved_products(catalog)
    if not products:
        raise FBGroupError(f"Không đọc được sản phẩm từ {catalog}")
    index = ProductIndex(products)
    print(f"[*] Catalog: {len(index.products)} sản phẩm có link hoa hồng.")

    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        browser = _launch(p, headless=headless)
        context = _new_context(browser, storage if os.path.isfile(storage) else None)
        page = context.new_page()
        page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
        _require_login(page, context)
        print(f"[*] Đang lấy {limit} bài gần nhất trong nhóm...")
        posts = collect_group_posts(page, limit)
        print(f"[+] Lấy được {len(posts)} bài từ feed.")

        target = None
        if post_url:
            page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            _require_login(page, context)
            target = read_open_post(page)
            target["requested_url"] = post_url
            print(f"[+] Bài thử: {target.get('caption', '')[:120]}")

        bundle = posts + ([target] if target else [])
        attach_local_images(context, bundle)
        analyzed = analyze_posts(bundle, index, min_score)
        feed_rows = analyzed[: len(posts)]
        target_row = analyzed[-1] if target else None

        commented = False
        if do_comment:
            if not target_row or not target_row.get("comment"):
                best = (target_row or {}).get("matches") or []
                detail = best[0]["name"] if best else "không có ứng viên"
                raise FBGroupError(
                    f"Chưa bình luận vì mức khớp chưa đủ (ngưỡng {min_score}). Ứng viên gần nhất: {detail}"
                )
            best = target_row["matches"][0]
            link = ensure_short_link(best, products)
            target_row["comment"] = natural_comment(
                target_row.get("caption") or "",
                best["name"],
                link,
                best.get("price_formatted") or "",
            )
            post_comment(page, target_row["comment"])
            commented = True
            shot = os.path.join(data_dir(), "fb_group_comment.png")
            page.screenshot(path=shot, full_page=False)
            print(f"[+] Đã gửi bình luận. Ảnh màn hình: {shot}")

        _save_state(context, storage)
        browser.close()

    report = {
        "group_url": group_url,
        "post_url": post_url,
        "feed": feed_rows,
        "target": target_row,
        "commented": commented,
    }
    dest = report_path()
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[+] Báo cáo: {dest}")
    _print_report(feed_rows, target_row, commented)
    return report


def _print_report(feed_rows: List[Dict[str, Any]], target: Optional[Dict[str, Any]], commented: bool) -> None:
    print("\n" + "=" * 72)
    print(f" FEED NHÓM: {len(feed_rows)} BÀI")
    print("=" * 72)
    for i, row in enumerate(feed_rows, 1):
        best = (row.get("matches") or [None])[0]
        label = f"{best['score']} | {best['name']}" if best else "không khớp"
        print(f"[{i}] {(row.get('caption') or '(không caption)')[:110]}")
        print(f"    Khớp: {label}")
        if row.get("permalink"):
            print(f"    {row['permalink']}")
    if target:
        print("-" * 72)
        print("BÀI THỬ")
        print(target.get("caption") or "(không caption)")
        for match in target.get("matches") or []:
            print(f"  - {match['score']} | {match['name']}")
            print(f"    {match['link']}")
        if target.get("comment"):
            print("Nội dung bình luận:")
            print(target["comment"])
        print("Đã gửi bình luận." if commented else "Chưa gửi bình luận.")


def main():
    parser = argparse.ArgumentParser(description="Khớp sản phẩm affiliate và bình luận vào bài trong nhóm Facebook.")
    parser.add_argument("--group", default=GROUP_DEFAULT, help="URL nhóm")
    parser.add_argument("--limit", type=int, default=10, help="Số bài gần nhất cần lấy")
    parser.add_argument("--post", default=POST_DEFAULT, help="Bài viết cần thử bình luận")
    parser.add_argument("--comment", action="store_true", help="Gửi bình luận lên --post nếu khớp đủ điểm")
    parser.add_argument("--login", action="store_true", help="Mở Chrome để đăng nhập Facebook và lưu phiên")
    parser.add_argument("--catalog", default="products_affiliate.json")
    parser.add_argument("--min-score", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    try:
        if args.login:
            login_facebook(session_path())
            return
        run(
            group_url=args.group,
            post_url=args.post,
            limit=clamp_post_limit(args.limit),
            do_comment=args.comment,
            min_score=args.min_score,
            catalog=args.catalog,
            storage=session_path(),
            headless=args.headless,
        )
    except FBGroupError as e:
        print(f"[Lỗi] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
