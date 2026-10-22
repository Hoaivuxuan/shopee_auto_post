"""Tăng số bài trong ngày thì xếp thêm ngay, giữ bài đã hẹn."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool import admin_web, auto_post, paths  # noqa: E402


def _use_data(folder):
    paths._DATA_DIR = folder
    os.makedirs(folder, exist_ok=True)


def test_ready_ids_keep_selected_categories_only():
    raw = {"products": [
        {"item_id": "home", "category_name": "Đồ gia dụng", "video_file": "a.mp4", "short_link": "https://s.shopee.vn/a"},
        {"item_id": "trend", "category_name": "Sản phẩm xu hướng", "video_file": "b.mp4", "short_link": "https://s.shopee.vn/b"},
        {"item_id": "life", "category_name": "Nhà cửa & Đời sống", "video_file": "c.mp4", "long_link": "https://shopee.vn/x"},
    ]}
    assert auto_post._ready_ids(raw, "page", ["Sản phẩm xu hướng", "Đồ gia dụng"]) == ["home", "trend"]
    assert auto_post._ready_ids(raw, "page", ["Bán chạy nhất"]) == ["trend"]
    assert auto_post._ready_ids(raw, "page", []) == ["home", "trend", "life"]


def test_pending_ids_skip_posted_and_fill_quota():
    kept = [{"item_id": "posted", "ok": True, "at": "2026-10-15 08:28"}]
    ready = ["posted", "b", "c", "d", "e"]
    assert auto_post._pending_ids(ready, kept, 4) == ["b", "c", "d"]
    assert auto_post._pending_ids(ready, kept, 1) == []


def test_raising_quota_replans_today():
    folder = tempfile.mkdtemp(prefix="auto-post-")
    _use_data(folder)
    today = auto_post._now().strftime("%Y-%m-%d")
    auto_post.save_settings({
        "enabled": True,
        "per_day": 1,
        "page_id": "page",
        "planned_on": today,
        "settled_on": today,
        "settled_count": 1,
        "message": "Hôm nay đã xếp lịch. Số bài mới áp dụng từ ngày mai.",
        "slots": [{
            "item_id": "posted",
            "name": "Đã đăng",
            "at": f"{today} 08:28",
            "ok": True,
            "error": "",
        }],
    })
    kicked = []
    original = auto_post._kick
    auto_post._kick = lambda: kicked.append(True)
    try:
        status = auto_post.update_settings(True, 12, "page")
    finally:
        auto_post._kick = original
        paths._DATA_DIR = None
    assert kicked == [True]
    assert status["per_day"] == 12
    assert status["enabled"] is True
    assert "ngày mai" not in status["message"]
    assert status["slots"][0]["item_id"] == "posted"


def test_plan_keeps_posted_slot_and_schedules_the_rest():
    folder = tempfile.mkdtemp(prefix="auto-plan-")
    _use_data(folder)
    today = auto_post._now().strftime("%Y-%m-%d")
    products = [
        {
            "item_id": "posted",
            "name": "Đã đăng",
            "video_file": "affiliate/posted/posted.mp4",
            "short_link": "https://s.shopee.vn/old",
            "facebook_video_id": "1",
            "facebook_page_id": "page",
            "facebook_status": "published",
        },
        {
            "item_id": "next-a",
            "name": "Bài A",
            "video_file": "affiliate/a/a.mp4",
            "short_link": "https://s.shopee.vn/a",
        },
        {
            "item_id": "next-b",
            "name": "Bài B",
            "video_file": "affiliate/b/b.mp4",
            "short_link": "https://s.shopee.vn/b",
        },
    ]
    with open(os.path.join(folder, "products_affiliate.json"), "w", encoding="utf-8") as handle:
        json.dump({"products": products}, handle)
    auto_post.save_settings({
        "enabled": True,
        "per_day": 3,
        "page_id": "page",
        "planned_on": today,
        "slots": [{
            "item_id": "posted",
            "name": "Đã đăng",
            "at": f"{today} 08:28",
            "ok": True,
            "error": "",
        }],
    })
    posted = []

    def fake_tools(_page_id):
        return {"page": {"id": "page", "name": "Trang"}}

    def fake_post(_raw, _item, item_id, mode, _ts, label, _tools):
        posted.append((item_id, mode, label))
        return {"ok": True, "item_id": item_id}

    original_tools = admin_web._facebook_tools
    original_post = admin_web._post_one
    admin_web._facebook_tools = fake_tools
    admin_web._post_one = fake_post
    try:
        auto_post._plan_today()
        saved = auto_post.load_settings()
    finally:
        admin_web._facebook_tools = original_tools
        admin_web._post_one = original_post
        paths._DATA_DIR = None
    assert [row[0] for row in posted] == ["next-a", "next-b"]
    assert all(row[1] == "schedule" for row in posted)
    ids = [slot["item_id"] for slot in saved["slots"] if slot.get("ok")]
    assert ids[0] == "posted"
    assert ids[1:] == ["next-a", "next-b"]
    assert saved["settled_count"] == 3
    assert "3/3" in saved["message"]


def test_dates_stay_inside_facebook_window():
    now = datetime(2026, 10, 15, 12, 0, tzinfo=auto_post._tz())
    assert auto_post.normalize_dates(["2026-10-16", "2026-10-15", "2026-10-15"], now) == ["2026-10-15", "2026-10-16"]
    for bad in ("2026-10-14", "2026-11-14"):
        try:
            auto_post.normalize_dates([bad], now)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_future_day_runs_across_the_whole_day():
    now = datetime(2026, 10, 15, 11, 17, tzinfo=auto_post._tz())
    times = auto_post.even_times(4, now=now, day=datetime(2026, 10, 16).date())
    labels = [item.strftime("%Y-%m-%d %H:%M") for item in times]
    assert labels[0] == "2026-10-16 00:00"
    assert labels[-1] == "2026-10-16 23:59"
    assert len({item[:10] for item in labels}) == 1


def test_tick_does_not_plan_when_no_dates_are_chosen():
    folder = tempfile.mkdtemp(prefix="auto-tick-")
    _use_data(folder)
    auto_post.save_settings({"enabled": True, "per_day": 4, "page_id": "page", "dates": []})
    kicked = []
    original = auto_post._kick
    auto_post._kick = lambda: kicked.append(True)
    try:
        auto_post.tick()
    finally:
        auto_post._kick = original
        paths._DATA_DIR = None
    assert kicked == []


def test_plan_puts_one_quota_on_each_selected_day():
    folder = tempfile.mkdtemp(prefix="auto-days-")
    _use_data(folder)
    today = auto_post._now().date()
    tomorrow = today + timedelta(days=1)
    products = [
        {"item_id": "next-a", "name": "Bài A", "video_file": "a.mp4", "short_link": "https://s.shopee.vn/a"},
        {"item_id": "next-b", "name": "Bài B", "video_file": "b.mp4", "short_link": "https://s.shopee.vn/b"},
    ]
    with open(os.path.join(folder, "products_affiliate.json"), "w", encoding="utf-8") as handle:
        json.dump({"products": products}, handle)
    auto_post.save_settings({
        "enabled": True,
        "per_day": 1,
        "page_id": "page",
        "dates": [today.isoformat(), tomorrow.isoformat()],
        "date_mode": "days",
    })
    posted = []

    def fake_tools(_page_id):
        return {"page": {"id": "page", "name": "Trang"}}

    def fake_post(_raw, _item, item_id, mode, _ts, label, _tools):
        posted.append((item_id, mode, label))
        return {"ok": True, "item_id": item_id}

    original_tools = admin_web._facebook_tools
    original_post = admin_web._post_one
    admin_web._facebook_tools = fake_tools
    admin_web._post_one = fake_post
    try:
        auto_post._plan_today()
        saved = auto_post.load_settings()
    finally:
        admin_web._facebook_tools = original_tools
        admin_web._post_one = original_post
        paths._DATA_DIR = None
    assert [row[2][:10] for row in posted] == [today.isoformat(), tomorrow.isoformat()]
    assert posted[1][2][11:] == "00:00"
    assert saved["settled_dates"] == [today.isoformat(), tomorrow.isoformat()]
    assert "1/1" in saved["message"]


if __name__ == "__main__":
    test_ready_ids_keep_selected_categories_only()
    test_pending_ids_skip_posted_and_fill_quota()
    test_raising_quota_replans_today()
    test_plan_keeps_posted_slot_and_schedules_the_rest()
    test_dates_stay_inside_facebook_window()
    test_future_day_runs_across_the_whole_day()
    test_tick_does_not_plan_when_no_dates_are_chosen()
    test_plan_puts_one_quota_on_each_selected_day()
    print("ok")
