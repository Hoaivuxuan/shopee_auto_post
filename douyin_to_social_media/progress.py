"""Tiến trình từng bước — dùng chung Tạo video ngắn & Đăng nền tảng."""

from __future__ import annotations

from typing import Any, Callable

# id → nhãn hiển thị (thứ tự = pipeline)
AI_STEP_DEFS: list[tuple[str, str]] = [
    ("asr", "ASR — nhận dạng tiếng Trung"),
    ("highlight", "Chọn highlight"),
    ("cut", "Cắt / ghép video"),
    ("script", "Viết kịch bản tiếng Việt"),
    ("voice", "TTS lồng tiếng"),
    ("mux", "Ghép audio vào video"),
    ("subtitle", "Burn phụ đề"),
]

PUBLISH_STEP_DEFS: dict[str, list[tuple[str, str]]] = {
    "facebook": [
        ("check", "Kiểm tra token & video ngắn AI"),
        ("caption", "Chuẩn bị nội dung tiếng Việt"),
        ("auth", "Xác thực Page Access Token"),
        ("upload", "Tải video lên Facebook"),
        ("permalink", "Lấy link bài đăng"),
    ],
    "youtube": [
        ("check", "Kiểm tra OAuth & video ngắn AI"),
        ("caption", "Chuẩn bị tiêu đề / mô tả"),
        ("upload", "Upload YouTube Shorts"),
        ("done", "Xác nhận đã đăng"),
    ],
    "tiktok": [
        ("check", "Kiểm tra ủy quyền & video ngắn AI"),
        ("caption", "Chuẩn bị caption TikTok"),
        ("init", "Khởi tạo Direct Post"),
        ("upload", "Gửi file lên TikTok"),
        ("status", "Kiểm tra trạng thái publish"),
        ("done", "Hoàn tất"),
    ],
    "instagram": [
        ("check", "Kiểm tra IG Professional & video AI"),
        ("caption", "Chuẩn bị caption Reels"),
        ("container", "Tạo container Reels"),
        ("transfer", "Upload / kéo video"),
        ("process", "Chờ Instagram xử lý"),
        ("publish", "Publish Reels"),
        ("done", "Lấy permalink"),
    ],
}


def empty_steps(defs: list[tuple[str, str]]) -> dict[str, dict]:
    return {
        key: {"status": "pending", "label": label, "detail": "", "error": ""}
        for key, label in defs
    }


def defs_for(kind: str, target: str = "") -> list[tuple[str, str]]:
    if kind == "ai":
        return list(AI_STEP_DEFS)
    return list(PUBLISH_STEP_DEFS.get(target) or PUBLISH_STEP_DEFS["facebook"])


def mark_step(
    steps: dict[str, dict],
    step_id: str,
    *,
    status: str,
    detail: str = "",
    error: str = "",
    label: str = "",
) -> dict[str, dict]:
    row = dict(steps.get(step_id) or {})
    if label:
        row["label"] = label
    row["status"] = status
    if detail:
        row["detail"] = str(detail)[:400]
    if error:
        row["error"] = str(error)[:400]
    elif status != "error":
        row["error"] = ""
    steps[step_id] = row
    return steps


def begin_step(steps: dict[str, dict], step_id: str, *, detail: str = "") -> dict[str, dict]:
    """Đánh dấu bước hiện tại đang chạy; các bước trước còn pending giữ nguyên."""
    return mark_step(steps, step_id, status="running", detail=detail)


def finish_step(steps: dict[str, dict], step_id: str, *, detail: str = "") -> dict[str, dict]:
    return mark_step(steps, step_id, status="done", detail=detail)


def fail_step(steps: dict[str, dict], step_id: str, *, error: str) -> dict[str, dict]:
    return mark_step(steps, step_id, status="error", error=error)


def serialize_steps(
    defs: list[tuple[str, str]],
    steps: dict[str, Any] | None,
    *,
    current_step: str = "",
    overall: str = "",
    error: str = "",
) -> list[dict]:
    """Trả về danh sách bước có thứ tự cho UI."""
    raw = steps if isinstance(steps, dict) else {}
    # Khi đang chạy mà chưa ghi current_step → coi bước đầu chưa xong là bước hiện tại
    if overall == "running" and not current_step and defs:
        for key, _label in defs:
            row = raw.get(key) if isinstance(raw.get(key), dict) else {}
            if row and "status" not in row and any(k != "status" for k in row):
                continue  # đã có dữ liệu = coi như done
            st = str(row.get("status") or "pending")
            if st not in ("done", "error", "skipped"):
                current_step = key
                break
        if not current_step:
            current_step = defs[0][0]

    out: list[dict] = []
    seen_current = False
    for key, label in defs:
        row = raw.get(key) if isinstance(raw.get(key), dict) else {}
        # Hỗ trợ meta AI cũ: steps[key] chỉ là dict chi tiết không có status
        if row and "status" not in row and any(k != "status" for k in row):
            status = "done"
            detail = _brief(row)
        else:
            status = str(row.get("status") or "pending")
            detail = str(row.get("detail") or "")
            if not detail and status == "done":
                detail = _brief(row)
        err = str(row.get("error") or "")
        if overall == "error" and current_step == key and not err:
            err = error
            status = "error"
        if overall == "running" and key == current_step:
            status = "running"
            seen_current = True
        elif overall == "running" and not seen_current and status == "pending":
            # các bước trước current mà vẫn pending → đã xong ngầm (hoặc chưa tới)
            pass
        elif overall == "running" and seen_current and status == "pending":
            pass
        if overall == "done" and status == "pending":
            status = "done"
        out.append({
            "id": key,
            "label": str(row.get("label") or label),
            "status": status if status in ("pending", "running", "done", "error", "skipped") else "pending",
            "detail": detail[:400],
            "error": err[:400],
        })
    return out


def _brief(row: dict) -> str:
    parts = []
    for key in ("provider", "model", "voice", "duration", "segments", "clips", "lines", "parts", "accent"):
        if key in row and row[key] not in (None, "", []):
            parts.append(f"{key}={row[key]}")
    return ", ".join(parts)[:400]


class PublishTracker:
    """Theo dõi bước đăng: cập nhật job live + bản ghi posts."""

    def __init__(
        self,
        *,
        target: str,
        lock,
        job: dict,
        save_record: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.target = target
        self.lock = lock
        self.job = job
        self.save_record = save_record
        self.defs = defs_for("publish", target)
        self.steps = empty_steps(self.defs)
        self.video_id = ""
        self.current_step = ""

    def reset(self, video_id: str, title: str = "", message: str = "") -> None:
        self.video_id = str(video_id)
        self.steps = empty_steps(self.defs)
        self.current_step = ""
        with self.lock:
            self.job.update(
                running=True,
                video_id=self.video_id,
                title=title or self.job.get("title") or "",
                message=message or "Chuẩn bị đăng…",
                status="running",
                current_step="",
                error="",
                steps=dict(self.steps),
                progress=self.snapshot(),
            )
        self._persist(status="posting", message=message or "Chuẩn bị đăng…")

    def begin(self, step_id: str, message: str = "") -> None:
        self.current_step = step_id
        begin_step(self.steps, step_id, detail=message)
        with self.lock:
            self.job.update(
                message=message or step_id,
                current_step=step_id,
                status="running",
                steps=dict(self.steps),
                progress=self.snapshot(),
            )
        self._persist(status="posting", message=message or step_id)

    def ok(self, step_id: str, detail: str = "") -> None:
        finish_step(self.steps, step_id, detail=detail)
        with self.lock:
            self.job["steps"] = dict(self.steps)
            self.job["progress"] = self.snapshot()
        self._persist(status="posting")

    def fail(self, step_id: str, error: str) -> dict:
        fail_step(self.steps, step_id or self.current_step or (self.defs[0][0] if self.defs else "check"), error=error)
        snap = self.snapshot(status="error", message=error, error=error)
        with self.lock:
            self.job.update(
                running=False,
                message=error[:400],
                status="error",
                error=error[:400],
                current_step=step_id or self.current_step,
                steps=dict(self.steps),
                progress=snap,
            )
        self._persist(status="error", message=error, error=error, finished=True)
        return snap

    def succeed(self, *, message: str, permalink: str = "", remote_id: str = "") -> dict:
        # Đánh dấu mọi bước còn pending/running thành done
        for key, _ in self.defs:
            st = (self.steps.get(key) or {}).get("status")
            if st in ("pending", "running"):
                finish_step(self.steps, key)
        snap = self.snapshot(
            status="done",
            message=message,
            permalink=permalink,
            remote_id=remote_id,
        )
        with self.lock:
            self.job.update(
                running=False,
                message=message,
                status="done",
                error="",
                current_step="",
                steps=dict(self.steps),
                progress=snap,
            )
        self._persist(
            status="published",
            message=message,
            permalink=permalink,
            remote_id=remote_id,
            finished=True,
        )
        return snap

    def snapshot(
        self,
        *,
        status: str = "",
        message: str = "",
        error: str = "",
        permalink: str = "",
        remote_id: str = "",
    ) -> dict:
        with self.lock:
            job_status = status or self.job.get("status") or ("running" if self.job.get("running") else "idle")
            job_message = message or self.job.get("message") or ""
            job_error = error or self.job.get("error") or ""
        return progress_payload(
            kind="publish",
            target=self.target,
            status=job_status,
            message=job_message,
            current_step=self.current_step,
            steps=self.steps,
            error=job_error,
            permalink=permalink,
            remote_id=remote_id,
        )

    def _persist(
        self,
        *,
        status: str,
        message: str = "",
        error: str = "",
        permalink: str = "",
        remote_id: str = "",
        finished: bool = False,
    ) -> None:
        if not self.save_record or not self.video_id:
            return
        payload = {
            "status": status,
            "error": error[:400] if error else "",
            "permalink": permalink,
            "progress": self.snapshot(status="error" if status == "error" else ("done" if status == "published" else "running"), message=message, error=error, permalink=permalink, remote_id=remote_id),
        }
        if remote_id:
            payload["remote_id"] = remote_id
        if finished:
            from datetime import datetime, timedelta, timezone
            payload["posted_at"] = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S") if status == "published" else ""
        self.save_record(self.video_id, payload)


def progress_payload(
    *,
    kind: str,
    target: str = "",
    status: str = "idle",
    message: str = "",
    current_step: str = "",
    steps: dict | None = None,
    error: str = "",
    finished_at: str = "",
    started_at: str = "",
    permalink: str = "",
    remote_id: str = "",
) -> dict:
    defs = defs_for(kind, target)
    return {
        "kind": kind,
        "target": target,
        "status": status,
        "message": message,
        "current_step": current_step,
        "error": error,
        "started_at": started_at,
        "finished_at": finished_at,
        "permalink": permalink,
        "remote_id": remote_id,
        "steps": serialize_steps(defs, steps, current_step=current_step, overall=status, error=error),
        "step_defs": [{"id": k, "label": lab} for k, lab in defs],
    }
