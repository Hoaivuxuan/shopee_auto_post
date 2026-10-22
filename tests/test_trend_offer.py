"""Mục sản phẩm xu hướng: phân trang API và hoa hồng."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool.shopee_affiliate import (  # noqa: E402
    OFFERS,
    affiliate_session_ready,
    canonical_category,
    display_commission,
    display_from_process_list,
    extract_products,
    is_login_url,
    list_page_count,
    merge_product_lists,
    offer_by_key,
    offer_page_url,
    offers_for_catalog_update,
    product_in_offer,
    product_needs_media,
    official_login_url,
    parse_curl_command,
    product_offer_update_order,
    read_offer_snapshot,
    session_cookie_missing,
    write_curl_cookies,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_trend_page_count_covers_five_hundred():
    assert list_page_count(500, 20, 25) == 25
    assert list_page_count(500, 20, 3) == 3
    assert list_page_count(20, 20, 25) == 1


def test_trend_offer_uses_product_page():
    offer = offer_by_key("trend")
    assert offer["name"] == "Bán chạy nhất"
    assert offer["list_type"] == "2"
    assert offer_by_key("Sản phẩm xu hướng")["id"] == "trend"
    assert offer_by_key("Bán chạy nhất")["id"] == "trend"
    page = offer_page_url({
        "url": "https://affiliate.shopee.vn/api/v3/offer/product/list?list_type=2&page_offset=0&page_limit=20",
        "headers": {"referer": "https://affiliate.shopee.vn/offer/product_offer"},
    })
    assert page == "https://affiliate.shopee.vn/offer/product_offer"


def test_product_offer_tabs_follow_the_page():
    names = [item["name"] for item in OFFERS[:7]]
    assert names == [
        "Tất cả",
        "Hoa hồng Xtra",
        "Bán chạy nhất",
        "Nhà Cửa & Đời Sống",
        "Sắc Đẹp",
        "Bách Hóa Online",
        "Thời Trang Nữ",
    ]
    assert offer_by_key("Hoa hồng Xtra")["list_type"] == "7"
    assert offer_by_key("Tất cả")["list_type"] == "0"
    assert offer_by_key("Sắc Đẹp")["match_id"] == "100630"
    assert offer_by_key("Bách Hóa Online")["match_id"] == "100629"
    assert offer_by_key("Thời Trang Nữ")["match_id"] == "100017"
    assert offer_by_key("Nhà cửa & Đời sống")["name"] == "Nhà Cửa & Đời Sống"
    assert canonical_category("Sản phẩm xu hướng", "trend") == ("trend", "Bán chạy nhất")
    assert canonical_category("Nhà cửa & Đời sống", "100636") == ("100636", "Nhà Cửa & Đời Sống")


def test_expired_session_opens_official_login():
    login = official_login_url("https://affiliate.shopee.vn/offer/product_offer")
    assert login.startswith("https://shopee.vn/buyer/login?next=")
    assert "affiliate.shopee.vn" in login
    assert session_cookie_missing({})
    assert session_cookie_missing({"SPC_ST": "-", "SPC_U": "1"})
    assert not session_cookie_missing({"SPC_ST": "phien", "SPC_U": "1", "SPC_EC": "-"})
    ready = {"SPC_ST": "phien", "SPC_U": "1"}
    assert affiliate_session_ready("https://affiliate.shopee.vn/offer/product_offer", ready)
    assert not affiliate_session_ready("https://shopee.vn/buyer/login?next=1", ready)
    assert not affiliate_session_ready("https://shopee.vn/verify/traffic/error", ready)
    assert not is_login_url("https://affiliate.shopee.vn/offer/product_offer")
    assert display_from_process_list("/usr/lib/xorg/Xorg -core :0 -seat seat0") == ":0"
    assert display_from_process_list("Xvfb :95 -screen 0 1280x800x24") == ""
    folder = os.path.join(ROOT, "data")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "_curl_cookie_test.txt")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(
                "curl --url 'https://affiliate.shopee.vn/api/v3/offer/product/list?list_type=2' \\\n"
                "  -b 'SPC_ST=cu; SPC_U=1' \\\n"
                "  -H 'referer: https://affiliate.shopee.vn/offer/product_offer'\n"
                "response:\n{\"data\":{}}\n"
            )
        write_curl_cookies(path, {"SPC_ST": "moi", "SPC_U": "2", "SPC_EC": "-"})
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        assert "response:" in content
        info = parse_curl_command(content.split("response:")[0])
        assert info["cookies"]["SPC_ST"] == "moi"
        assert info["cookies"]["SPC_U"] == "2"
        assert not session_cookie_missing(info["cookies"])
    finally:
        if os.path.isfile(path):
            os.remove(path)
    curl_file = os.path.join(ROOT, "api_shopee", "curl_trend_product.txt")
    with open(curl_file, encoding="utf-8") as handle:
        info = parse_curl_command(handle.read().split("response:")[0])
    assert not session_cookie_missing(info.get("cookies") or {})


def test_catalog_update_skips_products_already_saved():
    order = [item["name"] for item in product_offer_update_order()]
    assert order[:7] == [
        "Hoa hồng Xtra",
        "Bán chạy nhất",
        "Nhà Cửa & Đời Sống",
        "Sắc Đẹp",
        "Bách Hóa Online",
        "Thời Trang Nữ",
        "Tất cả",
    ]
    assert offers_for_catalog_update("Sắc Đẹp")[0]["id"] == "100630"
    assert offers_for_catalog_update("Bán chạy nhất")[0]["id"] == "trend"
    assert offers_for_catalog_update("all")[0]["name"] == "Tất cả"
    assert [item["name"] for item in offers_for_catalog_update("*")] == order
    assert [item["name"] for item in offers_for_catalog_update("Mọi mục")] == order
    try:
        offers_for_catalog_update("")
        raise AssertionError("mục trống phải bị từ chối")
    except ValueError as exc:
        assert "chọn một mục" in str(exc)
    saved = [{"item_id": "1", "name": "cũ", "short_link": "https://s.shopee.vn/a", "category_name": "Bán chạy nhất"}]
    fresh = [
        {"item_id": "1", "name": "mới", "short_link": "", "category_name": "Tất cả"},
        {"item_id": "2", "name": "thêm", "category_name": "Sắc Đẹp"},
        {"item_id": "2", "name": "thêm lần nữa", "category_name": "Sắc Đẹp"},
    ]
    merged, added = merge_product_lists(saved, fresh)
    assert added == 1
    assert [item["item_id"] for item in merged] == ["1", "2"]
    assert merged[0]["short_link"] == "https://s.shopee.vn/a"
    assert merged[0]["category_name"] == "Bán chạy nhất"


def test_catalog_downloads_missing_media_for_selected_category():
    import shopeetool.shopee_affiliate as mod

    offer = offer_by_key("Sắc Đẹp")
    assert product_in_offer({"category_id": "trend", "category_name": "Sản phẩm xu hướng"}, offer_by_key("Bán chạy nhất"))
    assert not product_in_offer({"category_id": "trend", "category_name": "Bán chạy nhất"}, offer)
    ready_key = "8_ready"
    ready_dir = os.path.join(ROOT, "data", "affiliate", ready_key)
    os.makedirs(ready_dir, exist_ok=True)
    with open(os.path.join(ready_dir, ready_key + ".jpg"), "wb") as handle:
        handle.write(b"jpeg")
    ready = {
        "item_id": "ready",
        "shop_id": "8",
        "category_id": "100630",
        "category_name": "Sắc Đẹp",
        "image_url": "https://img/ready",
        "image_file": "affiliate/8_ready/8_ready.jpg",
    }
    assert not product_needs_media(ready)
    assert product_needs_media({
        "item_id": "new",
        "shop_id": "8",
        "image_url": "https://img/new",
        "video_url": "https://cdn/new.mp4",
    })
    out = os.path.join(ROOT, "data", "_catalog_media_test.json")
    saved = [
        {
            "item_id": "new",
            "shop_id": "8",
            "name": "thiếu ảnh",
            "category_id": "100630",
            "category_name": "Sắc Đẹp",
            "image_url": "https://img/new",
            "video_url": "https://cdn/new.mp4",
        },
        ready,
        {
            "item_id": "other",
            "shop_id": "8",
            "name": "mục khác",
            "category_id": "trend",
            "category_name": "Bán chạy nhất",
            "image_url": "https://img/other",
        },
    ]
    mod.save_to_json(saved, out)
    calls = []

    def fake_download(products, limit=0, on_item=None, only=""):
        calls.append([item["item_id"] for item in products])
        for index, product in enumerate(products, 1):
            key = f"{product['shop_id']}_{product['item_id']}"
            folder = os.path.join(ROOT, "data", "affiliate", key)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, key + ".jpg"), "wb") as handle:
                handle.write(b"jpeg")
            product["image_file"] = f"affiliate/{key}/{key}.jpg"
            if product.get("video_url"):
                with open(os.path.join(folder, key + ".mp4"), "wb") as handle:
                    handle.write(b"mp4")
                product["video_file"] = f"affiliate/{key}/{key}.mp4"
            if on_item:
                on_item(index, len(products), product)
        return products

    def fake_get(**kwargs):
        current = mod.load_saved_products(kwargs["output_file"]) or []
        extra = {
            "item_id": "fresh",
            "shop_id": "8",
            "name": "mới",
            "category_id": "100630",
            "category_name": "Sắc Đẹp",
            "image_url": "https://img/fresh",
        }
        merged, _added = mod.merge_product_lists(current, [extra])
        path = mod.save_to_json(merged, kwargs["output_file"])
        return merged, path

    old_download = mod.download_product_media
    old_get = mod.get_affiliate_products
    try:
        mod.download_product_media = fake_download
        mod.get_affiliate_products = fake_get
        result = mod.update_product_catalog(output_file=out, offer_key="Sắc Đẹp", max_pages=1)
    finally:
        mod.download_product_media = old_download
        mod.get_affiliate_products = old_get
        if os.path.isfile(out):
            os.remove(out)
        for key in ("8_ready", "8_new", "8_fresh"):
            folder = os.path.join(ROOT, "data", "affiliate", key)
            for name in os.listdir(folder) if os.path.isdir(folder) else []:
                os.remove(os.path.join(folder, name))
            if os.path.isdir(folder):
                os.rmdir(folder)
    assert calls == [["new"], ["new"], ["fresh"], ["fresh"]]
    assert result["added"] == 1
    assert result["images"] == 2
    assert result["videos"] == 1
    assert result["offers"][0]["name"] == "Sắc Đẹp"


def test_trend_snapshot_keeps_seller_commission():
    curl_file = os.path.join(ROOT, "api_shopee", "curl_trend_product.txt")
    raw = read_offer_snapshot(curl_file, offer_by_key("trend"))
    data = raw["data"]
    assert data["page_limit"] == 20
    assert data["total_count"] == 500
    assert len(data["list"]) == 20
    products = extract_products(raw, "trend", "Bán chạy nhất")
    assert len(products) == 20
    assert products[0]["category_name"] == "Bán chạy nhất"
    assert products[0]["commission_rate"] != "0%"
    assert display_commission({"max_commission_rate": "82,5%", "seller_commission_rate": "80%"}) == "82,5%"


if __name__ == "__main__":
    test_trend_page_count_covers_five_hundred()
    test_trend_offer_uses_product_page()
    test_product_offer_tabs_follow_the_page()
    test_catalog_update_skips_products_already_saved()
    test_catalog_downloads_missing_media_for_selected_category()
    test_expired_session_opens_official_login()
    test_trend_snapshot_keeps_seller_commission()
    print("ok")
