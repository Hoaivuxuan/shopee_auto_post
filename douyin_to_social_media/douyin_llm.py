"""LLM cascade: Groq → Gemini → Ollama (giảm tải qwen3:4b local).

Khóa đọc từ api_keys.txt ở root project (cùng pattern suggest.py).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

import douyin_quality

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
GEMINI_PATH = ROOT / "data" / "gemini.json"
GROQ_MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-20b")
GEMINI_FALLBACKS = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-lite-latest")
OLLAMA_MODEL = os.environ.get("OLLAMA_SUGGEST_MODEL", "qwen3:4b").strip() or "qwen3:4b"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def provider_keys() -> dict:
    found = {}
    try:
        raw = (PROJECT / "api_keys.txt").read_text(encoding="utf-8")
    except OSError:
        raw = ""
    for line in raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        name, value = line.split(":", 1)
        found[name.strip()] = value.strip().strip('"').strip("'")
    file_conf = _read_json(GEMINI_PATH, {})
    model = str(file_conf.get("model") or "gemini-flash-latest").strip() or "gemini-flash-latest"
    gemini = found.get("gemini_api_key") or str(file_conf.get("api_key") or "").strip()
    return {"gemini": gemini, "groq": found.get("groq_api_key") or "", "model": model}


def configured() -> bool:
    keys = provider_keys()
    return bool(keys["gemini"] or keys["groq"])


def _hide(message: str) -> str:
    keys = provider_keys()
    for secret in (keys["gemini"], keys["groq"]):
        if secret:
            message = message.replace(secret, "***")
    return message[:400]


def _strip_fence(text: str) -> str:
    raw = (text or "").strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()


def parse_json_object(text: str) -> dict:
    raw = _strip_fence(text)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM không trả về JSON object.")
    return data


def _gemini_models(primary: str) -> list[str]:
    names = []
    for name in (primary, *GEMINI_FALLBACKS):
        name = (name or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _gemini_text(data: dict) -> str:
    parts = data["candidates"][0]["content"]["parts"]
    texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
    if not texts:
        raise KeyError("text")
    return texts[-1]


def _ask_groq(prompt: str, *, temperature: float = 0.2) -> tuple[str, str]:
    key = provider_keys()["groq"]
    if not key:
        raise RuntimeError("Chưa có khóa Groq.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_error = "Groq không trả lời."
    for model in GROQ_MODELS:
        body = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=douyin_quality.LLM_GROQ_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"Không gọi được Groq: {exc.__class__.__name__}"
            continue
        if resp.status_code in (429, 500, 503):
            last_error = f"Groq đang bận (HTTP {resp.status_code})."
            continue
        if resp.status_code >= 400:
            last_error = f"Groq từ chối yêu cầu (HTTP {resp.status_code})."
            continue
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            return str(content or ""), model
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            last_error = "Groq không trả về nội dung đọc được."
    raise RuntimeError(last_error)


def _ask_gemini(prompt: str, *, temperature: float = 0.2) -> tuple[str, str]:
    conf = provider_keys()
    if not conf["gemini"]:
        raise RuntimeError("Chưa có khóa Gemini.")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    headers = {"Content-Type": "application/json", "X-goog-api-key": conf["gemini"]}
    last_error = "Không gọi được Gemini."
    for model in _gemini_models(conf["model"]):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=douyin_quality.LLM_GEMINI_TIMEOUT,
                )
            except requests.RequestException as exc:
                last_error = f"Không gọi được Gemini: {exc.__class__.__name__}"
                time.sleep(1 + attempt)
                continue
            if resp.status_code in (429, 500, 503):
                last_error = f"Gemini đang bận (HTTP {resp.status_code})."
                time.sleep(1 + attempt)
                continue
            if resp.status_code >= 400:
                last_error = f"Gemini từ chối yêu cầu (HTTP {resp.status_code})."
                break
            try:
                return _gemini_text(resp.json()), model
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                last_error = "Gemini không trả về nội dung đọc được."
                break
    raise RuntimeError(last_error)


def _ask_ollama(prompt: str, *, temperature: float = 0.2) -> tuple[str, str]:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_predict": douyin_quality.LLM_OLLAMA_NUM_PREDICT,
        },
    }
    try:
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=douyin_quality.LLM_OLLAMA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Không gọi được Ollama: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"Ollama từ chối yêu cầu (HTTP {resp.status_code}).")
    try:
        text = str((resp.json() or {}).get("response") or "")
        return text, OLLAMA_MODEL
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Ollama không trả về nội dung đọc được.") from exc


def chat_json(prompt: str, *, temperature: float = 0.2) -> dict:
    """Gọi cascade Groq → Gemini → Ollama. Trả về {data, provider, model, errors}."""
    errors: list[str] = []
    for name, fn in (
        ("groq", _ask_groq),
        ("gemini", _ask_gemini),
        ("ollama", _ask_ollama),
    ):
        try:
            text, model = fn(prompt, temperature=temperature)
            data = parse_json_object(text)
            return {
                "data": data,
                "provider": name,
                "model": model,
                "errors": errors,
                "raw": text,
            }
        except Exception as exc:  # noqa: BLE001 — cascade cần nuốt lỗi từng provider
            errors.append(_hide(f"{name}: {exc}"))
    raise RuntimeError("LLM không trả lời. " + " | ".join(errors))


def smoke_test() -> dict:
    """Gọi 1 prompt ngắn để xác nhận key hoạt động."""
    prompt = (
        'Trả về đúng JSON object: {"ok": true, "ping": "pong"}. '
        "Không thêm chữ nào khác."
    )
    return chat_json(prompt, temperature=0)


if __name__ == "__main__":
    result = smoke_test()
    print(
        json.dumps(
            {
                "provider": result["provider"],
                "model": result["model"],
                "data": result["data"],
                "errors": result["errors"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
