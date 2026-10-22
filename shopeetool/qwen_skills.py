"""Đọc hướng dẫn viết caption và comment cho qwen3:4b."""
import os
import re

from .paths import app_dir, resource_path

_CACHE = {}
# Số tiền. Không đụng chữ "giá" trong "giá đỡ", "giá sách".
_MONEY = re.compile(
    r"\bgiá\s*\d[\d.\s]*(?:₫|đ|k|vnđ|vnd)?"
    r"|₫"
    r"|\b(?:vnđ|vnd)\b"
    r"|\d[\d.\s]*\s*đ\b"
    r"|\d+\s*k\b"
    r"|\d{1,3}(?:\.\d{3})+"
    r"|\b\d+\s*(?:ngàn|nghìn|triệu|đồng)\b",
    re.I,
)


def mentions_price(text):
    return bool(_MONEY.search(text or ""))


def hide_prices(text):
    cleaned = _MONEY.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip(" -–,.")


def chat_prompt(system, user, starter):
    return (
        "<|im_start|>system\n"
        f"{system.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
        "<think>\n\n</think>\n"
        f"{starter}"
    )


def skill_text(filename, fallback):
    """Lấy phần hướng dẫn sau dòng ---. File thiếu hoặc rỗng thì dùng câu sẵn."""
    path = _find(filename)
    if not path:
        return fallback
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return fallback
    cached = _CACHE.get(filename)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        with open(path, encoding="utf-8") as handle:
            body = _body(handle.read())
    except OSError:
        return fallback
    if len(body) < 40:
        return fallback
    _CACHE[filename] = (stamp, body)
    return body


def _find(filename):
    rel = os.path.join("qwen_skills", filename)
    for path in (os.path.join(app_dir(), rel), resource_path(rel)):
        if path and os.path.isfile(path):
            return path
    return ""


def _body(raw):
    text = (raw or "").replace("\r\n", "\n")
    if "\n---\n" in text:
        text = text.split("\n---\n", 1)[1]
    return text.strip()
