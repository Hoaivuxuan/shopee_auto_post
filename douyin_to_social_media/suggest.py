"""Gợi ý sản phẩm Shopee khớp với một Shorts.

Lọc ứng viên trong kho products_affiliate.json. Qwen trên máy và Groq
cùng chấm; Gemini chỉ được gọi khi cả hai không trả lời, để khỏi dồn
tải vào một khóa. Kết quả lưu ở data/suggestions.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = ROOT / "data"
MANIFEST_PATH = DATA / "manifest.json"
CACHE_PATH = DATA / "suggestions.json"
AUTO_PATH = DATA / "suggest_auto.json"
GEMINI_PATH = DATA / "gemini.json"
VN_TZ = timezone(timedelta(hours=7))
MIN_SCORE = 70
SHORTLIST = 30
# gemini-flash-latest hay trả 503 khi quá tải. Chỉ dùng khi Qwen và Groq cùng lỗi.
FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-lite-latest")
GROQ_MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-20b")
QWEN_MODEL = "qwen3:4b"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")

if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poster import clean_title  # noqa: E402
from shopeetool.fb_group import STOPWORDS, _TOKEN_RE, content_tokens, fold  # noqa: E402
from shopeetool.paths import data_dir  # noqa: E402

# Từ kể chuyện trong tiêu đề, không phải tên món. Giữ lại sẽ kéo nhầm sản phẩm.
SKIP = {
    "cách", "người", "xưa", "nào", "thế", "chiếc", "sao", "tại", "lại", "trước",
    "tạo", "sau", "năm", "nghìn", "thống", "truyền", "bí", "mật", "đằng", "thuật",
    "hàng", "như", "này", "khi", "vì", "không", "được", "trong", "của", "với",
    "một", "các", "đã", "làm", "để", "từ", "cho", "và", "ra", "là", "những",
    "có", "qua", "nên", "từng", "ngay", "đầy", "bên", "thành", "ánh", "sáng",
    "sự", "thật", "về", "món", "nhưng", "bằng", "gọi", "nhà", "khác", "biệt",
    "đây", "chính", "phương", "pháp", "ban", "đầu", "chỉ", "còn", "thậm",
    "chí", "tính", "theo", "loại", "ở", "bị", "sẽ", "mà", "thì", "rất",
    "quá", "cũng", "đều", "nữa", "rồi", "hay", "hoặc", "đó", "kia", "em",
    "anh", "ạ", "ơi", "nhé", "hôm", "nay", "nếu", "mới", "cái", "chưa",
    "đang", "vào", "trên", "kỹ",
    "shorts", "short", "video", "youtube", "shortviral", "shortsviral",
    "kienthucthuvi", "khampha", "vuive", "kienthucbosung", "khamphathuvi",
    "viralvideo",
}
# Chữ quá rộng, không được đứng một mình để kéo sản phẩm vào danh sách.
WEAK = {
    "cây", "quả", "tách", "bền", "hiện", "đại", "hơn", "thô", "truyền",
    "thống", "cổ", "loại", "sinh", "phỏng", "bánh", "thể", "chục", "viết",
}

_LOCK = threading.RLock()
_ASK_LOCK = threading.Lock()
_AUTO_LOCK = threading.Lock()
_INDEX = {"stamp": None, "products": [], "docs": []}
_AUTO = {
    "enabled": False,
    "running": False,
    "index": 0,
    "total": 0,
    "round": 0,
    "video_id": "",
    "title": "",
    "message": "Tự động gợi ý đang tắt",
}


def now_str() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _provider_keys() -> dict:
    """Khóa lấy từ api_keys.txt. Model Gemini vẫn đọc ở data/gemini.json."""
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
    keys = _provider_keys()
    return bool(keys["gemini"] or keys["groq"])


def _hide_secret(message: str) -> str:
    keys = _provider_keys()
    for secret in (keys["gemini"], keys["groq"]):
        if secret:
            message = message.replace(secret, "***")
    return message[:300]


def _catalog():
    path = Path(data_dir()) / "products_affiliate.json"
    stamp = path.stat().st_mtime if path.is_file() else None
    if _INDEX["stamp"] == stamp and _INDEX["products"]:
        return _INDEX["products"], _INDEX["docs"]
    raw = _read_json(path, {})
    products = []
    docs = []
    for item in raw.get("products") or []:
        if not isinstance(item, dict):
            continue
        if not (item.get("short_link") or item.get("long_link")):
            continue
        products.append(item)
        docs.append(content_tokens(item.get("name") or ""))
    _INDEX.update(stamp=stamp, products=products, docs=docs)
    return products, docs


def _video(video_id: str) -> dict | None:
    manifest = _read_json(MANIFEST_PATH, {})
    for item in manifest.get("videos") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == video_id:
            return item
    return None


def _words(text: str) -> list[str]:
    """Giữ cả chữ 2 âm như 'lá', 'nha' để cụm 'quạt lá' không biến thành 'quạt'."""
    words = []
    for word in _TOKEN_RE.findall(fold(text)):
        if len(word) < 2 or word in SKIP or word in (STOPWORDS - {"nha"}):
            continue
        words.append(word)
    return words


def _bigrams(words: list[str]) -> list[str]:
    phrases = []
    for left, right in zip(words, words[1:]):
        if left in WEAK and right in WEAK:
            continue
        phrases.append(f"{left} {right}")
    return phrases


def _queries(title: str, description: str) -> tuple[set, set, set]:
    title_words = _words(clean_title(title))
    desc_words = _words(description or "")
    shared = set(_bigrams(title_words)) & set(_bigrams(desc_words))
    return set(title_words), set(desc_words), shared


def _row(product: dict) -> dict:
    return {
        "item_id": str(product.get("item_id") or ""),
        "name": str(product.get("name") or ""),
        "price_formatted": str(product.get("price_formatted") or ""),
        "category_name": str(product.get("category_name") or ""),
        "short_link": str(product.get("short_link") or product.get("long_link") or ""),
    }


def shortlist(title: str, description: str, limit: int = SHORTLIST) -> list[dict]:
    """Ứng viên phải khớp cả tiêu đề và mô tả.

    Cụm hai chữ có ở cả hai đoạn phải nằm liền trong tên sản phẩm. Không có cụm
    đó trong kho thì không lấy món chỉ trùng một chữ (quạt lá không thành quạt điện).
    """
    products, _docs = _catalog()
    title_query, desc_query, phrases = _queries(title, description)
    shared = (title_query & desc_query) - WEAK
    covered = set()
    for phrase in phrases:
        covered.update(phrase.split())
    loose = shared - covered
    if not phrases and not loose:
        return []
    names = [fold(item.get("name") or "") for item in products]
    scored = []
    for index, name in enumerate(names):
        exact = [phrase for phrase in phrases if phrase in name]
        words = set(_TOKEN_RE.findall(name))
        if exact:
            rank = 10 + len(exact) + len(words & shared)
        else:
            focus = loose if phrases else shared
            if not focus or not (words & focus):
                continue
            if title_query and not (words & title_query):
                continue
            if desc_query and not (words & desc_query):
                continue
            rank = len(words & shared) + len(words & title_query) + len(words & desc_query)
        sold = int(products[index].get("historical_sold") or products[index].get("sold") or 0)
        scored.append((rank, sold, index))
    scored.sort(key=lambda row: (-row[0], -row[1]))
    return [_row(products[index]) for _rank, _sold, index in scored[:limit]]


def _prompt(title: str, description: str, candidates: list[dict]) -> str:
    lines = []
    for item in candidates:
        name = item["name"] if len(item["name"]) <= 90 else item["name"][:87].rstrip() + "..."
        lines.append(
            f"- {item['item_id']} | {name} | {item['price_formatted']} | {item['category_name']}"
        )
    body = (description or "").strip() or "(không có mô tả)"
    _title_query, _desc_query, phrases = _queries(title, description)
    shared_words = sorted((_title_query & _desc_query) - WEAK)
    hint = ""
    if phrases:
        hint = "Cụm có ở cả tiêu đề và mô tả: " + ", ".join(sorted(phrases)) + ". "
    elif shared_words:
        hint = "Từ có ở cả tiêu đề và mô tả: " + ", ".join(shared_words) + ". "
    return (
        "Đọc cả tiêu đề và mô tả, rồi chọn sản phẩm đúng món video đang nói. "
        + hint
        + "Mô tả dùng để xác nhận loại món và để loại món chỉ trùng một chữ: "
        "quạt lá không phải quạt điện, giấy viết không phải giấy vệ sinh, "
        "mạch nha không phải yến mạch, giày không phải keo dán giày. "
        "Nếu không có món nào đúng loại, trả về danh sách rỗng.\n\n"
        f"Tiêu đề: {clean_title(title)}\n"
        f"Mô tả:\n{body}\n\n"
        "Ứng viên:\n"
        + "\n".join(lines)
        + "\n\nTrả về JSON đúng dạng "
        '{"products":[{"item_id":"...","score":85,"reason":"một câu tiếng Việt"}]}. '
        "score từ 0 đến 100 là độ tương thích. Chỉ giữ món từ 70 trở lên, tối đa 3, "
        "sắp theo score giảm dần. item_id phải nằm trong danh sách ứng viên."
    )


def _parse_products(text: str) -> list[dict]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    data = json.loads(raw)
    rows = data if isinstance(data, list) else (data.get("products") or [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _model_order(primary: str) -> list[str]:
    names = []
    for name in (primary, *FALLBACK_MODELS):
        name = (name or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _response_text(data: dict) -> str:
    parts = data["candidates"][0]["content"]["parts"]
    texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
    if not texts:
        raise KeyError("text")
    return texts[-1]


def _model_label(model: str) -> str:
    name = (model or "").strip()
    if name.startswith("qwen/"):
        return f"{name.split('/', 1)[1]} (Groq)"
    return name or "không rõ"


def _mark(items: list[dict], model: str) -> list[dict]:
    label = _model_label(model)
    for item in items:
        item["by"] = [label]
    return items


def _ask_qwen(prompt: str, candidates: list[dict]) -> list[dict]:
    model = os.environ.get("OLLAMA_SUGGEST_MODEL", QWEN_MODEL).strip() or QWEN_MODEL
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 280},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không gọi được Qwen: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"Qwen từ chối yêu cầu (HTTP {resp.status_code}).")
    try:
        text = str((resp.json() or {}).get("response") or "")
        return _mark(_keep_matches(_parse_products(text), candidates), model)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Qwen không trả về danh sách sản phẩm đọc được.") from exc


def _ask_groq(prompt: str, candidates: list[dict]) -> list[dict]:
    key = _provider_keys()["groq"]
    if not key:
        raise RuntimeError("Chưa có khóa Groq.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_error = "Groq không trả lời."
    for model in GROQ_MODELS:
        body = {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=40,
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
            return _mark(_keep_matches(_parse_products(content), candidates), model)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            last_error = "Groq không trả về danh sách sản phẩm đọc được."
    raise RuntimeError(last_error)


def _ask_gemini(prompt: str, candidates: list[dict]) -> list[dict]:
    conf = _provider_keys()
    if not conf["gemini"]:
        raise RuntimeError("Chưa có khóa Gemini.")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    headers = {"Content-Type": "application/json", "X-goog-api-key": conf["gemini"]}
    last_error = "Không gọi được Gemini."
    for model in _model_order(conf["model"]):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        attempts = 2 if model == conf["model"] else 1
        for attempt in range(attempts):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
            except requests.RequestException as exc:
                last_error = f"Không gọi được Gemini: {exc.__class__.__name__}"
                time.sleep(1 + attempt * 2)
                continue
            if resp.status_code in (429, 500, 503):
                last_error = f"Gemini đang bận (HTTP {resp.status_code})."
                time.sleep(1 + attempt * 2)
                continue
            if resp.status_code >= 400:
                last_error = f"Gemini từ chối yêu cầu (HTTP {resp.status_code})."
                break
            try:
                picked = _parse_products(_response_text(resp.json()))
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Gemini không trả về danh sách sản phẩm đọc được.") from exc
            return _mark(_keep_matches(picked, candidates), model)
    raise RuntimeError(last_error)


def _combine(votes: list[list[dict]]) -> list[dict]:
    """Khi cả hai trả lời, chỉ giữ món cả hai cùng chọn. Một bên lỗi thì dùng bên còn lại."""
    if not votes:
        return []
    if len(votes) == 1:
        return votes[0]
    grouped: dict[str, dict] = {}
    for picked in votes:
        seen = set()
        for item in picked:
            item_id = item["item_id"]
            if item_id in seen:
                continue
            seen.add(item_id)
            slot = grouped.setdefault(item_id, {"item": item, "scores": [], "by": []})
            slot["scores"].append(item["score"])
            for label in item.get("by") or []:
                if label not in slot["by"]:
                    slot["by"].append(label)
            if item["score"] >= slot["item"]["score"]:
                slot["item"] = item
    chosen = []
    for slot in grouped.values():
        scores = slot["scores"]
        if len(scores) < 2:
            continue
        score = round(sum(scores) / len(scores))
        if score < MIN_SCORE:
            continue
        item = dict(slot["item"])
        item["score"] = score
        item["by"] = slot["by"]
        chosen.append(item)
    chosen.sort(key=lambda item: -item["score"])
    return chosen[:3]


def _ask(title: str, description: str, candidates: list[dict]) -> list[dict]:
    prompt = _prompt(title, description, candidates)
    votes: dict[str, list[dict]] = {}
    errors: list[str] = []

    def run(name: str, fn) -> None:
        try:
            votes[name] = fn()
        except RuntimeError as exc:
            errors.append(str(exc))

    workers = [
        threading.Thread(target=run, args=("qwen", lambda: _ask_qwen(prompt, candidates))),
        threading.Thread(target=run, args=("groq", lambda: _ask_groq(prompt, candidates))),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    if votes:
        return _combine([votes[name] for name in ("qwen", "groq") if name in votes])
    try:
        return _ask_gemini(prompt, candidates)
    except RuntimeError as exc:
        detail = " ".join(errors)
        raise RuntimeError(_hide_secret(f"{exc} {detail}".strip())) from exc


def _keep_matches(picked: list[dict], candidates: list[dict]) -> list[dict]:
    by_id = {item["item_id"]: item for item in candidates}
    chosen = []
    seen = set()
    for row in picked:
        item_id = str(row.get("item_id") or "").strip()
        source = by_id.get(item_id)
        if not source or item_id in seen:
            continue
        try:
            score = int(round(float(row.get("score") or 0)))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        if score < MIN_SCORE:
            continue
        seen.add(item_id)
        chosen.append({
            "item_id": item_id,
            "name": source["name"],
            "price_formatted": source["price_formatted"],
            "category_name": source["category_name"],
            "short_link": source["short_link"],
            "score": score,
            "reason": " ".join(str(row.get("reason") or "").split())[:180],
        })
    chosen.sort(key=lambda item: -item["score"])
    return chosen[:3]


def _cache() -> dict:
    data = _read_json(CACHE_PATH, {})
    return data if isinstance(data, dict) else {}


def public_cache() -> dict:
    with _LOCK:
        cache = _cache()
    out = {}
    for video_id, row in cache.items():
        if not isinstance(row, dict):
            continue
        out[str(video_id)] = {
            "items": row.get("items") or [],
            "error": row.get("error") or "",
            "note": row.get("note") or "",
            "checked": bool(row.get("at")),
        }
    return out


def _best_score(items: list) -> int:
    scores = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            scores.append(int(item.get("score") or 0))
        except (TypeError, ValueError):
            continue
    return max(scores) if scores else -1


def _prefer(previous: dict | None, items: list, error: str) -> tuple[list, str, str]:
    """Giữ món đã lưu. Chỉ thay khi gợi ý mới có điểm cao hơn."""
    old_items = []
    if isinstance(previous, dict):
        old_items = [item for item in (previous.get("items") or []) if isinstance(item, dict)]
    old_score = _best_score(old_items)
    new_score = _best_score(items)
    if error and old_items:
        return old_items, "", "Giữ sản phẩm đã lưu."
    if items and new_score > old_score:
        note = "Đã thay bằng sản phẩm tương thích hơn." if old_items else "Đã lưu sản phẩm."
        return items, "", note
    if old_items:
        return old_items, "", "Giữ sản phẩm đã lưu vì gợi ý mới không cao hơn."
    if error:
        return [], error, error
    return [], "", "Không có sản phẩm đủ tương thích."


def ensure(video_id: str, force: bool = False) -> dict:
    video_id = str(video_id or "").strip()
    if not force:
        with _LOCK:
            cached = _cache().get(video_id)
            if cached and cached.get("at") and not cached.get("error"):
                return cached
    with _ASK_LOCK:
        with _LOCK:
            previous = _cache().get(video_id)
        video = _video(video_id)
        if not video:
            raise RuntimeError("Không thấy video này trong danh sách đã tải.")
        title = str(video.get("title") or "")
        description = str(video.get("description") or "")
        candidates = shortlist(title, description)
        error = ""
        items = []
        if candidates:
            try:
                items = _ask(title, description, candidates)
            except RuntimeError as exc:
                error = _hide_secret(str(exc))
        kept, error, note = _prefer(previous if isinstance(previous, dict) else None, items, error)
        record = {"items": kept, "error": error, "note": note, "at": now_str()}
        with _LOCK:
            cache = _cache()
            cache[video_id] = record
            _write_json(CACHE_PATH, cache)
        return record


def _video_order() -> list[tuple[str, str]]:
    manifest = _read_json(MANIFEST_PATH, {})
    rows = []
    for item in manifest.get("videos") or []:
        if isinstance(item, dict) and item.get("id"):
            rows.append((str(item["id"]), str(item.get("title") or item["id"])))
    return rows


def auto_status() -> dict:
    with _AUTO_LOCK:
        return dict(_AUTO)


def set_auto(enabled: bool) -> dict:
    enabled = bool(enabled)
    _write_json(AUTO_PATH, {"enabled": enabled})
    with _AUTO_LOCK:
        _AUTO["enabled"] = enabled
        _AUTO["running"] = False
        _AUTO["video_id"] = ""
        _AUTO["title"] = ""
        _AUTO["message"] = "Đang gợi ý lần lượt từ trên xuống" if enabled else "Đã tắt gợi ý tự động"
        return dict(_AUTO)


def _auto_loop() -> None:
    while True:
        with _AUTO_LOCK:
            enabled = _AUTO["enabled"]
        if not enabled:
            time.sleep(1)
            continue
        rows = _video_order()
        with _AUTO_LOCK:
            _AUTO["round"] = int(_AUTO.get("round") or 0) + 1
            _AUTO["total"] = len(rows)
            round_no = _AUTO["round"]
        for index, (video_id, title) in enumerate(rows, start=1):
            with _AUTO_LOCK:
                if not _AUTO["enabled"]:
                    break
                short = title if len(title) <= 80 else title[:77].rstrip() + "..."
                _AUTO.update(
                    running=True,
                    index=index,
                    total=len(rows),
                    video_id=video_id,
                    title=title,
                    message=f"Vòng {round_no} · đang gợi ý {index}/{len(rows)}: {short}",
                )
            try:
                record = ensure(video_id, force=True)
                note = str(record.get("note") or "")
            except Exception as exc:
                note = _hide_secret(str(exc))[:160]
            with _AUTO_LOCK:
                if not _AUTO["enabled"]:
                    _AUTO.update(running=False, video_id="", title="", message="Đã tắt gợi ý tự động")
                    break
                _AUTO["message"] = f"Vòng {round_no} · {index}/{len(rows)} · {note}"
        else:
            with _AUTO_LOCK:
                if _AUTO["enabled"]:
                    _AUTO.update(
                        running=False,
                        video_id="",
                        title="",
                        message=f"Vòng {round_no} xong. Bắt đầu vòng mới từ trên xuống.",
                    )
            time.sleep(2)


def start_auto() -> None:
    enabled = bool(_read_json(AUTO_PATH, {}).get("enabled"))
    with _AUTO_LOCK:
        _AUTO["enabled"] = enabled
        if not enabled:
            _AUTO["message"] = "Tự động gợi ý đang tắt"
        started = getattr(start_auto, "_started", False)
        start_auto._started = True
    if started:
        return
    threading.Thread(target=_auto_loop, name="yt-suggest-auto", daemon=True).start()


def offer_suffix(video_id: str) -> str:
    """Dòng gắn vào bài Facebook nếu đã có món đủ tương thích."""
    try:
        record = ensure(video_id)
    except RuntimeError:
        return ""
    items = record.get("items") or []
    if not items:
        return ""
    best = items[0]
    link = best.get("short_link") or ""
    name = best.get("name") or ""
    if not link or not name:
        return ""
    return f"Gợi ý: {name}\nMua tại: {link}"
