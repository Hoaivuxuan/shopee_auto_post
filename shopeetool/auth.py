"""Tài khoản đăng nhập admin và phiên làm việc theo từng người dùng.

Mỗi tài khoản có workspace riêng tại data/workspaces/<username>/
(token, cookie, kho video, danh sách sản phẩm, cấu hình).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

COOKIE_NAME = "shopee_admin_session"
SESSION_DAYS = 14
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,31}$")
_LOCK = threading.RLock()
_CURRENT_USER: ContextVar[Optional[str]] = ContextVar("shopee_admin_user", default=None)

_LEGACY_FILES = (
    "config.json",
    "products_affiliate.json",
    "auto_post.json",
    "facebook_state.json",
    "facebook_accounts.json",
    "fb_groups.json",
    "fb_login_debug.json",
    "fb_group_comment.png",
    "fb_group_report.json",
    "shopee_state.json",
)
_LEGACY_DIRS = (
    "affiliate",
    "facebook_accounts",
    "fb_group_media",
    "videos",
    "logs",
)


def _shared_data_dir() -> str:
    from .paths import shared_data_dir
    return shared_data_dir()


def safe_username(value: str) -> str:
    name = str(value or "").strip()
    if not _USERNAME_RE.fullmatch(name):
        raise ValueError("Tên đăng nhập 2–32 ký tự: chữ, số, dấu chấm, gạch dưới, gạch ngang")
    return name.lower()


def workspace_dir(username: str) -> str:
    name = safe_username(username)
    path = os.path.join(_shared_data_dir(), "workspaces", name)
    os.makedirs(path, exist_ok=True)
    return path


def current_username() -> Optional[str]:
    return _CURRENT_USER.get()


def set_current_user(username: Optional[str]):
    return _CURRENT_USER.set(username)


def reset_current_user(token) -> None:
    _CURRENT_USER.reset(token)


def accounts_path() -> str:
    return os.path.join(_shared_data_dir(), "accounts.json")


def sessions_path() -> str:
    return os.path.join(_shared_data_dir(), "sessions.json")


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    raw = str(password or "")
    if len(raw) < 4:
        raise ValueError("Mật khẩu tối thiểu 4 ký tự")
    if len(raw) > 128:
        raise ValueError("Mật khẩu quá dài")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = str(encoded or "").split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds_n = int(rounds)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, rounds_n)
    return hmac.compare_digest(got, expected)


def _read_json(path: str, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def load_accounts() -> Dict[str, Any]:
    data = _read_json(accounts_path(), {"users": []})
    users = data.get("users") if isinstance(data.get("users"), list) else []
    clean = []
    for item in users:
        if not isinstance(item, dict):
            continue
        try:
            name = safe_username(item.get("username") or "")
        except ValueError:
            continue
        if not item.get("password_hash"):
            continue
        clean.append({
            "username": name,
            "password_hash": item["password_hash"],
            "role": "admin" if item.get("role") == "admin" else "user",
            "created_at": str(item.get("created_at") or ""),
        })
    return {"users": clean}


def save_accounts(data: Dict[str, Any]) -> None:
    _write_json(accounts_path(), {"users": data.get("users") or []})


def list_users() -> List[Dict[str, str]]:
    with _LOCK:
        return [
            {"username": item["username"], "role": item["role"], "created_at": item.get("created_at") or ""}
            for item in load_accounts()["users"]
        ]


def find_user(username: str) -> Optional[Dict[str, Any]]:
    try:
        name = safe_username(username)
    except ValueError:
        return None
    with _LOCK:
        for item in load_accounts()["users"]:
            if item["username"] == name:
                return item
    return None


def create_user(username: str, password: str, role: str = "user") -> Dict[str, str]:
    name = safe_username(username)
    role_name = "admin" if role == "admin" else "user"
    with _LOCK:
        data = load_accounts()
        if any(item["username"] == name for item in data["users"]):
            raise ValueError("Tên đăng nhập đã tồn tại")
        record = {
            "username": name,
            "password_hash": _hash_password(password),
            "role": role_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        data["users"].append(record)
        save_accounts(data)
    ensure_workspace(name)
    return {"username": name, "role": role_name, "created_at": record["created_at"]}


def change_password(username: str, new_password: str) -> None:
    name = safe_username(username)
    with _LOCK:
        data = load_accounts()
        for item in data["users"]:
            if item["username"] == name:
                item["password_hash"] = _hash_password(new_password)
                save_accounts(data)
                return
    raise LookupError("Không thấy tài khoản")


def delete_user(username: str, actor: str) -> None:
    name = safe_username(username)
    actor_name = safe_username(actor)
    if name == actor_name:
        raise ValueError("Không thể xóa tài khoản đang đăng nhập")
    with _LOCK:
        data = load_accounts()
        users = data["users"]
        target = next((item for item in users if item["username"] == name), None)
        if not target:
            raise LookupError("Không thấy tài khoản")
        admins = [item for item in users if item["role"] == "admin"]
        if target["role"] == "admin" and len(admins) <= 1:
            raise ValueError("Phải giữ ít nhất một tài khoản admin")
        data["users"] = [item for item in users if item["username"] != name]
        save_accounts(data)
        _revoke_user_sessions(name)


def check_password(username: str, password: str) -> Dict[str, Any]:
    user = find_user(username)
    if not user or not _verify_password(password, user["password_hash"]):
        raise ValueError("Sai tên đăng nhập hoặc mật khẩu")
    return user


def authenticate(username: str, password: str) -> Dict[str, str]:
    user = check_password(username, password)
    return create_session(user["username"])


def _load_sessions() -> Dict[str, Any]:
    data = _read_json(sessions_path(), {"sessions": {}})
    sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
    now = time.time()
    alive = {}
    for token, item in sessions.items():
        if not isinstance(item, dict):
            continue
        if float(item.get("expires_at") or 0) < now:
            continue
        alive[str(token)] = {
            "username": str(item.get("username") or ""),
            "expires_at": float(item["expires_at"]),
        }
    return {"sessions": alive}


def _save_sessions(data: Dict[str, Any]) -> None:
    _write_json(sessions_path(), {"sessions": data.get("sessions") or {}})


def create_session(username: str) -> Dict[str, str]:
    name = safe_username(username)
    token = secrets.token_urlsafe(32)
    expires = time.time() + SESSION_DAYS * 24 * 3600
    with _LOCK:
        data = _load_sessions()
        data["sessions"][token] = {"username": name, "expires_at": expires}
        _save_sessions(data)
    return {"token": token, "username": name, "role": (find_user(name) or {}).get("role") or "user"}


def session_user(token: str) -> Optional[Dict[str, str]]:
    raw = str(token or "").strip()
    if not raw:
        return None
    with _LOCK:
        data = _load_sessions()
        item = data["sessions"].get(raw)
        if not item:
            return None
        user = find_user(item["username"])
        if not user:
            data["sessions"].pop(raw, None)
            _save_sessions(data)
            return None
        # Gia hạn phiên khi còn dùng
        item["expires_at"] = time.time() + SESSION_DAYS * 24 * 3600
        _save_sessions(data)
        return {"username": user["username"], "role": user["role"]}


def destroy_session(token: str) -> None:
    raw = str(token or "").strip()
    if not raw:
        return
    with _LOCK:
        data = _load_sessions()
        if raw in data["sessions"]:
            data["sessions"].pop(raw, None)
            _save_sessions(data)


def _revoke_user_sessions(username: str) -> None:
    with _LOCK:
        data = _load_sessions()
        data["sessions"] = {
            token: item
            for token, item in data["sessions"].items()
            if item.get("username") != username
        }
        _save_sessions(data)


def parse_cookie_header(header: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in str(header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def cookie_token(headers) -> str:
    return parse_cookie_header(headers.get("Cookie") or "").get(COOKIE_NAME) or ""


def session_cookie(token: str, clear: bool = False) -> str:
    if clear:
        return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    max_age = SESSION_DAYS * 24 * 3600
    return f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"


def ensure_workspace(username: str) -> str:
    path = workspace_dir(username)
    for name in ("affiliate", "facebook_accounts", "fb_group_media", "videos", "logs", "api_shopee"):
        os.makedirs(os.path.join(path, name), exist_ok=True)
    seed_workspace_api(path)
    cfg = os.path.join(path, "config.json")
    if not os.path.isfile(cfg):
        from . import config as cfgmod
        from .paths import use_workspace, reset_workspace
        token = use_workspace(path)
        try:
            cfgmod.save(cfgmod.load())
        finally:
            reset_workspace(token)
    return path


def seed_workspace_api(workspace: str) -> str:
    """Sao chép file curl mẫu từ api_shopee toàn cục vào workspace (cookie riêng từng người)."""
    from .paths import app_dir
    dest = os.path.join(workspace, "api_shopee")
    os.makedirs(dest, exist_ok=True)
    src = os.path.join(app_dir(), "api_shopee")
    if not os.path.isdir(src):
        return dest
    for name in os.listdir(src):
        if not name.endswith((".txt", ".json")):
            continue
        target = os.path.join(dest, name)
        if os.path.exists(target):
            continue
        source = os.path.join(src, name)
        if os.path.isfile(source):
            try:
                with open(source, "rb") as hin, open(target, "wb") as hout:
                    hout.write(hin.read())
            except OSError:
                pass
    return dest


def workspace_api_dir() -> str:
    from .paths import data_dir
    return seed_workspace_api(data_dir())


def list_workspace_usernames() -> List[str]:
    root = os.path.join(_shared_data_dir(), "workspaces")
    if not os.path.isdir(root):
        return []
    names = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        try:
            names.append(safe_username(name))
        except ValueError:
            continue
    return names


def _move_path(src: str, dest: str) -> None:
    if not os.path.exists(src):
        return
    if os.path.exists(dest):
        return
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    os.rename(src, dest)


def migrate_legacy_workspace(username: str = "admin") -> Optional[str]:
    """Chuyển data cũ ở thư mục gốc vào workspace của admin (một lần)."""
    shared = _shared_data_dir()
    has_legacy = any(
        os.path.exists(os.path.join(shared, name))
        for name in (*_LEGACY_FILES, *_LEGACY_DIRS)
    )
    if not has_legacy:
        return None
    name = safe_username(username)
    ws = workspace_dir(name)
    for filename in _LEGACY_FILES:
        _move_path(os.path.join(shared, filename), os.path.join(ws, filename))
    for dirname in _LEGACY_DIRS:
        _move_path(os.path.join(shared, dirname), os.path.join(ws, dirname))
    seed_workspace_api(ws)
    return name


def bootstrap() -> Dict[str, Any]:
    """Khởi tạo tài khoản admin và chuyển data cũ nếu cần."""
    migrated = migrate_legacy_workspace("admin")
    with _LOCK:
        data = load_accounts()
        if data["users"]:
            for item in data["users"]:
                ensure_workspace(item["username"])
            return {"created": False, "migrated": migrated, "users": list_users()}
        password = os.environ.get("SHOPEE_ADMIN_PASSWORD") or "admin123"
        create_user("admin", password, role="admin")
        return {
            "created": True,
            "migrated": migrated,
            "username": "admin",
            "default_password": password if not os.environ.get("SHOPEE_ADMIN_PASSWORD") else "",
            "users": list_users(),
        }
