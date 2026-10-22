"""Caption có tag tìm kiếm, bình luận kèm ảnh và link rút gọn."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool import admin_web, facebook, paths  # noqa: E402

VN = timezone(timedelta(hours=7))


def test_product_tags_use_name_and_category():
    tags = admin_web.product_tags("Hộp đựng giấy ăn vuông gỗ hương", "Nhà cửa & Đời sống")
    assert tags[0] == "#HopDungGiayAn"
    assert "#NhaCua" in tags
    assert "#DoiSong" in tags
    assert "#Cua" not in admin_web.product_tags("Hộp của gỗ", "")
    assert "#Do" in admin_web.product_tags("Đồ gỗ", "")
    caption = admin_web._caption("Hộp đựng giấy ăn", "https://s.shopee.vn/abc", "Mua tại: ", tags)
    assert "https://s.shopee.vn/abc" not in caption
    assert "Mua tại:" not in caption
    assert "#HopDungGiayAn" in caption


def test_caption_prompt_loads_skill():
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"response": "Hộp giấy ăn gỗ để bàn gọn hơn. 🤍 Lau qua là sạch."}).encode()

    def capture(req, timeout=None):
        seen["prompt"] = json.loads(req.data.decode())["prompt"]
        return Resp()

    original = admin_web.urllib.request.urlopen
    admin_web.urllib.request.urlopen = capture
    try:
        admin_web._draft_caption(
            "Hộp đựng giấy ăn vuông gỗ hương 89.000₫", "Nhà cửa & Đời sống", "120.000 ₫",
        )
    finally:
        admin_web.urllib.request.urlopen = original
    assert "Đúng chủ đề" in seen["prompt"]
    assert "Hộp đựng giấy ăn" in seen["prompt"]
    assert "89.000" not in seen["prompt"]
    assert "120.000" not in seen["prompt"]
    assert "https://" not in seen["prompt"]
    priced = "✨ Hộp giấy ăn chỉ 89.000₫, gọn hơn mỗi bữa. 🤍 Lau qua là sạch."
    assert not admin_web._caption_draft_ok(priced)
    assert "89.000" not in admin_web._caption("Giá đỡ điện thoại 99k", "", "")
    assert admin_web._caption("Giá đỡ điện thoại", "", "").startswith("Giá đỡ điện thoại")


def test_soft_caption_uses_qwen_without_link():
    draft = "✨ Hộp giấy ăn gỗ hương để bàn gọn hơn mỗi bữa. 🤍 Mềm mắt và dễ lau."
    assert admin_web._caption_draft_ok(draft)

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"response": "Hộp giấy ăn gỗ hương để bàn gọn hơn mỗi bữa. 🤍 Mềm mắt và dễ lau."}).encode()

    original = admin_web.urllib.request.urlopen
    admin_web.urllib.request.urlopen = lambda *_args, **_kwargs: Resp()
    try:
        message = admin_web.post_message(
            {"name": "Hộp đựng giấy ăn vuông gỗ hương", "category_name": "Nhà cửa & Đời sống", "price_formatted": "89.000 ₫"},
            "https://s.shopee.vn/abc",
            "Mua tại: ",
        )
    finally:
        admin_web.urllib.request.urlopen = original
    assert "✨" in message
    assert "🤍" in message
    assert "https://s.shopee.vn" not in message
    assert "Mua tại:" not in message
    assert "#HopDungGiayAn" in message


def test_soft_caption_falls_back_when_model_fails():
    def boom(*_args, **_kwargs):
        raise OSError("ollama tắt")

    original = admin_web.urllib.request.urlopen
    admin_web.urllib.request.urlopen = boom
    try:
        message = admin_web.post_message(
            {"name": "Hộp đựng giấy ăn", "category_name": "Nhà cửa & Đời sống"},
            "https://s.shopee.vn/abc",
            "Mua tại: ",
        )
    finally:
        admin_web.urllib.request.urlopen = original
    assert message.startswith("Hộp đựng giấy ăn")
    assert "https://s.shopee.vn" not in message
    assert "Mua tại:" not in message


def _product_files(folder):
    os.makedirs(os.path.join(folder, "affiliate", "x"), exist_ok=True)
    video = os.path.join(folder, "affiliate", "x", "a.mp4")
    image = os.path.join(folder, "affiliate", "x", "a.jpg")
    with open(video, "wb") as handle:
        handle.write(b"video")
    with open(image, "wb") as handle:
        handle.write(b"image")
    return "affiliate/x/a.mp4", "affiliate/x/a.jpg", image


def _tools(upload, comment):
    return {
        "page": {"id": "page", "name": "Trang", "token": "t"},
        "prefix": "Mua tại: ",
        "version": "v25.0",
        "upload_video": upload,
        "post_comment": comment,
        "FBError": facebook.FBError,
        "hint_for": lambda _err: "",
        "FATAL_CODES": set(),
    }


def test_publish_now_comments_image_with_short_link():
    folder = tempfile.mkdtemp(prefix="caption-")
    paths._DATA_DIR = folder
    video_rel, image_rel, image = _product_files(folder)
    raw = {"products": [{
        "item_id": "1",
        "name": "Hộp đựng giấy ăn vuông gỗ hương",
        "category_name": "Nhà cửa & Đời sống",
        "short_link": "https://s.shopee.vn/abc",
        "long_link": "https://shopee.vn/product/1/1",
        "video_file": video_rel,
        "image_file": image_rel,
    }]}
    seen = {}

    def upload(_page, _path, message, _version, schedule_ts=None):
        seen["message"] = message
        seen["schedule"] = schedule_ts
        return "vid"

    def comment(_page, video_id, text, _version, image_path=None):
        seen["comment"] = (video_id, text, image_path)
        return "cmt"

    original_message = admin_web.post_message
    admin_web.post_message = lambda item, link, prefix: admin_web._caption(
        item.get("name") or "", link, prefix,
        admin_web.product_tags(item.get("name") or "", item.get("category_name") or ""),
    )
    try:
        result = admin_web._post_one(raw, raw["products"][0], "1", "now", None, "", _tools(upload, comment))
    finally:
        admin_web.post_message = original_message
        paths._DATA_DIR = None
    assert result["ok"] is True
    assert result["warning"] == ""
    assert "#HopDungGiayAn" in seen["message"]
    assert "https://s.shopee.vn" not in seen["message"]
    assert seen["comment"][0] == "vid"
    assert seen["comment"][1] == "Mua tại: https://s.shopee.vn/abc"
    assert seen["comment"][2] == image
    assert raw["products"][0]["facebook_comment_id"] == "cmt"
    assert raw["products"][0]["facebook_comment_pending"] is False


def test_schedule_waits_to_comment_the_image():
    folder = tempfile.mkdtemp(prefix="caption-sched-")
    paths._DATA_DIR = folder
    video_rel, image_rel, _image = _product_files(folder)
    raw = {"products": [{
        "item_id": "1",
        "name": "Khay gỗ",
        "category_name": "Đồ gia dụng",
        "short_link": "https://s.shopee.vn/xyz",
        "video_file": video_rel,
        "image_file": image_rel,
    }]}
    seen = {"comment": False}

    def upload(*_args, **_kwargs):
        return "vid"

    def comment(*_args, **_kwargs):
        seen["comment"] = True
        return "cmt"

    original_message = admin_web.post_message
    admin_web.post_message = lambda item, link, prefix: admin_web._caption(
        item.get("name") or "", link, prefix,
        admin_web.product_tags(item.get("name") or "", item.get("category_name") or ""),
    )
    try:
        result = admin_web._post_one(
            raw, raw["products"][0], "1", "schedule", 1, "2026-10-15 23:50", _tools(upload, comment),
        )
    finally:
        admin_web.post_message = original_message
        paths._DATA_DIR = None
    assert result["ok"] is True
    assert seen["comment"] is False
    assert raw["products"][0]["facebook_comment_pending"] is True


def test_deliver_pending_comment_after_schedule():
    folder = tempfile.mkdtemp(prefix="caption-deliver-")
    paths._DATA_DIR = folder
    video_rel, image_rel, image = _product_files(folder)
    past = (datetime.now(VN) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    raw = {"updated_at": "", "products": [{
        "item_id": "1",
        "name": "Khay gỗ",
        "short_link": "https://s.shopee.vn/xyz",
        "video_file": video_rel,
        "image_file": image_rel,
        "facebook_video_id": "vid",
        "facebook_page_id": "page",
        "facebook_status": "published",
        "facebook_scheduled_at": past,
        "facebook_comment_pending": True,
    }]}
    with open(os.path.join(folder, "products_affiliate.json"), "w", encoding="utf-8") as handle:
        import json
        json.dump(raw, handle)
    seen = {}

    def comment(_page, video_id, text, _version, image_path=None):
        seen["comment"] = (video_id, text, image_path)
        return "cmt"

    original = admin_web._facebook_tools
    admin_web._facebook_tools = lambda _page_id: _tools(lambda *_a, **_k: "", comment)
    try:
        sent = admin_web.deliver_pending_comments()
        saved = admin_web._load_catalog()
    finally:
        admin_web._facebook_tools = original
        paths._DATA_DIR = None
    assert sent == 1
    assert seen["comment"] == ("vid", "Mua tại: https://s.shopee.vn/xyz", image)
    assert saved["products"][0]["facebook_comment_id"] == "cmt"
    assert saved["products"][0]["facebook_comment_pending"] is False


def test_post_comment_sends_image_file():
    folder = tempfile.mkdtemp(prefix="fb-comment-")
    image = os.path.join(folder, "a.jpg")
    with open(image, "wb") as handle:
        handle.write(b"image")
    captured = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"id": "99"}

    def fake_post(url, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = files
        captured["timeout"] = timeout
        return Resp()

    original = facebook.requests.post
    facebook.requests.post = fake_post
    try:
        comment_id = facebook.post_comment(
            {"id": "1", "token": "t"}, "vid", "Mua tại: https://s.shopee.vn/abc", "v25.0", image,
        )
    finally:
        facebook.requests.post = original
    assert comment_id == "99"
    assert captured["data"]["message"] == "Mua tại: https://s.shopee.vn/abc"
    name, handle, mime = captured["files"]["source"]
    assert name == "a.jpg"
    assert mime == "image/jpeg"
    handle.close()


if __name__ == "__main__":
    test_product_tags_use_name_and_category()
    test_caption_prompt_loads_skill()
    test_soft_caption_uses_qwen_without_link()
    test_soft_caption_falls_back_when_model_fails()
    test_publish_now_comments_image_with_short_link()
    test_schedule_waits_to_comment_the_image()
    test_deliver_pending_comment_after_schedule()
    test_post_comment_sends_image_file()
    print("ok")
