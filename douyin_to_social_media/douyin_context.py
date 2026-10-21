"""Ngữ cảnh chủ đề video: tiêu đề gốc + caption_vi đã dịch."""

from __future__ import annotations

import re

import douyin_poster
import douyin_translate

_HASHTAG = re.compile(r"[#＃][^\s#＃]+")


def strip_hashtags(text: str) -> str:
    return re.sub(r"\s+", " ", _HASHTAG.sub(" ", text or "")).strip()


def load_topic(video_id: str) -> dict:
    """Ghép manifest + translations.json thành ngữ cảnh viết lời/phụ đề."""
    video_id = str(video_id or "")
    title_zh = ""
    description_zh = ""
    for item in douyin_poster.load_videos():
        if str(item.get("id") or "") == video_id:
            title_zh = str(item.get("title") or "")
            description_zh = str(item.get("description") or "")
            break

    saved = douyin_translate.lookup(video_id)
    caption_vi = str(saved.get("caption_vi") or "").strip()
    topic_vi = strip_hashtags(caption_vi)
    topic_zh = strip_hashtags(title_zh or description_zh)

    return {
        "video_id": video_id,
        "title_zh": title_zh,
        "description_zh": description_zh,
        "caption_vi": caption_vi,
        "topic_vi": topic_vi,
        "topic_zh": topic_zh,
        "asr_prompt": topic_zh or topic_vi,
    }
