"""Job nền: tạo video ngắn AI (ASR → highlight → TTS → phụ đề)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import progress

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "douyin" / "processed"

_LOCK = threading.Lock()
_JOB = {
    "running": False,
    "video_id": "",
    "message": "",
    "status": "",
    "error": "",
    "current_step": "",
}


def ai_dir(video_id: str) -> Path:
    return PROCESSED / str(video_id or "")


def ai_output_path(video_id: str) -> Path | None:
    path = ai_dir(video_id) / "output_ai.mp4"
    return path if path.is_file() else None


def read_meta(video_id: str) -> dict:
    path = ai_dir(video_id) / "meta.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def job_status() -> dict:
    with _LOCK:
        live = dict(_JOB)
    meta = read_meta(live.get("video_id") or "") if live.get("running") else {}
    payload = progress.progress_payload(
        kind="ai",
        status="running" if live.get("running") else (live.get("status") or "idle"),
        message=meta.get("message") or live.get("message") or "",
        current_step=meta.get("current_step") or live.get("current_step") or "",
        steps=meta.get("steps") if isinstance(meta.get("steps"), dict) else progress.empty_steps(progress.AI_STEP_DEFS),
        error=live.get("error") or "",
        started_at=meta.get("started_at") or live.get("started_at") or "",
        finished_at=meta.get("finished_at") or "",
    )
    live.update(payload)
    return live


def status_for(video_id: str) -> dict:
    """Trạng thái AI cho một video (job đang chạy hoặc meta đã lưu)."""
    video_id = str(video_id or "")
    with _LOCK:
        live = dict(_JOB)
    meta = read_meta(video_id)
    out = ai_output_path(video_id)
    steps = meta.get("steps") if isinstance(meta.get("steps"), dict) else {}
    current = str(meta.get("current_step") or "")

    if live.get("running") and live.get("video_id") == video_id:
        base = progress.progress_payload(
            kind="ai",
            status="running",
            message=meta.get("message") or live.get("message") or "Đang tạo video ngắn…",
            current_step=current or live.get("current_step") or "",
            steps=steps or progress.empty_steps(progress.AI_STEP_DEFS),
            error="",
        )
        base.update({
            "has_ai": bool(out),
            "output": str(out) if out else "",
            "providers": meta.get("providers") or {},
            "finished_at": "",
            "started_at": meta.get("started_at") or live.get("started_at") or "",
        })
        return base

    if meta.get("status") == "error":
        base = progress.progress_payload(
            kind="ai",
            status="error",
            message=meta.get("message") or "Lỗi tạo video ngắn",
            current_step=current,
            steps=steps,
            error=meta.get("message") or "",
            finished_at=meta.get("finished_at") or "",
        )
        base.update({
            "has_ai": bool(out),
            "output": str(out) if out else "",
            "providers": meta.get("providers") or {},
        })
        return base

    if out and meta.get("status") == "done":
        base = progress.progress_payload(
            kind="ai",
            status="done",
            message=meta.get("message") or "Đã có video ngắn",
            current_step="",
            steps=steps,
            started_at=meta.get("started_at") or "",
            finished_at=meta.get("finished_at") or "",
        )
        base.update({
            "has_ai": True,
            "output": str(out),
            "providers": meta.get("providers") or {},
            "duration": ((meta.get("steps") or {}).get("cut") or {}).get("duration"),
        })
        return base

    if out:
        base = progress.progress_payload(
            kind="ai",
            status="done",
            message="Đã có video ngắn",
            steps=steps,
            started_at=meta.get("started_at") or "",
            finished_at=meta.get("finished_at") or "",
        )
        base.update({
            "has_ai": True,
            "output": str(out),
            "providers": meta.get("providers") or {},
        })
        return base

    base = progress.progress_payload(kind="ai", status="idle", message="", steps=steps)
    base.update({
        "has_ai": False,
        "output": "",
        "providers": {},
        "finished_at": "",
    })
    return base


def enrich_videos(videos: list[dict]) -> list[dict]:
    with _LOCK:
        live = dict(_JOB)
    for item in videos or []:
        if not isinstance(item, dict):
            continue
        vid = str(item.get("id") or "")
        info = status_for(vid)
        if live.get("running") and live.get("video_id") == vid:
            meta = read_meta(vid)
            info["status"] = "running"
            info["message"] = meta.get("message") or live.get("message") or info["message"]
            info["current_step"] = meta.get("current_step") or info.get("current_step") or ""
            info["steps"] = progress.serialize_steps(
                progress.AI_STEP_DEFS,
                meta.get("steps") if isinstance(meta.get("steps"), dict) else {},
                current_step=info["current_step"],
                overall="running",
            )
        item["ai"] = info
    return videos


def _run(video_id: str, force: bool) -> None:
    import douyin_process

    try:
        with _LOCK:
            _JOB.update(
                running=True,
                video_id=video_id,
                status="running",
                error="",
                message="Đang tạo video ngắn AI…",
                current_step="",
            )
        meta = douyin_process.process_video(video_id, force=force)
        with _LOCK:
            _JOB.update(
                status=meta.get("status") or "done",
                message=meta.get("message") or "Xong",
                error="" if meta.get("status") == "done" else (meta.get("message") or ""),
                current_step="",
            )
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            _JOB.update(status="error", message=str(exc)[:400], error=str(exc)[:400])
    finally:
        with _LOCK:
            _JOB["running"] = False


def _bootstrap_meta(video_id: str, message: str = "Chuẩn bị tạo video ngắn…") -> None:
    """Ghi meta.json ngay khi bấm tạo — UI thấy checklist trước khi ASR bắt đầu."""
    from datetime import datetime, timedelta, timezone

    folder = ai_dir(video_id)
    folder.mkdir(parents=True, exist_ok=True)
    steps = progress.empty_steps(progress.AI_STEP_DEFS)
    first = progress.AI_STEP_DEFS[0][0]
    progress.begin_step(steps, first, detail=message)
    meta = {
        "video_id": video_id,
        "status": "running",
        "started_at": datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "current_step": first,
        "steps": steps,
    }
    path = folder / "meta.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def start_process(video_id: str, *, force: bool = False) -> dict:
    video_id = str(video_id or "").strip()
    if not video_id:
        raise RuntimeError("Thiếu id video.")
    import douyin_poster

    if not douyin_poster.media_path(video_id):
        raise RuntimeError("Không thấy file video Douyin trên máy.")
    with _LOCK:
        if _JOB["running"]:
            raise RuntimeError(
                f"Đang tạo video ngắn cho {_JOB.get('video_id') or 'video khác'}. Hãy đợi xong."
            )
        first = progress.AI_STEP_DEFS[0][0]
        from datetime import datetime, timedelta, timezone

        _JOB.update(
            running=True,
            video_id=video_id,
            status="running",
            error="",
            message="Chuẩn bị tạo video ngắn…",
            current_step=first,
            started_at=datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S"),
        )
    try:
        _bootstrap_meta(video_id, "Chuẩn bị tạo video ngắn…")
    except Exception:
        pass
    threading.Thread(target=_run, args=(video_id, force), daemon=True).start()
    return job_status()
