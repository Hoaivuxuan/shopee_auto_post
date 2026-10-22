"""Chuyển product_link thành short_link trên trang Custom Link của Shopee.

Trang https://affiliate.shopee.vn/offer/custom_link nhận tối đa 5 liên kết mỗi lần.
Chữ ký chống bot gắn với trình duyệt, nên gọi GraphQL batchGetCustomLink từ Chrome
đã đăng nhập, rồi gán short_link vào sản phẩm còn trống.
"""
import csv
import io
import os
import re
import zipfile
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse
from xml.sax.saxutils import escape

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_NAME = "Batch Custom Links.xlsx"
HEADERS = ("Liên kết gốc", "Sub_id1", "Sub_id2", "Sub_id3", "Sub_id4", "Sub_id5")
ORIGIN_HEADERS = {"liên kết gốc", "original link"}
SHORT_HEADERS = {"liên kết chuyển đổi", "short link", "converted link"}
FAIL_HEADERS = {"lí do thất bại", "lý do thất bại", "fail reason", "failure reason"}
_PRODUCT_RE = re.compile(r"/product/(\d+)/(\d+)")
_SEO_RE = re.compile(r"-i\.(\d+)\.(\d+)(?:$|[/?#])")


def missing_links(products: Sequence[dict]) -> List[str]:
    """Link gốc của sản phẩm chưa có short_link, giữ thứ tự, bỏ trùng."""
    seen = set()
    links = []
    for item in products:
        if not isinstance(item, dict) or _has_short(item):
            continue
        link = product_link_of(item)
        if not link or link in seen:
            continue
        seen.add(link)
        links.append(link)
    return links


def product_link_of(item: dict) -> str:
    raw = str(item.get("product_link") or "").strip()
    canonical = canonical_product_link(raw)
    if canonical:
        return canonical
    shop = str(item.get("shop_id") or "").strip()
    item_id = str(item.get("item_id") or "").strip()
    if shop.isdigit() and item_id.isdigit():
        return f"https://shopee.vn/product/{shop}/{item_id}"
    return ""


def canonical_product_link(value: str) -> str:
    pair = product_pair(value)
    if not pair:
        return ""
    return f"https://shopee.vn/product/{pair[0]}/{pair[1]}"


def product_pair(value: str) -> Optional[Tuple[str, str]]:
    text = (value or "").strip()
    if not text:
        return None
    match = _PRODUCT_RE.search(text) or _SEO_RE.search(text)
    if not match:
        return None
    return match.group(1), match.group(2)


def default_template() -> str:
    packaged = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "Batch Custom Links.xlsx")
    docs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "Batch Custom Links.xlsx")
    for path in (docs, packaged):
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("Thiếu file mẫu Batch Custom Links.xlsx")


def build_workbook(links: Sequence[str], template_path: str) -> bytes:
    if not links:
        raise ValueError("Không có link gốc để xuất")
    sheet = _sheet_xml(links)
    strings = _shared_strings_xml(links)
    if not os.path.isfile(template_path):
        raise FileNotFoundError("Thiếu file mẫu Batch Custom Links.xlsx")
    buf = io.BytesIO()
    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(buf, "w") as out:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                payload = sheet
            elif info.filename == "xl/sharedStrings.xml":
                payload = strings
            out.writestr(info, payload)
    return buf.getvalue()


def apply_csv(products: List[dict], raw: bytes) -> Dict[str, int]:
    """Gán short_link theo cột Liên kết chuyển đổi. Chỉ điền sản phẩm còn trống."""
    text = _decode_csv(raw)
    reader = _csv_reader(text)
    fields = [_header_key(name) for name in (reader.fieldnames or [])]
    if not any(name in ORIGIN_HEADERS for name in fields):
        raise ValueError("File CSV thiếu cột Liên kết gốc")
    if not any(name in SHORT_HEADERS for name in fields):
        raise ValueError("File CSV thiếu cột Liên kết chuyển đổi")

    by_pair: Dict[Tuple[str, str], List[dict]] = {}
    for item in products:
        if not isinstance(item, dict):
            continue
        pair = product_pair(product_link_of(item))
        if pair:
            by_pair.setdefault(pair, []).append(item)

    updated = skipped = failed = unmatched = empty = 0
    for row in reader:
        if not row or not any((value or "").strip() for value in row.values()):
            continue
        origin = _column(row, ORIGIN_HEADERS)
        short = _column(row, SHORT_HEADERS).strip()
        reason = _column(row, FAIL_HEADERS).strip()
        if not origin and not short and not reason:
            continue
        if reason or (short and not _valid_short(short)):
            failed += 1
            continue
        if not short:
            empty += 1
            continue
        pair = product_pair(origin)
        targets = by_pair.get(pair or ("", "")) or []
        if not targets:
            unmatched += 1
            continue
        for item in targets:
            if _has_short(item):
                skipped += 1
                continue
            item["short_link"] = _valid_short(short)
            updated += 1
    return {
        "updated": updated,
        "skipped_existing": skipped,
        "failed": failed,
        "unmatched": unmatched,
        "empty": empty,
    }


CUSTOM_PAGE = "https://affiliate.shopee.vn/offer/custom_link"
CUSTOM_BATCH = 5


def parse_custom_link_response(originals: Sequence[str], body: dict) -> List[dict]:
    """Đọc batchCustomLink theo đúng thứ tự link đã gửi."""
    data = body.get("data") if isinstance(body, dict) else None
    items = data.get("batchCustomLink") if isinstance(data, dict) else None
    if not isinstance(items, list):
        code = body.get("error") if isinstance(body, dict) else ""
        raise RuntimeError(
            f"Shopee từ chối chuyển link{f' (mã {code})' if code else ''}. "
            "Hãy chạy cập nhật danh sách và đăng nhập trên cửa sổ Shopee."
        )
    rows = []
    for origin, item in zip(originals, items):
        item = item if isinstance(item, dict) else {}
        try:
            fail_code = int(item.get("failCode") or 0)
        except (TypeError, ValueError):
            fail_code = 1
        rows.append({
            "original_link": origin,
            "short_link": str(item.get("shortLink") or ""),
            "long_link": str(item.get("longLink") or ""),
            "fail_code": fail_code,
        })
    for origin in list(originals)[len(items):]:
        rows.append({
            "original_link": origin,
            "short_link": "",
            "long_link": "",
            "fail_code": 1,
        })
    return rows


def apply_custom_rows(products: List[dict], rows: Sequence[dict]) -> Dict[str, int]:
    """Gán short_link theo kết quả Custom Link. Chỉ điền sản phẩm còn trống."""
    by_pair: Dict[Tuple[str, str], List[dict]] = {}
    for item in products:
        if not isinstance(item, dict):
            continue
        pair = product_pair(product_link_of(item))
        if pair:
            by_pair.setdefault(pair, []).append(item)

    updated = skipped = failed = unmatched = 0
    for row in rows:
        if not isinstance(row, dict):
            failed += 1
            continue
        short = _http_url(str(row.get("short_link") or ""), 500)
        long_link = _http_url(str(row.get("long_link") or ""), 8000)
        try:
            fail_code = int(row.get("fail_code") or 0)
        except (TypeError, ValueError):
            fail_code = 1
        if fail_code or not short:
            failed += 1
            continue
        targets = by_pair.get(product_pair(str(row.get("original_link") or "")) or ("", "")) or []
        if not targets:
            unmatched += 1
            continue
        for item in targets:
            if _has_short(item):
                skipped += 1
                continue
            item["short_link"] = short
            if long_link and not str(item.get("long_link") or "").strip():
                item["long_link"] = long_link
            updated += 1
    return {
        "updated": updated,
        "skipped_existing": skipped,
        "failed": failed,
        "unmatched": unmatched,
    }


def fetch_custom_link_rows(links: Sequence[str], on_batch=None, batch_size: int = CUSTOM_BATCH) -> List[dict]:
    """Mở Custom Link, gửi từng lô và trả short_link theo thứ tự link gốc."""
    pending = [link for link in links if link]
    if not pending:
        return []
    size = max(1, min(int(batch_size or CUSTOM_BATCH), CUSTOM_BATCH))
    aff = _affiliate()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Thiếu playwright. Chạy ./scripts/ubuntu/setup.sh trước khi tạo link rút gọn.") from exc

    session = _browser_session(aff)
    cookies = [
        {"name": key, "value": value, "domain": ".shopee.vn", "path": "/"}
        for key, value in (session.get("cookies") or {}).items()
        if key and value
    ]
    found: List[dict] = []
    with sync_playwright() as playwright:
        browser = aff._launch_chrome(playwright, visible=False)
        try:
            context_args = {"locale": "vi-VN", "viewport": {"width": 1400, "height": 900}}
            user_agent = (session.get("headers") or {}).get("user-agent") or ""
            if user_agent:
                context_args["user_agent"] = user_agent
            context = browser.new_context(**context_args)
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            page.goto(CUSTOM_PAGE, wait_until="domcontentloaded", timeout=60000)
            if aff.is_login_url(page.url) or not aff.affiliate_session_ready(page.url, aff.browser_cookies(context)):
                raise RuntimeError(
                    "Cookie đăng nhập đã hết hạn. Hãy chạy cập nhật danh sách và đăng nhập trên cửa sổ Shopee."
                )
            page.wait_for_selector("textarea.ant-input", timeout=30000)
            done = 0
            for start in range(0, len(pending), size):
                chunk = pending[start:start + size]
                body = _submit_custom_batch(page, chunk)
                rows = parse_custom_link_response(chunk, body)
                found.extend(rows)
                done += len(chunk)
                if on_batch:
                    on_batch(done, len(pending), rows)
                _dismiss_result_modal(page)
                if done < len(pending):
                    page.wait_for_timeout(800)
        finally:
            browser.close()
    return found


def _affiliate():
    try:
        from . import shopee_affiliate as mod
    except (ImportError, ValueError):
        from shopeetool import shopee_affiliate as mod
    return mod


def _browser_session(aff) -> dict:
    api_dir = os.path.join(aff.app_dir(), "api_shopee")
    best = None
    best_mtime = -1.0
    if os.path.isdir(api_dir):
        for name in os.listdir(api_dir):
            if not name.startswith("curl_") or not name.endswith(".txt"):
                continue
            path = os.path.join(api_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read().split("response:")[0]
                info = aff.parse_curl_command(text)
            except OSError:
                continue
            if aff.session_cookie_missing(info.get("cookies") or {}):
                continue
            mtime = os.path.getmtime(path)
            if mtime >= best_mtime:
                best = info
                best_mtime = mtime
    if not best:
        raise RuntimeError(
            "Cookie đăng nhập đã hết hạn. Hãy chạy cập nhật danh sách và đăng nhập trên cửa sổ Shopee."
        )
    return best


def _submit_custom_batch(page, links: Sequence[str]) -> dict:
    page.locator("textarea.ant-input").fill("\n".join(links))
    with page.expect_response(lambda response: "q=batchCustomLink" in response.url, timeout=30000) as caught:
        page.get_by_role("button", name="Lấy link").click()
    try:
        body = caught.value.json()
    except Exception as exc:
        raise RuntimeError("Shopee không trả kết quả chuyển link.") from exc
    if not isinstance(body, dict):
        raise RuntimeError("Shopee không trả kết quả chuyển link.")
    return body


def _dismiss_result_modal(page) -> None:
    modal = page.locator(".ant-modal-wrap")
    try:
        modal.first.wait_for(state="visible", timeout=3000)
    except Exception:
        return
    close = modal.get_by_role("button", name="Close")
    if close.count():
        close.first.click()
    else:
        page.keyboard.press("Escape")
    try:
        modal.first.wait_for(state="hidden", timeout=5000)
    except Exception:
        page.keyboard.press("Escape")


def _has_short(item: dict) -> bool:
    return bool(str(item.get("short_link") or "").strip())


def _valid_short(value: str) -> str:
    return _http_url(value, 500)


def _http_url(value: str, limit: int) -> str:
    value = (value or "").strip()
    if not value or len(value) > limit or any(ch.isspace() for ch in value):
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return value


def _decode_csv(raw: bytes) -> str:
    if raw.startswith(b"PK"):
        raise ValueError("Hãy chọn file CSV Shopee xuất ra sau khi chuyển đổi")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _csv_reader(text: str) -> csv.DictReader:
    first = text.splitlines()[0] if text else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return csv.DictReader(io.StringIO(text), delimiter=delimiter)


def _header_key(value: str) -> str:
    return (value or "").replace("\ufeff", "").strip().lower()


def _column(row: dict, names: set) -> str:
    for key, value in row.items():
        if _header_key(key) in names:
            return value or ""
    return ""


def _shared_strings_xml(links: Sequence[str]) -> bytes:
    values = list(HEADERS) + list(links)
    parts = ["<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"]
    count = len(values)
    parts.append(
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{count}" uniqueCount="{count}">'
    )
    for value in values:
        parts.append(f"<si><t>{escape(value)}</t></si>")
    parts.append("</sst>")
    return "".join(parts).encode("utf-8")


def _sheet_xml(links: Sequence[str]) -> bytes:
    last = len(links) + 1
    rows = [_header_row()]
    for offset, _link in enumerate(links, start=2):
        index = len(HEADERS) + (offset - 2)
        rows.append(f'<row r="{offset}" spans="1:6"><c r="A{offset}" t="s"><v>{index}</v></c></row>')
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        '<sheetPr><outlinePr summaryBelow="0" summaryRight="0"/></sheetPr>'
        f'<dimension ref="A1:F{last}"/>'
        '<sheetViews><sheetView tabSelected="1" workbookViewId="0">'
        '<selection activeCell="A1" sqref="A1"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultColWidth="12.6339285714286" defaultRowHeight="15.75" customHeight="1" outlineLevelCol="5"/>'
        '<cols><col min="1" max="1" width="62" customWidth="1"/>'
        '<col min="2" max="6" width="20.1339285714286" customWidth="1"/></cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '<pageMargins left="0.75" right="0.75" top="1" bottom="1" header="0.511805555555556" footer="0.511805555555556"/>'
        '<headerFooter/></worksheet>'
    )
    return body.encode("utf-8")


def _header_row() -> str:
    cells = []
    for index, column in enumerate("ABCDEF"):
        style = "1" if column == "A" else "2"
        cells.append(f'<c r="{column}1" s="{style}" t="s"><v>{index}</v></c>')
    return f'<row r="1" spans="1:6">{"".join(cells)}</row>'
