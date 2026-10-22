"""Các mạng xã hội và trang thuộc từng mạng.

Facebook vẫn dùng API đăng video. Instagram, TikTok và YouTube được lưu để quản lý
nhiều trang; API đăng bài của ba mạng này chưa gắn.
"""
from . import config as cfgmod

PLATFORMS = (
    {"id": "facebook", "label": "Facebook", "unit": "Page", "posting": True},
    {"id": "instagram", "label": "Instagram", "unit": "Tài khoản", "posting": False},
    {"id": "tiktok", "label": "TikTok", "unit": "Tài khoản", "posting": False},
    {"id": "youtube", "label": "YouTube", "unit": "Kênh", "posting": False},
)
PLATFORM_IDS = {item["id"] for item in PLATFORMS}


def platform_info(platform):
    for item in PLATFORMS:
        if item["id"] == platform:
            return item
    return None


def ensure_networks(cfg):
    """Bổ sung đủ 4 mạng. Page Facebook cũ trong `pages` được đưa sang networks một lần."""
    changed = False
    networks = cfg.get("networks")
    if not isinstance(networks, dict):
        networks = {}
        changed = True
    for item in PLATFORMS:
        block = networks.get(item["id"])
        if not isinstance(block, dict):
            block = {"pages": []}
            changed = True
        pages = block.get("pages")
        if not isinstance(pages, list):
            pages = []
            changed = True
        clean = []
        for page in pages:
            if isinstance(page, dict) and str(page.get("id") or "").strip():
                clean.append(_clean_page(page))
        if clean != pages:
            changed = True
        block["pages"] = clean
        networks[item["id"]] = block
    facebook_pages = networks["facebook"]["pages"]
    if not facebook_pages:
        for page in cfg.get("pages") or []:
            if isinstance(page, dict) and str(page.get("id") or "").strip():
                facebook_pages.append(_clean_page(page))
                changed = True
    cfg["networks"] = networks
    if _sync_legacy_pages(cfg):
        changed = True
    return changed


def load_cfg():
    cfg = cfgmod.load()
    if ensure_networks(cfg):
        cfgmod.save(cfg)
    return cfg


def save_cfg(cfg):
    ensure_networks(cfg)
    _sync_legacy_pages(cfg)
    cfgmod.save(cfg)


def public_networks(cfg):
    ensure_networks(cfg)
    out = []
    for item in PLATFORMS:
        pages = []
        for page in cfg["networks"][item["id"]]["pages"]:
            pages.append({
                "id": page["id"],
                "name": page.get("name") or page["id"],
                "enabled": bool(page.get("enabled", True)),
                "has_token": bool(page.get("token")),
            })
        out.append({**item, "pages": pages})
    return out


def find_page(cfg, platform, page_id):
    ensure_networks(cfg)
    info = platform_info(platform)
    if not info:
        return None
    for page in cfg["networks"][platform]["pages"]:
        if str(page.get("id")) == str(page_id):
            return page
    return None


def upsert_page(cfg, platform, page_id, name, token="", enabled=True):
    info = platform_info(platform)
    if not info:
        raise ValueError("Mạng xã hội không hỗ trợ")
    page_id = str(page_id or "").strip()
    name = " ".join(str(name or "").split())
    if not page_id or len(page_id) > 80:
        raise ValueError("Thiếu mã trang")
    if not name or len(name) > 120:
        raise ValueError("Thiếu tên trang")
    ensure_networks(cfg)
    pages = cfg["networks"][platform]["pages"]
    token = str(token or "").strip()
    for page in pages:
        if page["id"] == page_id:
            page["name"] = name
            page["enabled"] = bool(enabled)
            if token:
                page["token"] = token
            return page
    if platform == "facebook" and not token:
        raise ValueError("Page Facebook cần token")
    pages.append({
        "id": page_id,
        "name": name,
        "token": token,
        "enabled": bool(enabled),
    })
    return pages[-1]


def publications_of(item):
    """Các bài đã ghi trên sản phẩm, gồm cả bài Facebook lưu theo trường cũ."""
    found = []
    seen = set()
    for pub in item.get("publications") or []:
        if not isinstance(pub, dict):
            continue
        platform = str(pub.get("platform") or "")
        page_id = str(pub.get("page_id") or "")
        if platform not in PLATFORM_IDS or not page_id:
            continue
        key = (platform, page_id)
        if key in seen:
            continue
        seen.add(key)
        found.append(_public_pub(pub))
    video_id = str(item.get("facebook_video_id") or "").strip()
    page_id = str(item.get("facebook_page_id") or "").strip()
    if video_id and page_id and ("facebook", page_id) not in seen:
        found.append(_public_pub({
            "platform": "facebook",
            "page_id": page_id,
            "page_name": item.get("facebook_page_name") or "",
            "video_id": video_id,
            "status": item.get("facebook_status") or "published",
            "permalink": item.get("facebook_permalink") or "",
            "scheduled_at": item.get("facebook_scheduled_at") or "",
            "error": item.get("facebook_error") or "",
        }))
    return found


def already_posted(item, platform, page_id):
    page_id = str(page_id or "")
    for pub in publications_of(item):
        if pub["platform"] == platform and pub["page_id"] == page_id:
            if pub.get("video_id") or pub.get("status") in ("published", "scheduled"):
                return True
    return False


def remember_publication(item, pub):
    """Ghi bài đăng theo mạng và trang. Bài Facebook vẫn phản chiếu sang trường cũ."""
    platform = pub["platform"]
    page_id = str(pub["page_id"])
    stored = {
        "platform": platform,
        "page_id": page_id,
        "page_name": pub.get("page_name") or "",
        "video_id": str(pub.get("video_id") or ""),
        "status": pub.get("status") or "",
        "permalink": pub.get("permalink") or "",
        "comment_id": pub.get("comment_id") or "",
        "scheduled_at": pub.get("scheduled_at") or "",
        "error": pub.get("error") or "",
        "checked_at": pub.get("checked_at") or "",
    }
    pubs = [p for p in item.get("publications") or [] if isinstance(p, dict)]
    for index, existing in enumerate(pubs):
        if existing.get("platform") == platform and str(existing.get("page_id")) == page_id:
            pubs[index] = {**existing, **stored}
            break
    else:
        pubs.append(stored)
    item["publications"] = pubs
    if platform == "facebook":
        item["facebook_video_id"] = stored["video_id"]
        item["facebook_page_id"] = page_id
        item["facebook_page_name"] = stored["page_name"]
        item["facebook_status"] = stored["status"]
        item["facebook_permalink"] = stored["permalink"]
        item["facebook_scheduled_at"] = stored["scheduled_at"]
        item["facebook_error"] = stored["error"]
        item["facebook_checked_at"] = stored["checked_at"]
        if stored["comment_id"]:
            item["facebook_comment_id"] = stored["comment_id"]


def _clean_page(page):
    return {
        "id": str(page.get("id") or "").strip(),
        "name": str(page.get("name") or page.get("id") or "").strip(),
        "token": str(page.get("token") or ""),
        "enabled": bool(page.get("enabled", True)),
    }


def _sync_legacy_pages(cfg):
    """Giữ `pages` trùng Page Facebook để công cụ cũ vẫn đọc được."""
    current = []
    for page in cfg["networks"]["facebook"]["pages"]:
        current.append({
            "name": page.get("name") or page["id"],
            "id": page["id"],
            "token": page.get("token") or "",
            "enabled": bool(page.get("enabled", True)),
        })
    if cfg.get("pages") != current:
        cfg["pages"] = current
        return True
    return False


def _public_pub(pub):
    permalink = pub.get("permalink") or ""
    if permalink.startswith("/"):
        permalink = "https://www.facebook.com" + permalink
    return {
        "platform": pub.get("platform") or "",
        "page_id": str(pub.get("page_id") or ""),
        "page_name": pub.get("page_name") or "",
        "video_id": str(pub.get("video_id") or ""),
        "status": pub.get("status") or "",
        "permalink": permalink,
        "scheduled_at": pub.get("scheduled_at") or "",
        "error": pub.get("error") or "",
    }
