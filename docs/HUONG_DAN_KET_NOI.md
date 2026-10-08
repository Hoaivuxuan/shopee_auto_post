# Hướng dẫn kết nối Google Sheet và Facebook Page

Giao diện của Facebook, Google và Meta thay đổi khá thường xuyên, nên tên menu có thể khác đôi chút so với mô tả dưới đây. Nếu khác, hãy tìm mục có ý nghĩa tương tự.

# PHẦN A. Kết nối Google Sheet (miễn phí, không cần Google Cloud)

Chương trình đọc và ghi sheet thông qua một đoạn **Google Apps Script** do chính bạn triển khai. Không cần thẻ thanh toán, không cần file khóa.

## A1. Tạo Google Sheet
1. Vào sheets.google.com, tạo một bảng tính mới (phải là **Google Trang tính**, không phải file Excel .xlsx mở trong Drive).
2. Vào **Tệp > Cài đặt**: đặt **Ngôn ngữ** là Việt Nam và **Múi giờ** là (GMT+07:00) Hà Nội.

## A2. Tạo token và sao chép mã Apps Script
1. Trong chương trình: Cấu hình > 1. Google Sheet.
2. Bấm **Tạo token ngẫu nhiên** (hoặc tự nhập một chuỗi dài, gồm chữ và số).
3. Bấm **Sao chép mã Apps Script**. Mã đã có sẵn token của bạn.

## A3. Dán vào Apps Script
1. Trong Google Sheet, vào **Tiện ích mở rộng > Apps Script**.
2. Xóa hết mã mẫu, **dán** mã vừa sao chép, bấm **Ctrl+S** để lưu.
3. Nếu không thấy mục Apps Script: kiểm tra bạn đang dùng máy tính (không phải app điện thoại), file là Google Trang tính và bạn có quyền chỉnh sửa. Cách dự phòng: vào script.google.com, tạo dự án mới, dán mã, rồi thay dòng `SpreadsheetApp.getActiveSpreadsheet()` bằng `SpreadsheetApp.openById("ID_CỦA_SHEET")` (ID là đoạn giữa `/d/` và `/edit` trong link sheet) ở hai chỗ trong mã.

## A4. Triển khai thành Web app
1. Bấm **Triển khai (Deploy) > Tùy chọn triển khai mới (New deployment)**.
2. Bấm biểu tượng bánh răng, chọn loại **Ứng dụng web (Web app)**.
3. **Execute as: Me** và **Who has access: Anyone**.
4. Bấm **Deploy**. Google yêu cầu cấp quyền: bấm **Authorize access**, chọn tài khoản. Nếu hiện cảnh báo "Google hasn't verified this app", bấm **Advanced > Go to ... (unsafe) > Allow**. Đây là script của chính bạn.
5. Copy **Web app URL** (kết thúc bằng `/exec`).

"Anyone" chỉ có nghĩa là ai có đường link thì gọi được; việc đọc/ghi sheet vẫn cần đúng token. **Đừng chia sẻ URL và token.**

## A5. Nhập vào chương trình
1. Dán URL vào ô **Web app URL**, kiểm tra ô **Token** đúng như đã dùng khi sao chép mã.
2. Bấm **Kiểm tra kết nối**: thấy "Kết nối thành công: file ..., tab ..." là xong.
3. Bấm **Tạo tiêu đề cột trong sheet**.

## A6. Khi cập nhật mã Apps Script
Mỗi lần dán lại mã mới, bắt buộc triển khai **phiên bản mới**: **Triển khai > Quản lý bản triển khai > biểu tượng bút chì > Phiên bản: Phiên bản mới > Triển khai**. URL giữ nguyên. Nếu không, bản cũ vẫn chạy và sẽ báo "Sai token" hoặc "Hành động không hợp lệ".

## A7. Lỗi thường gặp
| Thông báo | Cách xử lý |
|---|---|
| Sai token / Token không khớp | Token trong chương trình phải giống hệt dòng TOKEN trong Apps Script; sau khi sửa phải triển khai phiên bản mới |
| Không gọi được Apps Script | Kiểm tra URL (phải bắt đầu bằng https://script.google.com và kết thúc /exec), mạng, và "Who has access" là Anyone |
| Hành động không hợp lệ | Apps Script là bản cũ: dán lại mã mới và triển khai phiên bản mới |
| Không tìm thấy tab | Sửa ô "Tên tab" hoặc để trống để dùng tab đầu tiên |

---

# PHẦN B. Kết nối Facebook Page

Chương trình đăng bài bằng **API của Facebook** với token của từng Page, nên **không cần đăng nhập Facebook trên trình duyệt** khi chạy. Bạn chỉ cần lấy token một lần.

## B1. Chuẩn bị
- Tài khoản Facebook của bạn phải là **quản trị viên** của các Page cần đăng.
- Cần một **app trên Meta for Developers** (miễn phí).

## B2. Tạo app
1. Vào **developers.facebook.com**, đăng nhập bằng tài khoản quản trị các Page, bấm **My Apps > Create App**.
2. Đặt tên app. Ở bước chọn use case, chọn **Manage everything on your Page**. Nếu được hỏi thì kết nối với Business Portfolio của bạn.
3. Vào **App settings > Basic**, ghi lại **App ID** và **App Secret**. App Secret là bí mật.

## B3. Thêm quyền cho app
Các quyền cần có:
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `publish_video`

Nếu upload video báo thiếu quyền, thử thêm `pages_manage_metadata`. Nếu Page nằm trong Business Portfolio mà không lấy được Page, thử thêm `business_management`.

Nếu trong Graph API Explorer **không thấy `pages_manage_posts`**: vào bảng điều khiển app, mục **Use cases**, mở use case "Manage everything on your Page", bấm **Customize**, ở tab **Permissions and features** bấm **Add** cạnh quyền còn thiếu. Nếu app dùng use case khác không thêm được, cách gọn nhất là **tạo app mới** với đúng use case trên (use case đã thêm thì không gỡ được).

## B4. Lấy token người dùng
1. Vào công cụ **Graph API Explorer** (menu Tools trên trang developers).
2. Chọn app của bạn ở ô **Meta App**, chọn loại token là **User Token**.
3. Ở ô **Permissions** thêm các quyền ở B3.
4. Bấm **Generate Access Token**. Facebook hỏi quyền: bấm tiếp tục với tài khoản của bạn, rồi **chọn đúng các Page muốn đăng bài** (Page nào không chọn ở đây thì chương trình sẽ không thấy). Nếu có bước chọn Business, chọn doanh nghiệp đang chứa các Page.
5. Copy token vừa tạo. Token này chỉ sống khoảng **1 giờ**, nên làm bước B5 ngay.

## B5. Lấy Page vào chương trình
1. Trong chương trình: Cấu hình > 3. Facebook.
2. Nhập **App ID** và **App Secret** (mục A).
3. Dán token vào ô **Dán token người dùng** (mục B) rồi bấm **Lấy Page**.
4. Chương trình tự đổi sang token dài hạn (khoảng 60 ngày), lấy toàn bộ Page bạn quản trị và lưu token của từng Page. Danh sách hiện ở mục D.
5. Bấm **Kiểm tra** để thử token của các Page.

Theo các hướng dẫn tôi tham khảo (chưa kiểm tra trực tiếp), token Page lấy từ token người dùng dài hạn không tự hết hạn. Nếu sau này gặp lỗi 190 (token không hợp lệ), chỉ cần làm lại B4 và B5.

## B6. Đặt tên Page để dùng trong sheet
Chọn Page rồi bấm **Đổi tên**, đặt tên ngắn không dấu, ví dụ `meo`, `tienich`, `tienganh`. Trong cột F của sheet gõ đúng tên đó (không phân biệt hoa/thường), hoặc dùng Page ID. Nhiều Page ngăn cách bằng dấu phẩy.

## B7. Thêm Page mới sau này
Làm lại B4 (chọn thêm Page ở bước cấp quyền) rồi B5. Page cũ giữ nguyên tên bạn đã đặt, chỉ cập nhật token. Hoặc bấm **Thêm thủ công** nếu đã có sẵn Page ID và token.

## B8. Hẹn giờ trên Facebook
Chọn "Nhờ Facebook hẹn giờ" trong mục C. Giờ hẹn phải cách hiện tại từ 10 phút đến 30 ngày (chương trình chừa lề an toàn nên dùng khoảng 12 phút đến 29 ngày). Cách này chưa được thử trên Facebook thật trong quá trình tạo chương trình, hãy thử với một bài trước.

## B9. Lưu ý về video
- Chương trình đăng video bằng một lần tải lên, phù hợp video không quá lớn (khoảng dưới 1GB và ngắn). Video quá lớn có thể bị Facebook từ chối.
- Chỉ đăng video bạn có quyền sử dụng.

## B10. Lỗi thường gặp
| Thông báo | Cách xử lý |
|---|---|
| Lấy Page ra 0 Page | Lúc cấp quyền chưa chọn Page; thiếu `pages_show_list`; tài khoản không phải quản trị viên; Page nằm trong Business Portfolio (thử thêm `business_management`) |
| Không thấy `pages_manage_posts` trong Explorer | Thêm quyền trong Use cases > Customize, hoặc tạo app mới với use case "Manage everything on your Page" |
| Lỗi 190 | Token hết hạn hoặc bị thu hồi (đổi mật khẩu, bị gỡ quyền quản trị): làm lại B4, B5 |
| Lỗi 10 hoặc 200 | Thiếu quyền, hoặc token tạo trước khi thêm quyền: thêm quyền rồi tạo lại token |
| Lỗi 4, 17, 32, 613 | Facebook giới hạn tốc độ: dừng vài giờ, tăng thời gian nghỉ giữa các bài |
| Báo cần App Review | App cần được Facebook duyệt quyền cho trường hợp của bạn: chép nguyên thông báo để tìm cách xử lý. Tôi chưa chắc quyền đăng bài cho Page do chính bạn quản trị có bị yêu cầu hay không |

---

# PHẦN C. Kết nối Shopee (đăng nhập một lần)

1. Cấu hình > 2. Shopee > **Đăng nhập Shopee**.
2. Một cửa sổ trình duyệt mở ra. Đăng nhập Shopee (xử lý xác minh nếu có).
3. Quay lại chương trình, bấm **Tôi đã đăng nhập xong**. Đừng đóng cửa sổ trình duyệt trước đó.
4. Phiên được lưu trong thư mục `data` trên máy này. Hết hạn thì làm lại.
5. Nên dùng tài khoản Shopee phụ để giảm rủi ro cho tài khoản chính.
