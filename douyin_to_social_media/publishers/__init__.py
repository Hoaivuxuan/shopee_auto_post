"""Publisher đa nền tảng: Facebook, YouTube, TikTok, Instagram."""

from __future__ import annotations

from typing import Any, Protocol


class PublishResult(dict):
    """result = {ok, platform, post_id, url, message}."""


class Publisher(Protocol):
    name: str

    def publish(self, video_path: str, *, title: str, caption: str, **kwargs: Any) -> PublishResult:
        ...


PLATFORMS = ("facebook", "youtube", "tiktok", "instagram")

PLATFORM_LABELS = {
    "facebook": "Facebook",
    "youtube": "YouTube Shorts",
    "tiktok": "TikTok",
    "instagram": "Instagram Reels",
}
