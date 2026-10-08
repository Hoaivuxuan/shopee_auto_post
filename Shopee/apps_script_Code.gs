// Dán toàn bộ nội dung file này vào Apps Script của Google Sheet (Tiện ích mở rộng > Apps Script).
// BẮT BUỘC đổi TOKEN thành một chuỗi bí mật do bạn tự đặt (nên dài 20 ký tự trở lên).
// Bản 2: hỗ trợ cả tab tải video (tab đầu tiên) lẫn tab đăng bài Facebook (tab "Dang_bai").
const TOKEN = "DOI_TOKEN_BI_MAT_CUA_BAN";
const SHEET_NAME = ""; // tab tải video: để trống = dùng tab đầu tiên; hoặc điền đúng tên tab

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return SHEET_NAME ? ss.getSheetByName(SHEET_NAME) : ss.getSheets()[0];
}

function getTab_(name, create) {
  if (!name) return getSheet_(); // không chỉ định tab = dùng chung tab với phần tải video
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh && create) sh = ss.insertSheet(name);
  return sh;
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.token !== TOKEN) return out_({ ok: false, error: "Sai token" });

    // ===== Các hành động cho tab tùy chọn (dùng cho đăng bài Facebook) =====

    // Ghi tiêu đề (dòng 1) bắt đầu từ cột start_col, không đụng tới các cột khác
    if (req.action === "tab_set_header") {
      const t = getTab_(req.tab, true);
      t.getRange(1, req.start_col, 1, req.headers.length).setValues([req.headers]);
      return out_({ ok: true });
    }

    // Tạo tab (nếu chưa có) và ghi dòng tiêu đề nếu dòng 1 đang trống
    if (req.action === "tab_init") {
      const t = getTab_(req.tab, true);
      const n = req.headers.length;
      const first = t.getRange(1, 1, 1, n).getValues()[0];
      const hasData = first.some(function (c) { return String(c).trim() !== ""; });
      if (hasData) return out_({ ok: true, existed: true });
      t.getRange(1, 1, 1, n).setValues([req.headers]);
      return out_({ ok: true, existed: false });
    }

    // Đọc toàn bộ n cột đầu của tab
    if (req.action === "tab_list") {
      const t = getTab_(req.tab, false);
      if (!t) return out_({ ok: false, error: "Không tìm thấy tab: " + req.tab });
      const last = t.getLastRow();
      const values = last > 0 ? t.getRange(1, 1, last, req.ncols).getValues() : [];
      const tz = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
      return out_({ ok: true, values: values.map(function (r) {
        return r.map(function (c) {
          // ô ngày giờ -> chuỗi "yyyy-MM-dd HH:mm:ss" theo múi giờ của sheet
          return c instanceof Date ? Utilities.formatDate(c, tz, "yyyy-MM-dd HH:mm:ss") : String(c);
        });
      }) });
    }

    // Ghi kết quả vào dòng có khóa (ghép các cột key_cols bằng dấu "|") trùng với req.key
    if (req.action === "tab_update") {
      const t = getTab_(req.tab, false);
      if (!t) return out_({ ok: false, error: "Không tìm thấy tab: " + req.tab });
      const last = t.getLastRow();
      if (last < 2) return out_({ ok: true, found: false });
      const maxCol = Math.max.apply(null, req.key_cols);
      const data = t.getRange(1, 1, last, maxCol).getValues();
      const keyOf = function (r) {
        return req.key_cols.map(function (c) { return String(data[r][c - 1]).trim(); }).join("|");
      };
      let row = -1;
      if (req.hint >= 2 && req.hint <= last && keyOf(req.hint - 1) === req.key) {
        row = req.hint;
      } else {
        for (let i = 1; i < data.length; i++) {
          if (keyOf(i) === req.key) { row = i + 1; break; }
        }
      }
      if (row === -1) return out_({ ok: true, found: false });
      const range = t.getRange(row, req.start_col, 1, req.values.length);
      range.setNumberFormat("@"); // giữ nguyên dạng chữ, không tự đổi thành ngày
      range.setValues([req.values]);
      return out_({ ok: true, found: true, row: row });
    }

    // ===== Các hành động cho tab tải video (giữ nguyên như bản trước) =====
    const sh = getSheet_();
    if (!sh) return out_({ ok: false, error: "Không tìm thấy tab: " + SHEET_NAME });

    // Đọc toàn bộ 5 cột đầu
    if (req.action === "list") {
      const last = sh.getLastRow();
      const values = last > 0 ? sh.getRange(1, 1, last, 5).getValues() : [];
      return out_({ ok: true, values: values.map(function (r) {
        return r.map(function (c) { return String(c); });
      }) });
    }

    // Tạo dòng tiêu đề nếu dòng 1 đang trống
    if (req.action === "init") {
      const first = sh.getRange(1, 1, 1, 5).getValues()[0];
      const hasData = first.some(function (c) { return String(c).trim() !== ""; });
      if (hasData) return out_({ ok: true, existed: true });
      sh.getRange(1, 1, 1, 5).setValues([req.headers]);
      return out_({ ok: true, existed: false });
    }

    // Ghi kết quả vào đúng dòng của link (tìm lại theo nội dung link)
    if (req.action === "update") {
      const last = sh.getLastRow();
      if (last < 2) return out_({ ok: true, found: false });
      const links = sh.getRange(1, 1, last, 1).getValues()
        .map(function (r) { return String(r[0]).trim(); });
      let row = -1;
      if (req.hint >= 2 && req.hint <= last && links[req.hint - 1] === req.link) {
        row = req.hint;
      } else {
        for (let i = 1; i < links.length; i++) {
          if (links[i] === req.link) { row = i + 1; break; }
        }
      }
      if (row === -1) return out_({ ok: true, found: false });
      const range = sh.getRange(row, 2, 1, 4);
      range.setNumberFormat("@"); // giữ nguyên dạng chữ, không tự đổi thành ngày
      range.setValues([[req.status, req.time, req.file, req.note]]);
      return out_({ ok: true, found: true, row: row });
    }

    return out_({ ok: false, error: "Hành động không hợp lệ: " + req.action });
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  }
}
