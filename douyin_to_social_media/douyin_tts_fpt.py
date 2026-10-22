"""FPT.AI Text-to-Speech — giọng miền rõ (leminh = nam Bắc).

Docs: https://docs.fpt.ai/docs/vi/speech/api/text-to-speech/
Đăng ký key: https://console.fpt.ai → thêm vào api_keys.txt (có thể nhiều key dự phòng):

  fpt_api_key: "KEY_CHINH"
  fpt_api_key: "KEY_DUPHONG_1"
  fpt_api_key: "KEY_DUPHONG_2"

Hoặc: fpt_api_key_2 / fpt_tts_key / fpt_api_keys: "k1,k2".

Khi một key lỗi (429 / hết quota / async 404 / timeout):
  → cooldown key đó → thử key kế tiếp.
Hết mọi key → FptRateLimitError → cascade Piper/Edge ở douyin_voice.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
FPT_URL = "https://api.fpt.ai/hmi/tts/v5"

# leminh = nam miền Bắc (ấm, phổ biến cho narration)
DEFAULT_FPT_VOICE = "leminh"
# Free tier 429 / async chết thường không phục hồi nhanh — cooldown từng key.
_RATE_LIMIT_COOLDOWN_SEC = 30 * 60
_SOFT_FAIL_COOLDOWN_SEC = 10 * 60  # 404/timeout async — thử lại sau, ngắn hơn 429
# key → unix timestamp hết cooldown
_key_cooldown_until: dict[str, float] = {}
_KEY_NAME_RE = re.compile(r"^(?:fpt_api_key(?:_\d+)?|fpt_tts_key(?:_\d+)?|fpt_api_keys)$", re.I)


class FptRateLimitError(RuntimeError):
    """Hết key FPT khả dụng (429/quota/async fail). Caller cascade Piper/Edge."""


class FptKeyFailedError(RuntimeError):
    """Một key cụ thể lỗi — synthesize_to_mp3 sẽ thử key tiếp theo."""


def _parse_key_value(raw: str) -> list[str]:
    """Tách một hoặc nhiều key từ value (hỗ trợ CSV)."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return []
    parts = [p.strip().strip('"').strip("'") for p in text.split(",")]
    return [p for p in parts if p]


def load_fpt_keys() -> list[str]:
    """Đọc mọi fpt_api_key / fpt_tts_key / fpt_api_keys từ api_keys.txt (giữ thứ tự, bỏ trùng)."""
    try:
        raw = (PROJECT / "api_keys.txt").read_text(encoding="utf-8")
    except OSError:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        name, value = line.split(":", 1)
        name = name.strip()
        if not _KEY_NAME_RE.match(name):
            continue
        for key in _parse_key_value(value):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def load_fpt_key() -> str:
    """Key đang dùng được (còn hạn / chưa cooldown). Tương thích API cũ."""
    ready = available_keys()
    if ready:
        return ready[0]
    all_keys = load_fpt_keys()
    return all_keys[0] if all_keys else ""


def configured() -> bool:
    return bool(load_fpt_keys())


def _key_ready(key: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return now >= float(_key_cooldown_until.get(key) or 0)


def available_keys() -> list[str]:
    """Các key chưa bị cooldown."""
    now = time.time()
    return [k for k in load_fpt_keys() if _key_ready(k, now)]


def available() -> bool:
    """Còn ít nhất một key dùng được (không cooldown)."""
    return bool(available_keys())


def mark_rate_limited(
    cooldown_sec: float = _RATE_LIMIT_COOLDOWN_SEC,
    *,
    key: str | None = None,
) -> None:
    """Đánh dấu một key (hoặc tất cả) vào cooldown."""
    until = time.time() + max(60.0, float(cooldown_sec))
    if key:
        _key_cooldown_until[key] = until
        return
    for item in load_fpt_keys():
        _key_cooldown_until[item] = until


def _looks_quota_message(text: str) -> bool:
    low = (text or "").lower()
    return any(
        token in low
        for token in (
            "rate limit",
            "quota",
            "exceeded",
            "limit exceeded",
            "too many",
            "hết lượt",
            "het luot",
        )
    )


def _synthesize_with_key(
    text: str,
    out_mp3: Path,
    *,
    key: str,
    voice: str,
    speed: str,
    timeout_sec: float,
) -> Path:
    headers = {
        "api_key": key,
        "api-key": key,  # một số tài liệu dùng dạng này
        "voice": voice,
        "speed": str(speed),
        "format": "mp3",
        "Cache-Control": "no-cache",
    }
    data = None
    # Free quota: 429 ngay → bỏ key, không spam retry cùng key.
    for attempt in range(2):
        resp = requests.post(FPT_URL, headers=headers, data=text.encode("utf-8"), timeout=60)
        body = (resp.text or "")[:220]
        if resp.status_code == 429 or (resp.status_code == 200 and _looks_quota_message(body)):
            mark_rate_limited(key=key)
            raise FptKeyFailedError(f"HTTP {resp.status_code} quota/rate-limit: {body}")
        if resp.status_code in {401, 403}:
            mark_rate_limited(key=key, cooldown_sec=_RATE_LIMIT_COOLDOWN_SEC)
            raise FptKeyFailedError(f"HTTP {resp.status_code} key bị từ chối: {body}")
        if resp.status_code >= 400:
            # Lỗi tạm (5xx) — thử lại 1 lần rồi chuyển key
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(2)
                continue
            mark_rate_limited(key=key, cooldown_sec=_SOFT_FAIL_COOLDOWN_SEC)
            raise FptKeyFailedError(f"HTTP {resp.status_code}: {body}")
        try:
            data = resp.json()
        except ValueError as exc:
            mark_rate_limited(key=key, cooldown_sec=_SOFT_FAIL_COOLDOWN_SEC)
            raise FptKeyFailedError(f"Không trả JSON: {body}") from exc
        break
    else:
        mark_rate_limited(key=key)
        raise FptKeyFailedError("POST thất bại sau retry")

    # Một số bản trả error trong JSON dù HTTP 200
    err_code = (data or {}).get("error")
    err_msg = str((data or {}).get("message") or (data or {}).get("error") or "")
    if err_code not in (None, 0, "0") or _looks_quota_message(err_msg):
        mark_rate_limited(key=key)
        raise FptKeyFailedError(f"FPT JSON lỗi: {err_msg or data}")

    async_url = (data or {}).get("async") or (data or {}).get("async_url") or ""
    if not async_url:
        mark_rate_limited(key=key, cooldown_sec=_SOFT_FAIL_COOLDOWN_SEC)
        raise FptKeyFailedError(f"Thiếu async URL: {data}")

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    last_err = ""
    saw_404 = 0
    while time.time() < deadline:
        try:
            audio = requests.get(async_url, timeout=30)
            size = len(audio.content or b"")
            if audio.status_code == 200 and audio.content and size > 500:
                ctype = (audio.headers.get("Content-Type") or "").lower()
                if "json" in ctype or audio.content[:1] == b"{":
                    # Async chưa sẵn / JSON lỗi
                    preview = (audio.content[:160] or b"").decode("utf-8", errors="ignore")
                    if _looks_quota_message(preview):
                        mark_rate_limited(key=key)
                        raise FptKeyFailedError(f"Async JSON quota: {preview}")
                    time.sleep(1.2)
                    continue
                out_mp3.write_bytes(audio.content)
                return out_mp3
            last_err = f"HTTP {audio.status_code} size={size}"
            # 404 nhỏ (thường ~100–200B) = link chết / hết quota ẩn → chuyển key sớm
            if audio.status_code == 404:
                saw_404 += 1
                if saw_404 >= 4:
                    mark_rate_limited(key=key, cooldown_sec=_SOFT_FAIL_COOLDOWN_SEC)
                    raise FptKeyFailedError(f"Async 404 liên tục ({last_err})")
        except FptKeyFailedError:
            raise
        except requests.RequestException as exc:
            last_err = exc.__class__.__name__
        time.sleep(1.5)

    mark_rate_limited(key=key, cooldown_sec=_SOFT_FAIL_COOLDOWN_SEC)
    raise FptKeyFailedError(f"Hết thời gian chờ file audio ({last_err})")


def synthesize_to_mp3(
    text: str,
    out_mp3: Path,
    *,
    voice: str = DEFAULT_FPT_VOICE,
    speed: str = "0",
    timeout_sec: float = 90.0,
) -> Path:
    """Gọi FPT TTS; xoay lần lượt mọi key sẵn sàng khi key trước lỗi."""
    keys = load_fpt_keys()
    if not keys:
        raise RuntimeError(
            "Chưa có fpt_api_key trong api_keys.txt. "
            "Đăng ký miễn phí tại https://console.fpt.ai rồi thêm dòng: "
            'fpt_api_key: "YOUR_KEY"  (có thể thêm nhiều dòng dự phòng)'
        )
    ready = available_keys()
    if not ready:
        raise FptRateLimitError(
            f"FPT TTS: cả {len(keys)} key đang cooldown. Dùng Piper/Edge tạm thời."
        )

    text = (text or "").strip()
    if len(text) < 3:
        text = "Xin chào."

    errors: list[str] = []
    # Luôn đọc lại danh sách sẵn sàng (key vừa cooldown sẽ bị bỏ qua)
    tried: set[str] = set()
    while True:
        ready = [k for k in available_keys() if k not in tried]
        if not ready:
            break
        key = ready[0]
        tried.add(key)
        try:
            return _synthesize_with_key(
                text,
                out_mp3,
                key=key,
                voice=voice,
                speed=speed,
                timeout_sec=timeout_sec,
            )
        except FptKeyFailedError as exc:
            errors.append(f"{key[:8]}…: {exc}")
            continue

    raise FptRateLimitError(
        "FPT TTS hết key khả dụng. "
        + (" | ".join(errors) if errors else "Thử lại sau hoặc thêm fpt_api_key dự phòng.")
    )
