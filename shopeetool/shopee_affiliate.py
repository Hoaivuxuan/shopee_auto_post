"""Shopee Affiliate: Lấy danh sách sản phẩm và link hoa hồng từ API Shopee Affiliate.

Hỗ trợ 2 chế độ:
1. Đọc & trích xuất từ file curl response có sẵn (api_shopee/curl_*.txt).
2. Gọi trực tiếp API Shopee Affiliate (online) để lấy link hoa hồng rút gọn s.shopee.vn hàng loạt.
Dữ liệu kết quả được lưu vào file JSON trong thư mục data/.
"""
import argparse
from datetime import datetime
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

try:
    import requests
except ImportError:
    requests = None


# Đảm bảo console xuất tiếng Việt không bị lỗi font trên Windows / terminal
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def app_dir() -> str:
    """Thư mục gốc của dự án."""
    try:
        from .paths import app_dir as _app_dir
        return _app_dir()
    except (ImportError, ValueError):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """Thư mục data/ của dự án."""
    try:
        from .paths import data_dir as _data_dir
        return _data_dir()
    except (ImportError, ValueError):
        d = os.path.join(app_dir(), "data")
        os.makedirs(d, exist_ok=True)
        return d


# Các tab trên https://affiliate.shopee.vn/offer/product_offer, đúng thứ tự giao diện.
# list_type=3 kèm match_id là tab ngành hàng. Đồ gia dụng là trang ưu đãi cũ.
_PAGE = "curl_trend_product.txt"
_LINKS = "curl_productOfferLinks.txt"
OFFERS = (
    {
        "id": "all",
        "name": "Tất cả",
        "list_type": "0",
        "match_id": "",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "xtra",
        "name": "Hoa hồng Xtra",
        "list_type": "7",
        "match_id": "",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "trend",
        "name": "Bán chạy nhất",
        "list_type": "2",
        "match_id": "",
        "page_file": _PAGE,
        "links_file": _LINKS,
        "response_file": "response_trend_product.json",
    },
    {
        "id": "100636",
        "name": "Nhà Cửa & Đời Sống",
        "list_type": "3",
        "match_id": "100636",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "100630",
        "name": "Sắc Đẹp",
        "list_type": "3",
        "match_id": "100630",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "100629",
        "name": "Bách Hóa Online",
        "list_type": "3",
        "match_id": "100629",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "100017",
        "name": "Thời Trang Nữ",
        "list_type": "3",
        "match_id": "100017",
        "page_file": _PAGE,
        "links_file": _LINKS,
    },
    {
        "id": "100010",
        "name": "Đồ gia dụng",
        "page_file": "curl_home_app.txt",
        "links_file": "curl_home_app_product.txt",
    },
)

_OFFER_ALIASES = {
    "trend": ("Sản phẩm xu hướng", "Top Performing"),
    "100636": ("Nhà cửa & Đời sống",),
}

# list_type=2 trên /offer/product_offer. Giữ để file curl cũ vẫn bấm đúng tab.
_LIST_TABS = {
    "2": ("Bán chạy nhất", "Sản phẩm xu hướng", "Top Performing"),
}

# SPC_EC có thể là "-" khi vẫn còn phiên. SPC_ST và SPC_U mới là cookie đăng nhập.
_SESSION_COOKIES = ("SPC_ST", "SPC_U")

_KEEP_ON_MERGE = {
    "short_link",
    "image_file",
    "video_file",
    "publications",
    "facebook_video_id",
    "facebook_page_id",
    "facebook_page_name",
    "facebook_status",
    "facebook_permalink",
    "facebook_error",
    "facebook_checked_at",
    "facebook_scheduled_at",
    "facebook_comment_id",
}


def offer_by_key(offer_key: str) -> Dict[str, str]:
    """Tìm mục theo mã, tên trên trang hoa hồng, hoặc tên cũ còn trong dữ liệu."""
    key = str(offer_key or "").strip()
    folded = key.casefold()
    for offer in OFFERS:
        labels = [offer["id"], offer["name"], *_OFFER_ALIASES.get(offer["id"], ())]
        if any(str(item).casefold() == folded for item in labels):
            return offer
    known = ", ".join(f"{item['id']} ({item['name']})" for item in OFFERS)
    raise ValueError(f"Không có mục {offer_key}. Các mục: {known}")


def canonical_category(name: str = "", category_id: str = "") -> Tuple[str, str]:
    """Đưa tên mục cũ về đúng tab trên trang hoa hồng sản phẩm."""
    folded = str(name or "").strip().casefold()
    current_id = str(category_id or "").strip()
    for offer in OFFERS:
        labels = [offer["name"], *_OFFER_ALIASES.get(offer["id"], ())]
        if current_id and current_id == offer["id"]:
            return offer["id"], offer["name"]
        if folded and any(str(item).casefold() == folded for item in labels):
            return offer["id"], offer["name"]
    return current_id, str(name or "").strip()


def offer_page_url(curl_info: Dict[str, Any]) -> str:
    """URL trang danh sách. Mục ngành hàng nằm ở /offer/shopee_offer/, xu hướng ở /offer/product_offer."""
    url = str(curl_info.get("url") or "")
    referer = str((curl_info.get("headers") or {}).get("referer") or "")
    for candidate in (url, referer):
        path = urlparse(candidate).path.rstrip("/")
        if path.endswith("/offer/product_offer") or "/offer/shopee_offer/" in path:
            return candidate.split("?", 1)[0]
    raise RuntimeError("File curl không có trang danh sách sản phẩm.")


def list_page_count(total_count: int, page_limit: int, cap: int = 0) -> int:
    """Số trang cần lấy. API xu hướng cố định 20 sản phẩm/trang và báo tổng 500."""
    limit = int(page_limit or 0)
    total = int(total_count or 0)
    if limit <= 0 or total <= 0:
        return max(int(cap or 0), 0)
    need = (total + limit - 1) // limit
    if cap and int(cap) > 0:
        return min(int(cap), need)
    return need


def _query_value(url: str, key: str) -> str:
    values = parse_qs(urlparse(url).query).get(key) or []
    return str(values[0]) if values else ""


def session_cookie_missing(cookies: Dict[str, Any]) -> bool:
    """Thiếu cookie phiên thì trang affiliate sẽ đẩy về màn đăng nhập."""
    jar = cookies or {}
    for name in _SESSION_COOKIES:
        value = str(jar.get(name) or "").strip()
        if not value or value == "-":
            return True
    return False


def is_login_url(url: str) -> bool:
    """Trang đăng nhập Shopee. Trang kiểm tra traffic không phải hết phiên."""
    raw = str(url or "")
    low = raw.lower()
    if "verify/traffic" in low:
        return False
    if "/buyer/login" in low or "/seller/login" in low or "accounts.shopee" in low:
        return True
    path = urlparse(low).path.rstrip("/")
    return path.endswith("/login")


class AffiliateLoginRequired(RuntimeError):
    """Trang affiliate đẩy về đăng nhập, cần mở cửa sổ để người dùng đăng nhập."""


def affiliate_session_ready(url: str, cookies: Dict[str, Any]) -> bool:
    """Đã rời trang đăng nhập và còn cookie phiên."""
    if "verify/traffic" in str(url or "").lower():
        return False
    if is_login_url(url):
        return False
    return not session_cookie_missing(cookies)


def official_login_url(return_to: str) -> str:
    """Trang đăng nhập Shopee. Sau khi đăng nhập sẽ quay lại trang hoa hồng."""
    target = str(return_to or "").strip() or "https://affiliate.shopee.vn/offer/product_offer"
    return "https://shopee.vn/buyer/login?next=" + quote(target, safe="")


def display_from_process_list(listing: str) -> str:
    """Lấy màn hình thật từ tiến trình Xorg, bỏ màn hình ảo."""
    for line in str(listing or "").splitlines():
        if "Xorg" not in line and "Xwayland" not in line:
            continue
        match = re.search(r"(?:^|\s)(:\d+)(?:\s|$)", line)
        if match:
            return match.group(1)
    return ""


def desktop_display() -> str:
    """Màn hình đang mở. Biến DISPLAY trống vẫn dùng được màn hình Xorg của máy."""
    current = str(os.environ.get("DISPLAY") or "").strip()
    if current:
        return current
    try:
        listing = subprocess.check_output(["ps", "-eo", "args"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return ""
    return display_from_process_list(listing)


def desktop_env() -> Dict[str, str]:
    """Môi trường để cửa sổ Chrome hiện trên màn hình đang đăng nhập."""
    env = dict(os.environ)
    display = desktop_display()
    if display:
        env["DISPLAY"] = display
    if not env.get("XAUTHORITY"):
        for candidate in ("/var/run/lightdm/root/:0", os.path.expanduser("~/.Xauthority")):
            if os.path.isfile(candidate):
                env["XAUTHORITY"] = candidate
                break
    return env


def browser_cookies(context) -> Dict[str, str]:
    """Cookie Shopee đang có trong trình duyệt."""
    jar: Dict[str, str] = {}
    for cookie in context.cookies():
        domain = str(cookie.get("domain") or "")
        if "shopee.vn" not in domain:
            continue
        name = str(cookie.get("name") or "").strip()
        if name:
            jar[name] = str(cookie.get("value") or "")
    return jar


def write_curl_cookies(curl_file: str, cookies: Dict[str, str]) -> None:
    """Ghi cookie mới vào tham số -b của file curl, giữ nguyên phần response."""
    with open(curl_file, "r", encoding="utf-8") as handle:
        content = handle.read()
    head, sep, tail = content.partition("response:")
    parts = []
    for name, value in cookies.items():
        key = str(name or "").strip()
        if not key:
            continue
        safe = str(value or "").replace("'", "").replace('"', "")
        parts.append(f"{key}={safe}")
    jar = "; ".join(parts)
    pattern = re.compile(r"-b\s+(?:\$)?'[^']*'|-b\s+\"[^\"]*\"", re.DOTALL)
    if not pattern.search(head):
        raise RuntimeError(f"Không thấy dòng cookie trong {os.path.basename(curl_file)}")
    head = pattern.sub(lambda _match: "-b '" + jar + "'", head, count=1)
    with open(curl_file, "w", encoding="utf-8") as handle:
        handle.write(head + sep + tail)


def _launch_chrome(playwright, visible: bool):
    """Mở Chrome. visible=True thì hiện cửa sổ trên màn hình máy."""
    launch_args = ["--disable-dev-shm-usage"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        launch_args.append("--no-sandbox")
    kwargs: Dict[str, Any] = {"channel": "chrome", "headless": not visible, "args": launch_args}
    if visible:
        if not desktop_display():
            raise RuntimeError("Không có màn hình để mở trang đăng nhập Shopee.")
        kwargs["env"] = desktop_env()
    try:
        return playwright.chromium.launch(**kwargs)
    except Exception as exc:
        if "channel" not in kwargs:
            if visible:
                raise RuntimeError("Không mở được cửa sổ Chrome để đăng nhập Shopee.") from exc
            raise
        fallback = {key: value for key, value in kwargs.items() if key != "channel"}
        try:
            return playwright.chromium.launch(**fallback)
        except Exception as inner:
            if visible:
                raise RuntimeError("Không mở được cửa sổ Chrome để đăng nhập Shopee.") from inner
            raise inner


def _wait_for_shopee_login(page, context, curl_file: str, page_url: str, timeout: int = 600) -> None:
    """Hiện trang đăng nhập chính thức, đợi người dùng đăng nhập, rồi lưu cookie."""
    print("[*] Cookie đăng nhập đã hết hạn. Đang mở trang đăng nhập Shopee...")
    page.goto(official_login_url(page_url), wait_until="domcontentloaded", timeout=60000)
    print("[*] Hãy đăng nhập trên cửa sổ Chrome. Xong, chương trình tự lấy cookie và cập nhật sản phẩm.")
    deadline = time.time() + timeout
    jar: Dict[str, str] = {}
    while time.time() < deadline:
        try:
            if page.is_closed():
                break
            jar = browser_cookies(context)
            if affiliate_session_ready(page.url, jar):
                break
        except Exception:
            break
        page.wait_for_timeout(1000)
    if not affiliate_session_ready(getattr(page, "url", ""), jar):
        raise RuntimeError("Chưa đăng nhập xong. Hãy chạy lại và đăng nhập trên cửa sổ Chrome của Shopee.")
    write_curl_cookies(curl_file, jar)
    print("[+] Đã lưu cookie đăng nhập mới.")
    page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
    if not affiliate_session_ready(page.url, browser_cookies(context)):
        raise RuntimeError("Đăng nhập xong nhưng Shopee vẫn yêu cầu đăng nhập.")


def _rate_number(text: str) -> float:
    raw = str(text or "").strip().replace("%", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def display_commission(item: Dict[str, Any]) -> str:
    """Hoa hồng hiển thị. Mục xu hướng để max_commission_rate = 0% và ghi tỷ lệ thật ở seller/default."""
    max_rate = str(item.get("max_commission_rate") or "").strip()
    seller = str(item.get("seller_commission_rate") or "").strip()
    default = str(item.get("default_commission_rate") or "").strip()
    for candidate in (max_rate, seller, default):
        if _rate_number(candidate) > 0:
            return candidate
    return max_rate or seller or default


def parse_curl_command(curl_text: str) -> Dict[str, Any]:
    """Phân tích lệnh curl để lấy url, method, headers, cookies, body data."""
    result: Dict[str, Any] = {
        "url": "",
        "method": "GET",
        "headers": {},
        "cookies": {},
        "data": None,
    }

    # Bỏ tiền tố curl: nếu có
    if curl_text.strip().startswith("curl:"):
        curl_text = curl_text.strip()[5:].strip()

    # Tìm URL
    url_m = re.search(r"--url\s+['\"]([^'\"]+)['\"]", curl_text) or re.search(r"curl\s+['\"]([^'\"]+)['\"]", curl_text)
    if url_m:
        result["url"] = url_m.group(1)

    # Tìm các Header (-H 'Key: Value')
    for hm in re.finditer(r"-H\s+['\"]([^'\"]+?)['\"]", curl_text):
        h_line = hm.group(1)
        if ":" in h_line:
            k, v = h_line.split(":", 1)
            result["headers"][k.strip()] = v.strip()

    # Tìm Cookies (-b '...')
    cookie_m = re.search(r"-b\s+['\"]([^'\"]+?)['\"]", curl_text)
    if cookie_m:
        cookie_raw = cookie_m.group(1)
        for part in cookie_raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                result["cookies"][k.strip()] = v.strip()

    # Tìm POST data (--data-raw $'...' hoặc --data-raw '...' hoặc -d '...')
    data_m = re.search(r"(?:--data-raw|-d)\s+\$?['\"](\{.*?\})['\"]", curl_text, re.DOTALL)
    if data_m:
        raw_payload = data_m.group(1)
        # unescape ký tự nếu là chuỗi $''
        raw_payload = raw_payload.encode("utf-8").decode("unicode_escape", errors="ignore")
        result["method"] = "POST"
        try:
            result["data"] = json.loads(raw_payload)
        except Exception:
            result["data"] = raw_payload

    return result


def read_response_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Đọc và parse phần JSON response từ file chứa curl và response."""
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Tách phần response:
    if "response:\n" in content:
        json_part = content.split("response:\n", 1)[1].strip()
    elif "response:" in content:
        json_part = content.split("response:", 1)[1].strip()
    else:
        json_part = content.strip()

    try:
        return json.loads(json_part)
    except json.JSONDecodeError as e:
        print(f"[Cảnh báo] Không thể parse JSON từ {file_path}: {e}")
        return None


def fetch_product_list_pages(
    curl_file: str,
    max_pages: int = 25,
    offer: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Mở trang chi tiết ưu đãi bằng trình duyệt và lật từng trang danh sách sản phẩm.

    Chữ ký chống bot của Shopee gắn với đúng URL, nên không đổi page_offset rồi gọi lại
    bằng requests. Trình duyệt tự ký từng request khi bấm trang tiếp theo.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Thiếu playwright. Chạy ./scripts/ubuntu/setup.sh trước khi lấy nhiều trang.") from e

    with open(curl_file, "r", encoding="utf-8") as f:
        curl_content = f.read().split("response:")[0]
    curl_info = parse_curl_command(curl_content)
    page_url = offer_page_url(curl_info)

    cookies = [
        {"name": k, "value": v, "domain": ".shopee.vn", "path": "/"}
        for k, v in curl_info.get("cookies", {}).items()
    ]
    pages: List[Dict[str, Any]] = []
    seen_offsets = set()
    if offer and str(offer.get("list_type") or "") != "":
        want_list = str(offer.get("list_type"))
        want_match = str(offer.get("match_id") or "")
        tab_labels = (offer["name"], *_OFFER_ALIASES.get(offer["id"], ()))
    else:
        want_list = _query_value(curl_info.get("url") or "", "list_type")
        want_match = _query_value(curl_info.get("url") or "", "match_id")
        tab_labels = _LIST_TABS.get(want_list) or ()
    pager = ".PaginationNoTotal__wrap .page-next, [class*='page-next'], .ant-pagination-next"

    def on_response(resp):
        if "offer/product/list" not in resp.url or resp.status != 200:
            return
        if want_list and _query_value(resp.url, "list_type") != want_list:
            return
        if want_match and _query_value(resp.url, "match_id") != want_match:
            return
        try:
            body = resp.json()
        except Exception:
            return
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            err = body.get("error") if isinstance(body, dict) else None
            if err:
                print(f"[Cảnh báo] product/list không có danh sách, mã {err}")
            return
        offset = data.get("page_offset")
        if offset in seen_offsets:
            return
        seen_offsets.add(offset)
        pages.append(data)
        print(f"[+] Trang offset={offset}: {len(data['list'])} sản phẩm, tổng {data.get('total_count')}")

    def open_list_tab(page):
        labels = tab_labels
        if not labels:
            return
        pattern = re.compile("|".join(re.escape(label) for label in labels))
        tabs = page.locator(".category-tabs")
        tab = tabs.get_by_text(pattern).first
        try:
            tab.wait_for(timeout=30000)
        except Exception as exc:
            if is_login_url(page.url):
                raise AffiliateLoginRequired() from exc
            raise RuntimeError(f"Không thấy tab {labels[0]} trên trang sản phẩm.") from exc
        tab.click()

    with sync_playwright() as p:
        def new_context(browser):
            context_args = {"locale": "vi-VN", "viewport": {"width": 1400, "height": 900}}
            user_agent = curl_info.get("headers", {}).get("user-agent") or ""
            if user_agent:
                context_args["user_agent"] = user_agent
            context = browser.new_context(**context_args)
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            page.on("response", on_response)
            return context, page

        def sign_in(browser):
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            visible = _launch_chrome(p, visible=True)
            context, page = new_context(visible)
            _wait_for_shopee_login(page, context, curl_file, page_url)
            return visible, context, page

        browser = None
        try:
            needs_login = session_cookie_missing(curl_info.get("cookies") or {})
            signed_in = False
            if needs_login:
                browser, context, page = sign_in(None)
                signed_in = True
            else:
                print("[*] Mở Chrome ẩn để lấy danh sách.")
                browser = _launch_chrome(p, visible=False)
                context, page = new_context(browser)
                page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
                if not affiliate_session_ready(page.url, browser_cookies(context)):
                    browser, context, page = sign_in(browser)
                    signed_in = True
            while True:
                try:
                    if want_list:
                        open_list_tab(page)
                    try:
                        page.wait_for_selector(pager, timeout=30000)
                    except Exception as exc:
                        if not pages and is_login_url(page.url):
                            raise AffiliateLoginRequired() from exc
                        if not pages:
                            raise RuntimeError("Không thấy nút trang tiếp theo trên trang sản phẩm.") from exc
                    specific = page.locator(".PaginationNoTotal__wrap .page-next")
                    nxt = specific.first if specific.count() else page.locator(pager).first
                    stalled = 0
                    target_pages = max_pages
                    for _ in range(max(0, max_pages - 1)):
                        if pages:
                            first = pages[0]
                            target_pages = list_page_count(
                                int(first.get("total_count") or 0),
                                int(first.get("page_limit") or 20),
                                max_pages,
                            )
                        if len(pages) >= target_pages:
                            print(f"[*] Đã đủ {len(pages)} trang.")
                            break
                        # Bấm dồn dễ bị Shopee đẩy sang /verify/traffic và mất nút phân trang.
                        page.wait_for_timeout(3000)
                        if is_login_url(page.url):
                            raise AffiliateLoginRequired()
                        if "verify/traffic" in page.url:
                            print("[Cảnh báo] Shopee chặn vì lật trang quá nhanh, dừng với các trang đã lấy.")
                            break
                        try:
                            cls = nxt.get_attribute("class", timeout=8000) or ""
                        except Exception as exc:
                            stalled += 1
                            print(f"[Cảnh báo] Không thấy nút trang tiếp theo ({stalled}): {exc}")
                            if stalled >= 3:
                                break
                            continue
                        if "disabled" in cls:
                            print("[*] Hết trang.")
                            break
                        before = len(pages)
                        nxt.scroll_into_view_if_needed()
                        try:
                            with page.expect_response(
                                lambda r: "offer/product/list" in r.url and r.status == 200,
                                timeout=20000,
                            ):
                                nxt.click()
                        except Exception as e:
                            stalled += 1
                            print(f"[Cảnh báo] Không nhận được trang mới ({stalled}): {e}")
                            if stalled >= 3:
                                break
                            continue
                        if len(pages) == before:
                            stalled += 1
                            if stalled >= 3:
                                print("[Cảnh báo] Bấm tiếp 3 lần mà không có sản phẩm mới, dừng.")
                                break
                        else:
                            stalled = 0
                    break
                except AffiliateLoginRequired:
                    if signed_in:
                        raise RuntimeError(
                            "Đăng nhập xong nhưng Shopee vẫn yêu cầu đăng nhập."
                        )
                    signed_in = True
                    pages.clear()
                    seen_offsets.clear()
                    browser, context, page = sign_in(browser)
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    merged: List[Dict[str, Any]] = []
    seen_ids = set()
    total = None
    for data in pages:
        total = data.get("total_count", total)
        for item in data.get("list") or []:
            iid = str(item.get("item_id") or "")
            if not iid or iid in seen_ids:
                continue
            seen_ids.add(iid)
            merged.append(item)
    print(f"[+] Gộp {len(merged)} sản phẩm (API báo tổng {total}).")
    return {"data": {"list": merged, "total_count": total}}


def extract_products(
    product_json: Dict[str, Any],
    category_id: str = "",
    category_name: str = "",
) -> List[Dict[str, Any]]:
    """Trích xuất danh sách sản phẩm chuẩn hóa từ response API 1."""
    products_raw = []
    if isinstance(product_json, dict):
        if "data" in product_json and isinstance(product_json["data"], dict):
            products_raw = product_json["data"].get("list", [])
        elif "list" in product_json:
            products_raw = product_json["list"]

    clean_products = []
    for item in products_raw:
        if not isinstance(item, dict):
            continue
        item_card = item.get("batch_item_for_item_card_full") or {}
        if not isinstance(item_card, dict):
            item_card = {}

        item_id = str(item.get("item_id") or item_card.get("itemid") or "")
        shop_id = str(item_card.get("shopid") or "")
        name = item_card.get("name") or item.get("name") or ""
        # Chuẩn hóa khoảng trắng thừa trong tên sản phẩm
        name = re.sub(r"\s+", " ", name).strip()

        # Giá sản phẩm (Shopee nhân 100,000 cho VND)
        price_raw_str = str(item_card.get("price") or "0")
        try:
            price_raw = int(price_raw_str)
            price = int(price_raw / 100000) if price_raw > 100000 else price_raw
        except ValueError:
            price = 0

        price_formatted = f"{price:,} ₫".replace(",", ".") if price > 0 else ""

        # Lấy link video nếu có
        video_url = None
        video_list = item_card.get("video_info_list") or []
        if isinstance(video_list, list) and video_list and isinstance(video_list[0], dict):
            first_vid = video_list[0]
            # Ưu tiên format chất lượng cao
            formats = first_vid.get("formats", [])
            if formats and isinstance(formats, list) and isinstance(formats[0], dict):
                video_url = formats[0].get("url")
            if not video_url:
                default_format = first_vid.get("default_format") or {}
                if isinstance(default_format, dict):
                    video_url = default_format.get("url")
                if not video_url:
                    video_url = first_vid.get("url")

        # Ảnh sản phẩm
        img_id = item_card.get("image", "")
        img_url = f"https://down-vn.img.susercontent.com/file/{img_id}" if img_id else ""

        clean_item = {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": name,
            "short_link": None,  # Sẽ được cập nhật từ API 2
            "long_link": item.get("long_link", ""),
            "product_link": item.get("product_link") or f"https://shopee.vn/product/{shop_id}/{item_id}",
            "price": price,
            "price_formatted": price_formatted,
            "commission_rate": display_commission(item),
            "seller_commission_rate": item.get("seller_commission_rate", ""),
            "shop_name": item_card.get("shop_name", ""),
            "shop_rating": round(float(item_card.get("shop_rating") or 0), 2),
            "sold": item_card.get("sold", 0),
            "historical_sold": item_card.get("historical_sold", 0),
            "rating_star": (item_card.get("item_rating") or {}).get("rating_star", 0)
            if isinstance(item_card.get("item_rating"), dict) else 0,
            "image_url": img_url,
            "video_url": video_url,
            "trace": item.get("trace", ""),
            "category_id": str(category_id or ""),
            "category_name": category_name or "",
        }
        clean_products.append(clean_item)

    return clean_products


def extract_offer_links(links_json: Dict[str, Any]) -> Dict[str, str]:
    """Trích xuất mapping {itemId: productOfferLink} từ response API 2."""
    mapping: Dict[str, str] = {}
    if not links_json or not isinstance(links_json, dict):
        return mapping

    data_block = links_json.get("data", {})
    link_list = data_block.get("productOfferLinks", [])
    for it in link_list:
        iid = str(it.get("itemId", ""))
        link = it.get("productOfferLink", "")
        if iid and link:
            mapping[iid] = link
    return mapping


def merge_products_and_links(
    products: List[Dict[str, Any]],
    offer_links: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Gán short_link vào danh sách sản phẩm theo itemId."""
    for p in products:
        iid = p["item_id"]
        if iid in offer_links:
            p["short_link"] = offer_links[iid]
    return products


def media_key(product: Dict[str, Any]) -> str:
    """Tên file/thư mục: shopId_itemId, trùng quy ước file video khi đăng Facebook."""
    shop = str(product.get("shop_id") or "0")
    item = str(product.get("item_id") or "0")
    return f"{shop}_{item}"


def affiliate_media_root() -> str:
    path = os.path.join(data_dir(), "affiliate")
    os.makedirs(path, exist_ok=True)
    return path


def _rel_data(path: str) -> str:
    return os.path.relpath(path, data_dir()).replace("\\", "/")


def _existing_file(folder: str, key: str, exts: Tuple[str, ...]) -> Optional[str]:
    for ext in exts:
        path = os.path.join(folder, key + ext)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    return None


def _download_http(url: str, dest: str) -> None:
    """Tải file thường (.jpg / .mp4) qua HTTP, ghi .part rồi đổi tên khi xong."""
    if not requests:
        raise RuntimeError("Cần thư viện 'requests' để tải ảnh và video.")
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://shopee.vn/",
    }
    try:
        with requests.get(url, stream=True, timeout=60, headers=headers) as resp:
            if resp.status_code in (401, 403):
                raise RuntimeError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)
        if not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            raise RuntimeError("File tải về bị rỗng")
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _image_ext(url: str, content_type: str) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    by_type = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if ctype in by_type:
        return by_type[ctype]
    path = url.split("?")[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def _download_image(url: str, folder: str, key: str) -> str:
    """Tải ảnh, chọn đuôi theo Content-Type. Trả về đường dẫn file đã lưu."""
    if not requests:
        raise RuntimeError("Cần thư viện 'requests' để tải ảnh và video.")
    os.makedirs(folder, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://shopee.vn/",
    }
    tmp = os.path.join(folder, key + ".part")
    try:
        with requests.get(url, stream=True, timeout=60, headers=headers) as resp:
            if resp.status_code in (401, 403):
                raise RuntimeError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            ext = _image_ext(url, resp.headers.get("content-type", ""))
            dest = os.path.join(folder, key + ext)
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        if not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            raise RuntimeError("Ảnh tải về bị rỗng")
        os.replace(tmp, dest)
        return dest
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


class _QuietDownload:
    def cancelled(self) -> bool:
        return False

    def check(self) -> None:
        return None


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _media_file(product: Dict[str, Any], field: str, exts: Tuple[str, ...]) -> Optional[str]:
    """File ảnh hoặc video đã nằm trong data/. Đường dẫn ghi trong JSON mà mất file thì coi như chưa có."""
    rel = str(product.get(field) or "").replace("\\", "/").strip()
    if rel and not rel.startswith("/") and ".." not in rel.split("/"):
        path = os.path.join(data_dir(), rel)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    key = media_key(product)
    return _existing_file(os.path.join(affiliate_media_root(), key), key, exts)


def product_in_offer(product: Dict[str, Any], offer: Dict[str, str]) -> bool:
    """Sản phẩm thuộc mục đang chọn, kể cả tên cũ còn lưu trong JSON."""
    category_id, category_name = canonical_category(
        str(product.get("category_name") or ""),
        str(product.get("category_id") or ""),
    )
    return category_id == offer["id"] or category_name == offer["name"]


def product_needs_media(product: Dict[str, Any]) -> bool:
    """Còn ảnh hoặc video trên Shopee mà máy chưa có file để hiện lên bảng."""
    if product.get("image_url") and not _media_file(product, "image_file", _IMAGE_EXTS):
        return True
    if product.get("video_url") and not _media_file(product, "video_file", (".mp4",)):
        return True
    return False


def download_product_media(
    products: List[Dict[str, Any]],
    limit: int = 0,
    on_item=None,
    only: str = "",
) -> List[Dict[str, Any]]:
    """Tải ảnh và video vào data/affiliate/{shopId}_{itemId}/.

    Tên file trùng mã shop và mã sản phẩm để cột File video của Facebook
    trỏ đúng một file: affiliate/{shop}_{item}/{shop}_{item}.mp4
    """
    try:
        from .shopee import ShopeeError, download_file
    except (ImportError, ValueError):
        root_pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root_pkg not in sys.path:
            sys.path.insert(0, root_pkg)
        from shopeetool.shopee import ShopeeError, download_file

    root = affiliate_media_root()
    todo = products if limit <= 0 else products[:max(0, limit)]
    ctx = _QuietDownload()
    n_img = n_vid = n_skip = n_fail = 0
    for i, product in enumerate(todo, 1):
        key = media_key(product)
        folder = os.path.join(root, key)
        os.makedirs(folder, exist_ok=True)
        label = f"[{i}/{len(todo)}] {key}"

        image_url = product.get("image_url") or ""
        if only == "video":
            pass
        elif image_url:
            found = _existing_file(folder, key, _IMAGE_EXTS)
            if found:
                product["image_file"] = _rel_data(found)
                n_skip += 1
            else:
                try:
                    saved = _download_image(image_url, folder, key)
                    product["image_file"] = _rel_data(saved)
                    n_img += 1
                    print(f"{label} ảnh -> {product['image_file']}")
                except Exception as e:
                    if not _media_file(product, "image_file", _IMAGE_EXTS):
                        product["image_file"] = None
                    n_fail += 1
                    print(f"[Cảnh báo] {label} không tải được ảnh: {e}")
        elif not _media_file(product, "image_file", _IMAGE_EXTS):
            product["image_file"] = None

        video_url = product.get("video_url") or ""
        video_dest = os.path.join(folder, key + ".mp4")
        if only == "image":
            pass
        elif video_url:
            if os.path.isfile(video_dest) and os.path.getsize(video_dest) > 0:
                product["video_file"] = _rel_data(video_dest)
                n_skip += 1
            else:
                try:
                    if ".m3u8" in video_url.split("?")[0].lower():
                        download_file(video_url, video_dest, ctx)
                    else:
                        _download_http(video_url, video_dest)
                    product["video_file"] = _rel_data(video_dest)
                    n_vid += 1
                    print(f"{label} video -> {product['video_file']}")
                except (ShopeeError, Exception) as e:
                    if not _media_file(product, "video_file", (".mp4",)):
                        product["video_file"] = None
                    n_fail += 1
                    print(f"[Cảnh báo] {label} không tải được video: {e}")
        elif not _media_file(product, "video_file", (".mp4",)):
            product["video_file"] = None
            print(f"{label} không có video")
        if on_item:
            on_item(i, len(todo), product)

    print(
        f"[+] Ảnh mới: {n_img} | Video mới: {n_vid} | "
        f"Đã có sẵn: {n_skip} | Lỗi: {n_fail}"
    )
    return products


def fill_missing_category(
    products: List[Dict[str, Any]],
    category_id: str = "100636",
    category_name: str = "Nhà Cửa & Đời Sống",
) -> None:
    """Sản phẩm lấy trước khi có mục thì gán về Nhà Cửa & Đời Sống."""
    for product in products:
        if str(product.get("category_id") or "").strip() or str(product.get("category_name") or "").strip():
            continue
        product["category_id"] = category_id
        product["category_name"] = category_name


def merge_product_lists(
    saved: List[Dict[str, Any]],
    fresh: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Ghép sản phẩm mới vào danh sách đã lưu. Giữ link, ảnh, video và trạng thái Facebook."""
    index: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for product in saved:
        iid = str(product.get("item_id") or "")
        if not iid or iid in index:
            continue
        index[iid] = product
        order.append(iid)
    added = 0
    for item in fresh:
        iid = str(item.get("item_id") or "")
        if not iid:
            continue
        old = index.get(iid)
        if old is None:
            index[iid] = item
            order.append(iid)
            added += 1
            continue
        for key, value in item.items():
            if key in ("category_id", "category_name") and old.get(key):
                continue
            if key in _KEEP_ON_MERGE and old.get(key) not in (None, "", [], {}):
                continue
            if value not in (None, ""):
                old[key] = value
    return [index[iid] for iid in order], added


def read_offer_snapshot(curl_file: str, offer: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Đọc JSON đã lưu. File curl xu hướng không nhúng response, nên đọc file kế bên."""
    response_name = str(offer.get("response_file") or "")
    if response_name:
        path = response_name if os.path.isabs(response_name) else os.path.join(
            os.path.dirname(os.path.abspath(curl_file)), response_name
        )
        found = read_response_from_file(path)
        if found:
            return found
    return read_response_from_file(curl_file)


def load_saved_products(output_filename: str) -> Optional[List[Dict[str, Any]]]:
    """Đọc danh sách sản phẩm đã lưu trong data/*.json, nếu file còn dùng được."""
    if os.path.isabs(output_filename):
        path = output_filename
    else:
        path = os.path.join(data_dir(), output_filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    products = data.get("products") if isinstance(data, dict) else None
    if isinstance(products, list) and products:
        return products
    return None


def fetch_short_links_live(
    products: List[Dict[str, Any]],
    curl_file: str,
    batch_size: int = 20
) -> Dict[str, str]:
    """Gọi API 2 (GraphQL batchGetProductOfferLink) trực tiếp để lấy link rút gọn cho toàn bộ sản phẩm."""
    if not requests:
        print("[Lỗi] Cần thư viện 'requests' để gọi API trực tiếp.")
        return {}

    if not os.path.exists(curl_file):
        print(f"[Cảnh báo] Không tìm thấy file curl mẫu {curl_file}")
        return {}

    with open(curl_file, "r", encoding="utf-8") as f:
        curl_content = f.read().split("response:")[0]

    curl_info = parse_curl_command(curl_content)
    if session_cookie_missing(curl_info.get("cookies") or {}):
        print("[Lỗi] Cookie đăng nhập đã hết hạn. Hãy chạy cập nhật danh sách và đăng nhập trên cửa sổ Shopee.")
        return {}
    url = curl_info.get("url") or "https://affiliate.shopee.vn/api/v3/gql?q=productOfferLinks"
    headers = curl_info.get("headers", {})
    cookies = curl_info.get("cookies", {})

    all_offer_links: Dict[str, str] = {}

    # Chia nhóm để gọi batch
    for i in range(0, len(products), batch_size):
        chunk = products[i : i + batch_size]
        link_params = []
        for p in chunk:
            try:
                shop_id_int = int(p["shop_id"]) if p["shop_id"] else 0
            except ValueError:
                shop_id_int = 0

            link_params.append({
                "itemId": p["item_id"],
                "shopId": shop_id_int,
                "trace": p.get("trace", ""),
            })

        payload = {
            "operationName": "batchGetProductOfferLink",
            "query": (
                "\n      query batchGetProductOfferLink (\n"
                "        $sourceCaller: SourceCaller!\n"
                "        $productOfferLinkParams: [ProductOfferLinkParam!]!\n"
                "        $advancedLinkParams: AdvancedLinkParams\n"
                "      ){\n"
                "        productOfferLinks(\n"
                "          productOfferLinkParams: $productOfferLinkParams,\n"
                "          sourceCaller: $sourceCaller,\n"
                "          advancedLinkParams: $advancedLinkParams\n"
                "        ) {\n"
                "          itemId\n"
                "          shopId\n"
                "          productOfferLink\n"
                "        }\n"
                "      }\n      "
            ),
            "variables": {
                "productOfferLinkParams": link_params,
                "sourceCaller": "WEB_SITE_CALLER",
                "advancedLinkParams": {
                    "subId1": "",
                    "subId2": "",
                    "subId3": "",
                    "subId4": "",
                    "subId5": "",
                },
            },
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=15
            )
            if resp.status_code in (401, 403):
                print("[Lỗi] Cookie đăng nhập đã hết hạn. Hãy chạy cập nhật danh sách và đăng nhập trên cửa sổ Shopee.")
                break
            if resp.status_code == 200:
                res_data = resp.json()
                mapping = extract_offer_links(res_data)
                all_offer_links.update(mapping)
                print(f"[Thành công] Đã lấy được {len(mapping)} short link cho lô {i // batch_size + 1}")
            else:
                print(f"[Cảnh báo] Gọi API 2 thất bại: HTTP {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"[Lỗi] Gặp lỗi khi gọi API 2: {e}")

    return all_offer_links


def save_to_json(
    products: List[Dict[str, Any]],
    output_filename: str = "products_affiliate.json"
) -> str:
    """Lưu danh sách sản phẩm và link hoa hồng vào thư mục data/."""
    # Đảm bảo đường dẫn file nằm trong data_dir()
    if os.path.isabs(output_filename):
        dest_path = output_filename
    else:
        dest_path = os.path.join(data_dir(), output_filename)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    categories: Dict[str, int] = {}
    for product in products:
        label = str(product.get("category_name") or "Chưa phân loại")
        categories[label] = categories.get(label, 0) + 1

    summary = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_products": len(products),
        "total_with_short_link": sum(1 for p in products if p.get("short_link")),
        "total_with_image": sum(1 for p in products if p.get("image_file")),
        "total_with_video": sum(1 for p in products if p.get("video_file")),
        "categories": categories,
        "media_dir": "affiliate/{shop_id}_{item_id}/",
        "products": products,
    }

    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, dest_path)

    return dest_path


def product_offer_update_order() -> List[Dict[str, str]]:
    """Tab ngành hàng trước, Tất cả sau, để sản phẩm giữ mục cụ thể và không bị ghi đè."""
    specific: List[Dict[str, str]] = []
    everything: List[Dict[str, str]] = []
    legacy: List[Dict[str, str]] = []
    for offer in OFFERS:
        kind = str(offer.get("list_type") or "")
        if kind == "0":
            everything.append(offer)
        elif kind:
            specific.append(offer)
        else:
            legacy.append(offer)
    return specific + everything + legacy


def offers_for_catalog_update(offer_key: str) -> List[Dict[str, str]]:
    """Một mục đang chọn, hoặc mọi mục khi khóa là * . Chuỗi rỗng vẫn bị từ chối."""
    key = str(offer_key or "").strip()
    if not key:
        raise ValueError("Hãy chọn một mục trước khi cập nhật danh sách.")
    if key in {"*", "Mọi mục"}:
        return product_offer_update_order()
    return [offer_by_key(key)]


def _download_missing_media(
    products: List[Dict[str, Any]],
    offer: Dict[str, str],
    output_file: str,
    on_progress=None,
) -> Dict[str, int]:
    """Tải ảnh và video còn thiếu của đúng mục đang chọn, rồi ghi lại để bảng hiện file."""
    pending = [item for item in products if product_in_offer(item, offer) and product_needs_media(item)]
    stats = {"checked": len(pending), "images": 0, "videos": 0, "failed": 0}
    if not pending:
        return stats
    before = {
        str(item.get("item_id") or ""): (
            bool(_media_file(item, "image_file", _IMAGE_EXTS)),
            bool(_media_file(item, "video_file", (".mp4",))),
        )
        for item in pending
    }

    def _saved(label: str):
        def _tick(index: int, total: int, _product: Dict[str, Any]) -> None:
            if index == total or index % 5 == 0:
                save_to_json(products, output_file)
            if on_progress:
                on_progress(f"{offer['name']}: đang tải {label} {index}/{total}.")
        return _tick

    if on_progress:
        on_progress(f"{offer['name']}: {len(pending)} sản phẩm chưa có ảnh hoặc video.")
    download_product_media(pending, on_item=_saved("ảnh"), only="image")
    save_to_json(products, output_file)
    download_product_media(pending, on_item=_saved("video"), only="video")
    save_to_json(products, output_file)
    for item in pending:
        iid = str(item.get("item_id") or "")
        had_image, had_video = before.get(iid, (False, False))
        has_image = bool(_media_file(item, "image_file", _IMAGE_EXTS))
        has_video = bool(_media_file(item, "video_file", (".mp4",)))
        if not had_image and has_image:
            stats["images"] += 1
        if not had_video and has_video:
            stats["videos"] += 1
        if (item.get("image_url") and not has_image) or (item.get("video_url") and not has_video):
            stats["failed"] += 1
    return stats


def update_product_catalog(
    max_pages: int = 25,
    output_file: str = "products_affiliate.json",
    on_progress=None,
    offer_key: str = "",
) -> Dict[str, Any]:
    """Lấy mục đang chọn hoặc mọi mục, thêm sản phẩm chưa có, rồi tải ảnh và video còn thiếu."""
    offers = offers_for_catalog_update(offer_key)
    reports: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    added_total = 0
    images = videos = media_failed = 0
    latest: List[Dict[str, Any]] = load_saved_products(output_file) or []
    for offer in offers:
        if on_progress:
            on_progress(f"Đang kiểm tra ảnh và video của mục {offer['name']}...")
        ready = _download_missing_media(latest, offer, output_file, on_progress=on_progress)
        if on_progress:
            on_progress(f"Đang lấy mục {offer['name']}...")
        before = {str(item.get("item_id") or "") for item in latest if item.get("item_id")}
        try:
            latest, _path = get_affiliate_products(
                output_file=output_file,
                max_pages=max_pages,
                offer_id=offer["id"],
            )
        except Exception as exc:
            errors.append({"id": offer["id"], "name": offer["name"], "error": str(exc)})
        after = []
        seen = set()
        for item in latest:
            iid = str(item.get("item_id") or "")
            if not iid or iid in seen:
                continue
            seen.add(iid)
            after.append(item)
        if len(after) != len(latest):
            latest = after
            save_to_json(latest, output_file)
        gained = len(seen - before)
        added_total += gained
        media = _download_missing_media(latest, offer, output_file, on_progress=on_progress)
        got_images = ready["images"] + media["images"]
        got_videos = ready["videos"] + media["videos"]
        images += got_images
        videos += got_videos
        media_failed += ready["failed"] + media["failed"]
        reports.append({
            "id": offer["id"],
            "name": offer["name"],
            "added": gained,
            "total": len(seen),
            "images": got_images,
            "videos": got_videos,
        })
        if on_progress:
            on_progress(
                f"{offer['name']}: thêm {gained} sản phẩm mới, "
                f"tải {got_images} ảnh và {got_videos} video."
            )
    return {
        "added": added_total,
        "total": len(latest),
        "images": images,
        "videos": videos,
        "media_failed": media_failed,
        "offers": reports,
        "errors": errors,
    }


def get_affiliate_products(
    product_curl_file: Optional[str] = None,
    links_curl_file: Optional[str] = None,
    output_file: str = "products_affiliate.json",
    fetch_online: bool = False,
    max_pages: int = 0,
    download_media: bool = False,
    download_limit: int = 0,
    offer_id: str = "",
) -> Tuple[List[Dict[str, Any]], str]:
    """Hàm xử lý chính: trích xuất Tên sản phẩm & Link hoa hồng, lưu vào thư mục data/.

    Trả về (danh_sách_sản_phẩm, đường_dẫn_file_json).
    """
    offer = offer_by_key(offer_id) if str(offer_id or "").strip() else offer_by_key("100636")
    try:
        from .auth import workspace_api_dir
        api_dir = workspace_api_dir()
    except (ImportError, ValueError):
        api_dir = os.path.join(app_dir(), "api_shopee")
    if not product_curl_file:
        product_curl_file = os.path.join(api_dir, offer["page_file"])
    if not links_curl_file:
        links_curl_file = os.path.join(api_dir, offer["links_file"])
    category_id = offer["id"]
    category_name = offer["name"]

    saved = load_saved_products(output_file)
    if saved:
        fill_missing_category(saved)
    product_json = None
    products: Optional[List[Dict[str, Any]]] = None
    fresh: List[Dict[str, Any]] = []
    if max_pages > 0:
        print(f"[*] Mục {category_name}: lật tối đa {max_pages} trang trên trình duyệt...")
        product_json = fetch_product_list_pages(product_curl_file, max_pages=max_pages, offer=offer)
        fresh = extract_products(product_json, category_id, category_name)
        print(f"[+] Mục {category_name}: tìm thấy {len(fresh)} sản phẩm.")
        if saved:
            products, added = merge_product_lists(saved, fresh)
            print(f"[+] Thêm {added} sản phẩm mới. Tổng {len(products)}.")
        else:
            products = fresh
    elif saved:
        products = saved
        print(f"[*] Dùng {len(products)} sản phẩm đã lưu trong {output_file}.")
    if products is None and not product_json:
        print(f"[*] Đang đọc danh sách sản phẩm từ: {product_curl_file}")
        product_json = read_offer_snapshot(product_curl_file, offer)
    if products is None and not product_json:
        raise RuntimeError(f"Không thể đọc hoặc parse response từ {product_curl_file}")

    if products is None:
        products = extract_products(product_json, category_id, category_name)
        print(f"[+] Tìm thấy {len(products)} sản phẩm.")

    link_targets = fresh if fresh else products
    offer_links = {}
    if fetch_online:
        print("[*] Đang gửi request online để tạo link hoa hồng rút gọn s.shopee.vn...")
        offer_links = fetch_short_links_live(link_targets, links_curl_file)

    # Nếu không chạy online hoặc online không lấy đủ, dùng link từ file curl đã lưu.
    if not offer_links and os.path.exists(links_curl_file):
        print(f"[*] Đọc link hoa hồng rút gọn có sẵn từ: {links_curl_file}")
        links_json = read_response_from_file(links_curl_file)
        if links_json:
            offer_links = extract_offer_links(links_json)

    if offer_links:
        products = merge_products_and_links(products, offer_links)

    if download_media:
        scope = "toàn bộ" if download_limit <= 0 else f"{download_limit} sản phẩm đầu"
        print(f"[*] Tải ảnh và video ({scope}) vào data/affiliate/...")
        products = download_product_media(products, limit=download_limit)

    # Lưu vào file JSON trong folder data/
    out_path = save_to_json(products, output_file)
    print(f"[+] Đã lưu dữ liệu vào: {out_path}")

    return products, out_path


def main():
    parser = argparse.ArgumentParser(
        description="Lấy danh sách Tên sản phẩm và Link hoa hồng từ API Shopee Affiliate."
    )
    parser.add_argument(
        "--product-file",
        default=None,
        help="Đường dẫn tới file curl_product.txt (mặc định: api_shopee/curl_product.txt)"
    )
    parser.add_argument(
        "--links-file",
        default=None,
        help="Đường dẫn tới file curl_productOfferLinks.txt (mặc định: api_shopee/curl_productOfferLinks.txt)"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="products_affiliate.json",
        help="Tên file JSON lưu trong folder data/ (mặc định: products_affiliate.json)"
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Gửi request online lên Shopee GraphQL để lấy link rút gọn cho toàn bộ sản phẩm"
    )
    parser.add_argument(
        "--offer",
        default="",
        help="Mục trên trang hoa hồng: all (Tất cả), xtra (Hoa hồng Xtra), trend (Bán chạy nhất), 100636 (Nhà Cửa & Đời Sống), 100630 (Sắc Đẹp), 100629 (Bách Hóa Online), 100017 (Thời Trang Nữ), 100010 (Đồ gia dụng). Bỏ trống = Nhà Cửa & Đời Sống."
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        help="Số trang cần lật trên trình duyệt. Sản phẩm xu hướng mỗi trang 20, API báo tổng 500 nên 25 trang là hết. 0 = chỉ đọc file đã lưu."
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Tải ảnh và video vào data/affiliate/{shop_id}_{item_id}/"
    )
    parser.add_argument(
        "--download-limit",
        type=int,
        default=0,
        help="Chỉ tải N sản phẩm đầu. 0 = tải tất cả (dùng cùng --download)."
    )
    parser.add_argument(
        "--show",
        type=int,
        default=5,
        help="Số lượng sản phẩm in xem trước ra console (mặc định: 5)"
    )

    args = parser.parse_args()

    try:
        products, out_path = get_affiliate_products(
            product_curl_file=args.product_file,
            links_curl_file=args.links_file,
            output_file=args.output,
            fetch_online=args.online,
            max_pages=args.pages,
            download_media=args.download,
            download_limit=args.download_limit,
            offer_id=args.offer,
        )

        print("\n" + "=" * 80)
        print(f" TỔNG KẾT: {len(products)} SẢN PHẨM | FILE LƯU: {out_path}")
        print("=" * 80)

        show_count = min(args.show, len(products))
        for idx, p in enumerate(products[:show_count], 1):
            short = p.get("short_link") or "[Chưa có link rút gọn - Dùng long_link bên dưới]"
            print(f"[{idx}] {p['name']}")
            print(f"    - Mục: {p.get('category_name') or '(chưa có)'}")
            print(f"    - Giá bán: {p['price_formatted']} | Hoa hồng: {p['commission_rate']}")
            print(f"    - Link hoa hồng rút gọn: {short}")
            print(f"    - Link hoa hồng dài: {p['long_link'][:90]}...")
            if p.get("image_file") or p.get("video_file"):
                print(f"    - Ảnh: {p.get('image_file') or '(không có)'}")
                print(f"    - Video: {p.get('video_file') or '(không có)'}")
            print("-" * 80)

        if len(products) > show_count:
            print(f"... và {len(products) - show_count} sản phẩm khác (xem chi tiết trong {out_path})")

    except Exception as e:
        print(f"[Lỗi] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
