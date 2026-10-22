"""Xuất Excel Custom Link và nhập CSV link rút gọn của Shopee."""
import io
import json
import os
import sys
import tempfile
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool import admin_web, paths, short_link_batch  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "docs", "Batch Custom Links.xlsx")
SAMPLE = os.path.join(ROOT, "docs", "AffiliateBatchCustomLinks202610150915.csv")


def _strings(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [node.text or "" for node in root.findall("m:si/m:t", NS)]


def test_workbook_matches_template_columns():
    links = [
        "https://shopee.vn/product/1801449736/56560510283",
        "https://shopee.vn/product/1/2",
    ]
    blob = short_link_batch.build_workbook(links, TEMPLATE)
    values = _strings(blob)
    assert values[:6] == list(short_link_batch.HEADERS)
    assert values[6:] == links
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall("m:sheetData/m:row", NS)
    assert len(rows) == 3
    header = [cell.find("m:v", NS).text for cell in rows[0].findall("m:c", NS)]
    assert header == ["0", "1", "2", "3", "4", "5"]


def test_import_sample_csv_fills_only_missing_links():
    products = [
        {
            "item_id": "56560510283",
            "shop_id": "1801449736",
            "product_link": "https://shopee.vn/product/1801449736/56560510283",
            "short_link": None,
        },
        {
            "item_id": "1",
            "shop_id": "2",
            "product_link": "https://shopee.vn/product/2/1",
            "short_link": "https://s.shopee.vn/already",
        },
    ]
    raw = open(SAMPLE, "rb").read()
    extra = (
        "\nhttps://shopee.vn/product/2/1,,,,,,https://s.shopee.vn/new,"
        "\nhttps://shopee.vn/product/9/9,,,,,,,"
        "\nhttps://shopee.vn/product/8/8,,,,,,,link hỏng"
        "\nhttps://shopee.vn/product/7/7,,,,,,không phải url,"
    )
    result = short_link_batch.apply_csv(products, raw + extra.encode("utf-8"))
    assert products[0]["short_link"] == "https://s.shopee.vn/6fi4IWQPnD"
    assert products[1]["short_link"] == "https://s.shopee.vn/already"
    assert result["updated"] == 1
    assert result["skipped_existing"] == 1
    assert result["empty"] == 1
    assert result["failed"] == 2
    assert result["unmatched"] == 0


def test_parse_and_apply_custom_link_response():
    products = [
        {
            "item_id": "56560510283",
            "shop_id": "1801449736",
            "product_link": "https://shopee.vn/product/1801449736/56560510283",
            "short_link": "",
            "long_link": "",
        },
        {
            "item_id": "1",
            "shop_id": "2",
            "product_link": "https://shopee.vn/product/2/1",
            "short_link": "https://s.shopee.vn/already",
        },
    ]
    rows = short_link_batch.parse_custom_link_response(
        [
            "https://shopee.vn/product/1801449736/56560510283",
            "https://shopee.vn/product/2/1",
            "https://shopee.vn/product/9/9",
        ],
        {
            "data": {
                "batchCustomLink": [
                    {"shortLink": "https://s.shopee.vn/new", "longLink": "https://shopee.vn/universal-link/x", "failCode": 0},
                    {"shortLink": "https://s.shopee.vn/other", "longLink": "", "failCode": 0},
                    {"shortLink": "", "longLink": "", "failCode": 2},
                ]
            }
        },
    )
    result = short_link_batch.apply_custom_rows(products, rows)
    assert products[0]["short_link"] == "https://s.shopee.vn/new"
    assert products[0]["long_link"] == "https://shopee.vn/universal-link/x"
    assert products[1]["short_link"] == "https://s.shopee.vn/already"
    assert result["updated"] == 1
    assert result["skipped_existing"] == 1
    assert result["failed"] == 1
    assert result["unmatched"] == 0


def test_generate_job_fills_catalog_without_browser():
    folder = tempfile.mkdtemp(prefix="short-link-live-")
    catalog = {
        "updated_at": "",
        "products": [
            {
                "item_id": "56560510283",
                "shop_id": "1801449736",
                "product_link": "https://shopee.vn/product/1801449736/56560510283",
                "short_link": "",
            }
        ],
    }
    with open(os.path.join(folder, "products_affiliate.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f)
    paths._DATA_DIR = folder
    admin_web._LINK.update(status="idle", message="", updated=0, failed=0, total=0, done=0)

    def fake(links, on_batch=None, batch_size=5):
        rows = [{
            "original_link": links[0],
            "short_link": "https://s.shopee.vn/auto",
            "long_link": "",
            "fail_code": 0,
        }]
        if on_batch:
            on_batch(1, 1, rows)
        return rows

    original = short_link_batch.fetch_custom_link_rows
    short_link_batch.fetch_custom_link_rows = fake
    server = ThreadingHTTPServer(("127.0.0.1", 0), admin_web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        req = Request(
            f"http://127.0.0.1:{port}/api/short-link/generate",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req) as res:
            started = json.loads(res.read().decode("utf-8"))
        assert started["ok"] is True
        payload = {"status": "running"}
        for _ in range(50):
            with urlopen(f"http://127.0.0.1:{port}/api/short-link/generate") as res:
                payload = json.loads(res.read().decode("utf-8"))
            if payload["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert payload["status"] == "done", payload
        assert payload["updated"] == 1
        saved = json.load(open(os.path.join(folder, "products_affiliate.json"), encoding="utf-8"))
        assert saved["products"][0]["short_link"] == "https://s.shopee.vn/auto"
        assert saved["total_with_short_link"] == 1
    finally:
        short_link_batch.fetch_custom_link_rows = original
        server.shutdown()
        paths._DATA_DIR = None
        admin_web._LINK.update(status="idle", message="", updated=0, failed=0, total=0, done=0)


def test_http_export_and_import_roundtrip():
    folder = tempfile.mkdtemp(prefix="short-link-")
    catalog = {
        "updated_at": "",
        "products": [
            {
                "item_id": "56560510283",
                "shop_id": "1801449736",
                "product_link": "https://shopee.vn/product/1801449736/56560510283?utm=1",
                "short_link": "",
            }
        ],
    }
    with open(os.path.join(folder, "products_affiliate.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f)
    paths._DATA_DIR = folder
    server = ThreadingHTTPServer(("127.0.0.1", 0), admin_web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/short-link/export") as res:
            blob = res.read()
            assert res.headers["X-Link-Count"] == "1"
        assert _strings(blob)[-1] == "https://shopee.vn/product/1801449736/56560510283"
        boundary = "----batch"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="links.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8") + open(SAMPLE, "rb").read() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{port}/api/short-link/import",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urlopen(req) as res:
            payload = json.loads(res.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["updated"] == 1
        saved = json.load(open(os.path.join(folder, "products_affiliate.json"), encoding="utf-8"))
        assert saved["products"][0]["short_link"] == "https://s.shopee.vn/6fi4IWQPnD"
        assert saved["total_with_short_link"] == 1
    finally:
        server.shutdown()
        paths._DATA_DIR = None


if __name__ == "__main__":
    test_workbook_matches_template_columns()
    test_import_sample_csv_fills_only_missing_links()
    test_parse_and_apply_custom_link_response()
    test_generate_job_fills_catalog_without_browser()
    test_http_export_and_import_roundtrip()
    print("ok")
