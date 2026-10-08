"""Chạy bằng dòng lệnh (không cần giao diện).
Cú pháp:  ShopeeFBTool.exe cli <lệnh> (Windows)  |  ./ShopeeFBTool cli <lệnh> (Ubuntu)  |  python app.py cli <lệnh>"""
import argparse
import copy
import threading

from . import APP_TITLE, VERSION, config as cfgmod, facebook as fb, shopee, syscheck
from .jobs import MODES, make_client, run_all
from .logger import RunContext
from .platforms import CLI_PROG
from .sheet import SheetError

COLORS = {"info": "", "ok": "", "warn": "", "error": ""}


def _emit(ev):
    if ev["type"] == "log":
        tag = {"ok": "OK   ", "warn": "CẢNH BÁO ", "error": "LỖI ", "info": ""}[ev["level"]]
        print(f"{ev['time']} {tag}{ev['msg']}", flush=True)


def _set_path(cfg, dotted, raw):
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node[k]
    old = node[keys[-1]]
    if isinstance(old, bool):
        val = raw.lower() in ("1", "true", "yes", "y", "có", "bật")
    elif isinstance(old, int):
        val = int(raw)
    else:
        val = raw
    node[keys[-1]] = val
    return val


def build_parser():
    ap = argparse.ArgumentParser(prog=CLI_PROG, description=f"{APP_TITLE} {VERSION} - dòng lệnh")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--dry-run", action="store_true", help="Chạy thử, không tải/đăng thật")
        p.add_argument("--retry", action="store_true", help="Chạy lại các dòng Lỗi/Một phần")
        p.add_argument("--limit", type=int, help="Số dòng/link tối đa mỗi lần")

    p = sub.add_parser("download", help="Tải video theo link trong sheet")
    common(p)
    p.add_argument("--show", action="store_true", help="Hiện cửa sổ trình duyệt")
    p.add_argument("--min-delay", type=int)
    p.add_argument("--max-delay", type=int)

    p = sub.add_parser("post", help="Đăng video đã tải lên Facebook Page")
    common(p)
    p.add_argument("--schedule", choices=["local", "facebook"])
    p.add_argument("--min-delay", type=int)
    p.add_argument("--max-delay", type=int)
    p.add_argument("--link-in-comment", action="store_true")
    p.add_argument("--watch", type=int, metavar="PHUT", help="Chạy liên tục, quét lại mỗi PHUT phút")

    p = sub.add_parser("all", help="Tải rồi đăng (lần lượt), hoặc song song với --parallel")
    common(p)
    p.add_argument("--parallel", action="store_true")
    p.add_argument("--show", action="store_true")

    sub.add_parser("login-shopee", help="Mở trình duyệt để đăng nhập Shopee và lưu phiên")
    sub.add_parser("clear-shopee", help="Xóa phiên đăng nhập Shopee đã lưu")
    sub.add_parser("test-sheet", help="Kiểm tra kết nối Google Sheet")
    sub.add_parser("init-sheet", help="Tạo dòng tiêu đề các cột trong sheet")
    sub.add_parser("check", help="Kiểm tra môi trường (trình duyệt, ffmpeg...)")

    p = sub.add_parser("exchange", help="Đổi token ngắn hạn sang dài hạn")
    p.add_argument("short_token")
    p.add_argument("--app-id")
    p.add_argument("--app-secret")
    p = sub.add_parser("sync-pages", help="Lấy tất cả Page từ token và lưu vào cấu hình")
    p.add_argument("token")
    p.add_argument("--exchange", action="store_true", help="Đổi token sang dài hạn trước (cần App ID/Secret)")
    p = sub.add_parser("add-page", help="Thêm tay một Page")
    p.add_argument("name")
    p.add_argument("page_id")
    p.add_argument("page_token")
    sub.add_parser("list-pages", help="Xem danh sách Page")
    sub.add_parser("check-pages", help="Kiểm tra token của các Page")

    p = sub.add_parser("config", help="Xem hoặc sửa cấu hình")
    p.add_argument("action", choices=["show", "set", "path"])
    p.add_argument("key", nargs="?", help="vd sheet.url, facebook.min_delay")
    p.add_argument("value", nargs="?")
    return ap


def _mask(v):
    return "(đã nhập)" if v else "(trống)"


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    cfg = cfgmod.load()

    try:
        if a.cmd == "config":
            if a.action == "path":
                print(cfgmod.config_path())
            elif a.action == "show":
                shown = copy.deepcopy(cfg)
                for sec, k in (("sheet", "token"), ("sheet", "url"), ("facebook", "app_secret")):
                    shown[sec][k] = _mask(shown[sec][k])
                for p in shown["pages"]:
                    p["token"] = _mask(p["token"])
                import json
                print(json.dumps(shown, ensure_ascii=False, indent=2))
            else:
                if not a.key or a.value is None:
                    print("Cú pháp: config set <khóa> <giá trị>   ví dụ: config set facebook.min_delay 10")
                    return 2
                _set_path(cfg, a.key, a.value)
                cfgmod.save(cfg)
                print(f"Đã lưu {a.key}")
            return 0

        if a.cmd == "check":
            for name, st, detail in syscheck.check_all(cfg):
                print(f"[{st.upper():5}] {name}: {detail}")
            return 0

        if a.cmd == "list-pages":
            if not cfg["pages"]:
                print("Chưa có Page nào. Dùng sync-pages hoặc add-page.")
            for p in cfg["pages"]:
                print(f"- {p['name']} (ID {p['id']}) {'' if p.get('enabled', True) else '[TẮT]'}")
            return 0

        if a.cmd == "add-page":
            for p in cfg["pages"]:
                if str(p["id"]) == a.page_id:
                    p.update(name=a.name, token=a.page_token)
                    break
            else:
                cfg["pages"].append({"name": a.name, "id": a.page_id, "token": a.page_token, "enabled": True})
            cfgmod.save(cfg)
            print(f"Đã lưu Page '{a.name}'.")
            return 0

        ver = cfg["facebook"]["api_version"]
        if a.cmd == "exchange":
            app_id = a.app_id or cfg["facebook"]["app_id"]
            secret = a.app_secret or cfg["facebook"]["app_secret"]
            if not app_id or not secret:
                print("Cần App ID và App Secret (--app-id/--app-secret hoặc config set facebook.app_id ...).")
                return 2
            tok, exp = fb.exchange_token(app_id, secret, a.short_token, ver)
            print("Token dài hạn (giữ bí mật):")
            print(tok)
            return 0

        if a.cmd == "sync-pages":
            tok = a.token
            if a.exchange:
                tok, _ = fb.exchange_token(cfg["facebook"]["app_id"], cfg["facebook"]["app_secret"], tok, ver)
            found = fb.fetch_pages(tok, ver)
            by_id = {str(p["id"]): p for p in cfg["pages"]}
            added = 0
            for f in found:
                if str(f["id"]) in by_id:
                    by_id[str(f["id"])]["token"] = f["access_token"]
                else:
                    cfg["pages"].append({"name": f["name"], "id": str(f["id"]), "token": f["access_token"], "enabled": True})
                    added += 1
            cfgmod.save(cfg)
            print(f"Facebook trả về {len(found)} Page, thêm mới {added}.")
            if not found:
                print("Không có Page nào: kiểm tra quyền pages_show_list và đã chọn Page ở màn hình cấp quyền chưa.")
            return 0

        if a.cmd == "check-pages":
            bad = 0
            for p in cfg["pages"]:
                try:
                    print(f"OK    {p['name']}: {fb.check_page(p, ver)}")
                except fb.FBError as e:
                    bad += 1
                    print(f"LỖI   {p['name']}: {e.code} {e} {fb.hint_for(e)}")
            return 1 if bad else 0

        if a.cmd == "clear-shopee":
            shopee.clear_session()
            print("Đã xóa phiên đăng nhập Shopee.")
            return 0

        if a.cmd == "login-shopee":
            ctx = RunContext(emit=_emit)
            done = threading.Event()

            def wait_enter():
                input("Đăng nhập Shopee trong trình duyệt vừa mở, xong thì nhấn Enter tại đây... ")
                done.set()

            threading.Thread(target=wait_enter, daemon=True).start()
            shopee.login(cfg, ctx, done)
            return 0

        if a.cmd == "test-sheet":
            r = make_client(cfg).ping()
            print(f"Kết nối thành công: file '{r.get('name')}', tab '{r.get('tab')}', {r.get('rows')} dòng.")
            return 0

        if a.cmd == "init-sheet":
            existed = make_client(cfg).init_headers()
            print("Đã ghi tiêu đề cột F-N" + (" (cột A-E đã có sẵn)." if existed else " và A-E."))
            return 0

        # ----- các lệnh chạy công việc
        if getattr(a, "show", False):
            cfg["shopee"]["show_browser"] = True
        if getattr(a, "min_delay", None) is not None:
            sec = "shopee" if a.cmd == "download" else "facebook"
            cfg[sec]["min_delay"] = a.min_delay
        if getattr(a, "max_delay", None) is not None:
            sec = "shopee" if a.cmd == "download" else "facebook"
            cfg[sec]["max_delay"] = a.max_delay
        if getattr(a, "schedule", None):
            cfg["facebook"]["schedule_mode"] = a.schedule
        if getattr(a, "link_in_comment", False):
            cfg["facebook"]["link_in_comment"] = True
        if a.limit:
            cfg["shopee"]["limit"] = a.limit
            cfg["facebook"]["limit"] = a.limit

        mode = {"download": "download", "post": "post",
                "all": "parallel" if getattr(a, "parallel", False) else "download_post"}[a.cmd]
        ctx = RunContext(emit=_emit)
        print(f"== {MODES[mode]} ==")
        try:
            if a.cmd == "post" and a.watch:
                print(f"Chế độ theo dõi: quét mỗi {a.watch} phút. Nhấn Ctrl+C để dừng.")
                while True:
                    run_all(cfg, ctx, "post", a.dry_run, a.retry)
                    if not ctx.sleep(a.watch * 60):
                        break
            else:
                run_all(cfg, ctx, mode, a.dry_run, a.retry)
        except KeyboardInterrupt:
            ctx.cancel()
            print("\nĐã dừng.")
        s = ctx.stats
        print("Tổng kết:", ", ".join(f"{k}={v}" for k, v in sorted(s.items())) or "không có thay đổi")
        return 1 if (s.get("dl_fail") or s.get("post_fail")) else 0

    except (SheetError, shopee.ShopeeError) as e:
        print("LỖI:", e)
        return 1
    except fb.FBError as e:
        print(f"LỖI Facebook {e.code}: {e} {fb.hint_for(e)}")
        return 1
    except KeyboardInterrupt:
        print("\nĐã dừng.")
        return 130
