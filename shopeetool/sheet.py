"""Kết nối Google Sheet thông qua Google Apps Script (miễn phí, không cần Google Cloud)."""
import time

import requests

DL_HEADERS = ["Link sản phẩm", "Trạng thái", "Thời gian", "File video", "Ghi chú"]
POST_HEADERS = ["Page", "Link affiliate", "Nội dung", "Tag", "Giờ đăng",
                "Trạng thái đăng", "Đã xử lý lúc", "ID bài đăng", "Ghi chú đăng"]
NCOLS = 14


class SheetError(Exception):
    pass


def friendly(msg):
    m = str(msg)
    if "Sai token" in m:
        return ("Token không khớp. Kiểm tra: token trong chương trình phải giống hệt dòng TOKEN trong Apps Script, "
                "và sau khi sửa Apps Script phải triển khai PHIÊN BẢN MỚI (Deploy > Manage deployments > Edit > New version).")
    if "Hành động không hợp lệ" in m:
        return ("Apps Script đang là bản cũ. Hãy dán lại mã Apps Script mới (nút 'Sao chép mã Apps Script') "
                "và triển khai phiên bản mới.")
    if "Không tìm thấy tab" in m:
        return m + " (kiểm tra ô 'Tên tab' trong Cấu hình > Google Sheet, hoặc để trống để dùng tab đầu tiên)."
    return m


class SheetClient:
    def __init__(self, url, token, tab=""):
        self.url = (url or "").strip()
        self.token = (token or "").strip()
        self.tab = (tab or "").strip()
        if not self.url or not self.token:
            raise SheetError("Chưa nhập URL hoặc Token của Google Sheet (Cấu hình > Google Sheet).")
        if not self.url.startswith("https://script.google.com/"):
            raise SheetError("URL Apps Script phải bắt đầu bằng https://script.google.com/ và kết thúc bằng /exec.")

    def call(self, action, **payload):
        body = {"token": self.token, "action": action, **payload}
        last_error = None
        data = None
        for attempt in range(4):
            try:
                r = requests.post(self.url, json=body, timeout=90)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                last_error = e
                time.sleep(3 * (attempt + 1))
        if data is None:
            raise SheetError(
                f"Không gọi được Apps Script ({last_error}). Kiểm tra mạng, URL, và mục 'Who has access' phải là 'Anyone'."
            )
        if not data.get("ok"):
            raise SheetError(friendly(data.get("error", "Apps Script báo lỗi")))
        return data

    # ----- các thao tác
    def ping(self):
        return self.call("ping", tab=self.tab)

    def tab_list(self, ncols=NCOLS):
        return self.call("tab_list", tab=self.tab, ncols=ncols)["values"]

    def tab_update(self, hint, key, start_col, values, key_cols=(1,)):
        return self.call("tab_update", tab=self.tab, hint=hint, key_cols=list(key_cols),
                         key=key, start_col=start_col, values=values)

    def init_headers(self):
        """Ghi tiêu đề A-E (nếu dòng 1 trống) và F-N."""
        a = self.call("tab_init", tab=self.tab, headers=DL_HEADERS)
        self.call("tab_set_header", tab=self.tab, start_col=6, headers=POST_HEADERS)
        return a.get("existed", False)
