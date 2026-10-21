"""Kho Douyin tách khỏi YouTube: nhận link, bỏ video trùng, hàng đăng riêng."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "douyin_to_social_media"))

import douyin_download as dy  # noqa: E402
import douyin_poster as dp  # noqa: E402
import douyin_translate as dt  # noqa: E402


VIDEO = "7349449338407439651"
USER = "MS4wLjABAAAAexampleUserId123456"


def _use_download(folder: Path) -> None:
    dy.DATA_DIR = folder
    dy.VIDEO_DIR = folder / "videos"
    dy.ARCHIVE_PATH = folder / "archive.txt"
    dy.MANIFEST_PATH = folder / "manifest.json"
    dy.SYNC_AUTO_PATH = folder / "sync_auto.json"
    dy.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    with dy._SYNC_LOCK:
        dy._SYNC.update(running=False, message="", seen=0, skipped=0, downloaded=0, failed=0)


def _use_poster(folder: Path) -> None:
    dp.DATA = folder
    dp.VIDEO_DIR = folder / "videos"
    dp.CONFIG_PATH = folder / "config.json"
    dp.MANIFEST_PATH = folder / "manifest.json"
    dp.POSTS_PATH = folder / "posts.json"
    dp.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dp._JOB.update(running=False, video_id="", title="", message="")
    dt.CACHE_PATH = folder / "translations.json"


def test_douyin_links_stay_apart_from_youtube():
    assert dy.is_video_url(f"https://www.douyin.com/video/{VIDEO}")
    assert dy.is_video_url(f"https://www.douyin.com/jingxuan?modal_id={VIDEO}")
    assert dy.is_video_url("https://v.douyin.com/iJrhQh5/")
    assert dy.is_user_url(f"https://www.douyin.com/user/{USER}")
    assert not dy.is_user_url(f"https://www.douyin.com/video/{VIDEO}")
    assert not dy.is_video_url("https://www.youtube.com/shorts/abcdefghijk")
    assert not dy.is_douyin_url("https://www.youtube.com/@biet.haychua/shorts")
    assert dy.video_id_of(f"https://www.douyin.com/share/video/{VIDEO}") == VIDEO
    assert dy.clean_user_url(f"https://www.douyin.com/user/{USER}?showTab=post") == f"https://www.douyin.com/user/{USER}"


def test_fresh_entries_skip_links_already_stored():
    known = dy.link_keys("", VIDEO)
    fresh, skipped = dy._fresh_entries([
        {"id": VIDEO, "url": dy.canonical_video_url(VIDEO)},
        {"id": "7000000000000000001", "url": "https://www.douyin.com/video/7000000000000000001"},
    ], known)
    assert skipped == 1
    assert fresh == [("7000000000000000001", "https://www.douyin.com/video/7000000000000000001")]


def test_cookie_error_is_actionable():
    text = dy.friendly_error(RuntimeError("Fresh cookies (not necessarily logged in) are needed"))
    assert "douyin_cookies.txt" in text


def test_download_refuses_youtube_and_duplicate_file():
    folder = Path(tempfile.mkdtemp(prefix="dy-dl-"))
    _use_download(folder)
    try:
        dy.start_download("https://www.youtube.com/shorts/abcdefghijk")
        raised = False
    except RuntimeError as exc:
        raised = "Douyin" in str(exc)
    assert raised

    (dy.VIDEO_DIR / f"{VIDEO}.mp4").write_bytes(b"mp4")
    dy._save_manifest({"accounts": [], "videos": [{
        "id": VIDEO,
        "url": dy.canonical_video_url(VIDEO),
        "file": str(dy.VIDEO_DIR / f"{VIDEO}.mp4"),
    }]})
    status = dy.start_download(dy.canonical_video_url(VIDEO))
    assert status["running"] is False
    assert "đã có" in status["message"]


def test_saved_sync_without_account_does_not_start():
    folder = Path(tempfile.mkdtemp(prefix="dy-sync-"))
    _use_download(folder)
    status = dy.start_sync("")
    assert status["running"] is False
    assert "tài khoản" in status["message"]


def test_poster_queue_reads_only_douyin_manifest():
    folder = Path(tempfile.mkdtemp(prefix="dy-post-"))
    _use_poster(folder)
    title = "Món ăn đường phố"
    (dp.VIDEO_DIR / f"{VIDEO}.mp4").write_bytes(b"mp4")
    (dp.VIDEO_DIR / "abcdefghijk.mp4").write_bytes(b"yt")
    dp.MANIFEST_PATH.write_text(json.dumps({"videos": [{
        "id": VIDEO,
        "title": title,
        "description": title,
        "url": dy.canonical_video_url(VIDEO),
        "upload_date": "20260801",
        "file": str(dp.VIDEO_DIR / f"{VIDEO}.mp4"),
        "channel": f"https://www.douyin.com/user/{USER}",
        "channel_name": "Bếp nhỏ",
    }]}), encoding="utf-8")
    dp.CONFIG_PATH.write_text(json.dumps({
        "page_id": "page",
        "page_name": "Page thử",
        "page_url": "",
        "token": "",
        "api_version": "v21.0",
        "auto": {"enabled": False, "interval_minutes": 60, "order": "oldest"},
    }), encoding="utf-8")
    state = dp.public_state()
    assert [item["id"] for item in state["videos"]] == [VIDEO]
    assert state["source"] == "douyin"
    assert state["videos"][0]["caption"] == title
    assert state["counts"]["pending"] == 1
    assert "abcdefghijk" not in json.dumps(state["videos"])


def test_compose_keeps_hashtags(monkeypatch):
    def fake(text):
        mapped = {
            "带你走进": "Dẫn bạn vào",
            "国风": "Phong cách Trung Quốc",
        }
        return mapped.get(text, text), "alibaba"

    monkeypatch.setattr(dt, "_translate_text", fake)
    caption, engine = dt.compose_caption("带你走进 #国风", "带你走进 #国风")
    assert engine == "alibaba"
    assert "Dẫn bạn vào" in caption
    assert "#PhongCáchTrungQuốc" in caption


def test_longer_description_is_translated_once(monkeypatch):
    def fake(text):
        return text, "alibaba"

    monkeypatch.setattr(dt, "_translate_text", fake)
    caption, _engine = dt.compose_caption("带你走进中国...", "带你走进中国传统纹样。 #国风")
    assert caption.count("带你走进中国") == 1
    assert "传统纹样" in caption


def test_user_post_payload_becomes_video_links():
    entries = dy._entries_from_posts({
        "status_code": 0,
        "aweme_list": [
            {"aweme_id": VIDEO, "desc": "皮影戏"},
            {"aweme_id": "không-phải-id"},
            "bỏ",
        ],
    })
    assert entries == [{
        "id": VIDEO,
        "url": dy.canonical_video_url(VIDEO),
        "title": "皮影戏",
    }]


def test_hashtag_joins_vietnamese_words():
    assert dt.hashtag("Phong cách Trung Quốc") == "#PhongCáchTrungQuốc"
    assert dt.looks_chinese("国风")
    assert not dt.looks_chinese("Hoa văn")


def test_saved_translation_becomes_the_caption():
    folder = Path(tempfile.mkdtemp(prefix="dy-vi-"))
    _use_poster(folder)
    (dp.VIDEO_DIR / f"{VIDEO}.mp4").write_bytes(b"mp4")
    dp.MANIFEST_PATH.write_text(json.dumps({"videos": [{
        "id": VIDEO,
        "title": "中文标题",
        "description": "中文标题",
        "upload_date": "20260801",
        "file": str(dp.VIDEO_DIR / f"{VIDEO}.mp4"),
    }]}), encoding="utf-8")
    dp.CONFIG_PATH.write_text(json.dumps({
        "page_id": "",
        "page_name": "",
        "page_url": "",
        "token": "",
        "api_version": "v21.0",
        "auto": {"enabled": False, "interval_minutes": 60, "order": "oldest"},
    }), encoding="utf-8")
    dt.save_caption(VIDEO, "Bản tiếng Việt #HoaVăn")
    state = dp.public_state()
    assert state["videos"][0]["caption"] == "Bản tiếng Việt #HoaVăn"
    assert state["videos"][0]["translated"] is True
    assert dp.media_path(VIDEO).name == f"{VIDEO}.mp4"
    assert dp.media_path("../secrets") is None


def test_edited_translation_is_not_replaced(monkeypatch):
    folder = Path(tempfile.mkdtemp(prefix="dy-edit-"))
    _use_poster(folder)
    dt.save_caption(VIDEO, "Giữ bản này")

    def boom(_text):
        raise AssertionError("không được dịch lại")

    monkeypatch.setattr(dt, "_translate_text", boom)
    row = dt.ensure_video({"id": VIDEO, "title": "中文标题", "description": "中文标题"}, force=False)
    assert row["caption_vi"] == "Giữ bản này"
    assert row["edited"] is True


def test_batch_translates_pending_chinese_titles(monkeypatch):
    folder = Path(tempfile.mkdtemp(prefix="dy-batch-"))
    _use_poster(folder)
    other = "7000000000000000002"
    videos = [
        {"id": VIDEO, "title": "中文标题", "description": "中文标题"},
        {"id": other, "title": "Đã tiếng Việt", "description": "Đã tiếng Việt"},
    ]

    def fake(text):
        return f"VI:{text}", "alibaba"

    monkeypatch.setattr(dt, "_translate_text", fake)
    with dt._BATCH_LOCK:
        dt._BATCH.update(running=False, video_id="", title="", message="", done=0, failed=0, total=0, pending=0)

    assert dt.needs_translation(videos[0])
    assert not dt.needs_translation(videos[1])
    status = dt.start_batch(videos)
    assert status["running"] is True or status["total"] == 1
    for _ in range(50):
        if not dt.batch_status()["running"]:
            break
        import time
        time.sleep(0.05)
    row = dt.lookup(VIDEO)
    assert row["caption_vi"].startswith("VI:")
    assert not dt.lookup(other).get("caption_vi")
    assert dt.batch_status()["done"] == 1
