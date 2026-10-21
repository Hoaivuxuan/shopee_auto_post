"""FPT.AI Text-to-Speech — giọng miền rõ (leminh = nam Bắc).

Docs: https://docs.fpt.ai/docs/vi/speech/api/text-to-speech/
Đăng ký key: https://console.fpt.ai → thêm vào api_keys.txt:
  fpt_api_key: "...."
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
FPT_URL = "https://api.fpt.ai/hmi/tts/v5"

# leminh = nam miền Bắc (ấm, phổ biến cho narration)
DEFAULT_FPT_VOICE = "leminh"


def load_fpt_key() -> str:
    found = {}
    try:
        raw = (PROJECT / "api_keys.txt").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        name, value = line.split(":", 1)
        found[name.strip()] = value.strip().strip('"').strip("'")
    return found.get("fpt_api_key") or found.get("fpt_tts_key") or ""


def configured() -> bool:
    return bool(load_fpt_key())


def synthesize_to_mp3(
    text: str,
    out_mp3: Path,
    *,
    voice: str = DEFAULT_FPT_VOICE,
    speed: str = "0",
    timeout_sec: float = 90.0,
) -> Path:
    """Gọi FPT TTS, poll link async rồi ghi file mp3."""
    key = load_fpt_key()
    if not key:
        raise RuntimeError(
            "Chưa có fpt_api_key trong api_keys.txt. "
            "Đăng ký miễn phí tại https://console.fpt.ai rồi thêm dòng: "
            'fpt_api_key: "YOUR_KEY"'
        )
    text = (text or "").strip()
    if len(text) < 3:
        text = "Xin chào."
    headers = {
        "api_key": key,
        "api-key": key,  # một số tài liệu dùng dạng này
        "voice": voice,
        "speed": str(speed),
        "format": "mp3",
        "Cache-Control": "no-cache",
    }
    data = None
    last_http = ""
    for attempt in range(8):
        resp = requests.post(FPT_URL, headers=headers, data=text.encode("utf-8"), timeout=60)
        if resp.status_code == 429:
            wait = min(60, 5 * (attempt + 1))
            last_http = f"HTTP 429: {resp.text[:120]}"
            time.sleep(wait)
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"FPT TTS HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"FPT TTS không trả JSON: {resp.text[:200]}") from exc
        break
    else:
        raise RuntimeError(f"FPT TTS rate-limit liên tục ({last_http})")

    # error == 0 là thành công trên một số bản; hoặc có field async
    async_url = (data or {}).get("async") or (data or {}).get("async_url") or ""
    if not async_url:
        err = (data or {}).get("message") or (data or {}).get("error") or data
        raise RuntimeError(f"FPT TTS lỗi: {err}")

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    last_err = ""
    while time.time() < deadline:
        try:
            audio = requests.get(async_url, timeout=30)
            if audio.status_code == 200 and audio.content and len(audio.content) > 500:
                ctype = (audio.headers.get("Content-Type") or "").lower()
                if "json" in ctype or audio.content[:1] == b"{":
                    time.sleep(1.2)
                    continue
                out_mp3.write_bytes(audio.content)
                return out_mp3
            last_err = f"HTTP {audio.status_code} size={len(audio.content or b'')}"
        except requests.RequestException as exc:
            last_err = exc.__class__.__name__
        time.sleep(1.5)
    raise RuntimeError(f"FPT TTS hết thời gian chờ file audio ({last_err})")
