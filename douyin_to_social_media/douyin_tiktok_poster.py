"""Hàng đợi đăng video ngắn Douyin lên TikTok."""

from __future__ import annotations

from pathlib import Path

from publishers import tiktok as ttk
from target_poster import TargetPoster

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "douyin"

_EMPTY = {
    "client_key": "",
    "client_secret": "",
    "redirect_uri": "http://127.0.0.1:8768/callback",
    "oauth_port": 8768,
    "privacy_level": "PUBLIC_TO_EVERYONE",
    "account_id": "",
    "account_name": "",
    "account_url": "https://www.tiktok.com",
    "open_id": "",
    "access_token": "",
    "refresh_token": "",
    "auto": {"enabled": False, "interval_minutes": 60, "order": "oldest"},
}


def _upload(video_path: str, *, title: str, caption: str, config: dict, on_step=None) -> dict:
    return ttk.upload_video(
        video_path,
        title=title,
        caption=caption,
        config=config,
        data_dir=DATA,
        on_step=on_step,
    )


def _auth_status(config: dict) -> dict:
    return ttk.auth_status(config, DATA)


poster = TargetPoster(
    target="tiktok",
    label="TikTok",
    data_dir=DATA,
    config_name="tiktok_config.json",
    posts_name="tiktok_posts.json",
    empty_config=_EMPTY,
    upload=_upload,
    auth_status=_auth_status,
    id_field="tiktok_publish_id",
    scheduler_name="dy-tt-auto",
)

load_config = poster.load_config
save_config = poster.save_config
load_posts = poster.load_posts
public_state = poster.public_state
update_settings = poster.update_settings
start_post = poster.start_post
post_video = poster.post_video
start_scheduler = poster.start_scheduler


def start_oauth() -> dict:
    cfg = poster.load_config()
    if not str(cfg.get("client_key") or "").strip() or not str(cfg.get("client_secret") or "").strip():
        raise RuntimeError("Hãy nhập và lưu client_key / client_secret trước khi ủy quyền TikTok.")
    port = int(cfg.get("oauth_port") or 8768)

    def runner():
        return ttk.start_oauth(cfg, DATA, port=port)

    return poster.run_auth_job(runner)
