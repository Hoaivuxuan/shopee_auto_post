"""Publisher Facebook — bọc douyin_poster (implementation hiện tại).

Giữ API mỏng để YouTube / TikTok bám cùng chữ ký publish().
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import douyin_poster as poster


name = "facebook"


def publish(video_path: str, *, title: str = "", caption: str = "", video_id: str = "", **kwargs: Any) -> dict:
    """Đăng video Douyin lên Facebook Page qua hàng đợi hiện có."""
    if video_id:
        try:
            state = poster.start_post(video_id)
            job = state.get("job") or {}
            return {
                "ok": True,
                "platform": name,
                "message": job.get("message") or "Đã đưa vào hàng đăng Facebook",
                "video_id": video_id,
                "title": title or job.get("title") or "",
                "state": state,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "platform": name, "message": str(exc), "video_id": video_id}
    path = Path(video_path)
    if not path.is_file():
        return {"ok": False, "platform": name, "message": f"Không thấy file: {path}"}
    return {
        "ok": False,
        "platform": name,
        "message": "Cần video_id (manifest Douyin) để đăng qua hàng đợi hiện tại.",
        "title": title,
        "caption": caption,
        **kwargs,
    }
