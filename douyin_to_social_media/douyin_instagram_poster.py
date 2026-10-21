"""Hàng đợi đăng video ngắn Douyin lên Instagram Reels."""

from __future__ import annotations

from pathlib import Path

import douyin_poster as fb
from publishers import instagram as ig
from target_poster import TargetPoster

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "douyin"

_EMPTY = {
    "access_token": "",
    "page_id": "",
    "ig_user_id": "",
    "api_version": "v21.0",
    "public_base_url": "",
    "account_id": "",
    "account_name": "",
    "account_url": "https://www.instagram.com",
    "auto": {"enabled": False, "interval_minutes": 60, "order": "oldest"},
}


def _seed_from_facebook(cfg: dict) -> dict:
    """Tái dùng Page token / page_id từ cấu hình Facebook nếu IG chưa có."""
    out = dict(cfg)
    if out.get("access_token") and out.get("page_id"):
        return out
    try:
        fb_cfg = fb.load_config()
    except Exception:
        return out
    if not out.get("access_token") and fb_cfg.get("token"):
        out["access_token"] = fb_cfg["token"]
    if not out.get("page_id") and fb_cfg.get("page_id"):
        out["page_id"] = fb_cfg["page_id"]
    if not out.get("api_version") and fb_cfg.get("api_version"):
        out["api_version"] = fb_cfg["api_version"]
    return out


def _upload(video_path: str, *, title: str, caption: str, config: dict, on_step=None) -> dict:
    return ig.upload_reel(
        video_path,
        title=title,
        caption=caption,
        config=_seed_from_facebook(config),
        on_step=on_step,
    )


def _auth_status(config: dict) -> dict:
    return ig.auth_status(_seed_from_facebook(config))


poster = TargetPoster(
    target="instagram",
    label="Instagram",
    data_dir=DATA,
    config_name="instagram_config.json",
    posts_name="instagram_posts.json",
    empty_config=_EMPTY,
    upload=_upload,
    auth_status=_auth_status,
    id_field="instagram_media_id",
    scheduler_name="dy-ig-auto",
)

load_config = poster.load_config
save_config = poster.save_config
load_posts = poster.load_posts
public_state = poster.public_state
update_settings = poster.update_settings
start_post = poster.start_post
post_video = poster.post_video
start_scheduler = poster.start_scheduler
