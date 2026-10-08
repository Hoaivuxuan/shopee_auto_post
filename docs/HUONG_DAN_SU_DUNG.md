# Hướng dẫn sử dụng chương trình (giao diện)

Chương trình giúp bạn: **tải video từ các link sản phẩm Shopee** trong Google Sheet, rồi **đăng lên một hoặc nhiều Facebook Page** (đăng ngay hoặc hẹn giờ), và **ghi kết quả vào lại sheet**. Mọi thiết lập đều làm trên giao diện, không cần gõ lệnh.

> Chỉ nên dùng video bạn có quyền sử dụng (video của bạn, hoặc chủ video/shop đã đồng ý). Đăng lại video của người khác khi chưa được phép có thể khiến Page bị gỡ bài hoặc hạn chế. Tự động hóa trên Shopee cũng có rủi ro với tài khoản, nên dùng tài khoản phụ và đừng tải dồn dập.

## 1. Cài đặt và mở chương trình

- Giải nén thư mục chương trình ở đâu cũng được (ví dụ `D:\ShopeeFBTool`), rồi bấm đúp **ShopeeFBTool.exe**. Không cần cài Python.
- Máy cần có **Microsoft Edge** (Windows 10/11 có sẵn) hoặc **Google Chrome** để tải video.
- Dữ liệu của chương trình (cấu hình, phiên đăng nhập Shopee, video, nhật ký) nằm trong thư mục **data** cạnh file .exe. Nếu thư mục đó không ghi được, chương trình tự dùng `%LOCALAPPDATA%\ShopeeFBTool`.
- Nếu Windows báo "Windows protected your PC", bấm **More info > Run anyway** (vì file chưa được ký số).

## 2. Các bước thiết lập lần đầu (làm theo thứ tự)

1. **Google Sheet:** vào Cấu hình > 1. Google Sheet, làm theo tài liệu "Kết nối Google Sheet & Facebook Page". Xong bấm **Kiểm tra kết nối** và **Tạo tiêu đề cột trong sheet**.
2. **Shopee:** vào Cấu hình > 2. Shopee, bấm **Đăng nhập Shopee** và đăng nhập một lần.
3. **Facebook:** vào Cấu hình > 3. Facebook, nhập App ID, App Secret, dán token và bấm **Lấy Page**.
4. **Điền sheet:** dán link sản phẩm vào cột A, và điền cột F-J cho các dòng muốn đăng.
5. **Chạy thử:** tab Chạy, tick **Chạy thử**, bấm **BẮT ĐẦU** để kiểm tra, rồi bỏ tick và chạy thật.

Tab **Hệ thống** cho biết còn thiếu gì (trình duyệt, ffmpeg, phiên đăng nhập, Sheet, Page).

## 3. Tab Cấu hình

### 3.1. Google Sheet
- **Web app URL (…/exec):** đường link nhận được khi triển khai Apps Script.
- **Token:** mật khẩu bạn tự đặt, phải giống dòng `TOKEN` trong Apps Script.
- **Tên tab:** để trống để dùng tab đầu tiên của sheet.
- **Tạo token ngẫu nhiên:** sinh một token khó đoán.
- **Sao chép mã Apps Script:** chép sẵn toàn bộ mã (đã chèn token của bạn) để dán vào Apps Script.
- **Kiểm tra kết nối:** báo tên file, tên tab, số dòng nếu kết nối thành công; nếu lỗi sẽ giải thích nguyên nhân.
- **Tạo tiêu đề cột trong sheet:** ghi tiêu đề cho các cột A-N.

### 3.2. Shopee
- **Thư mục lưu video:** mặc định là `data\videos`. Bấm **Chọn...** để đổi.
- **Trình duyệt dùng để tải:** nên để Microsoft Edge.
- **Hiện cửa sổ trình duyệt khi tải:** bỏ chọn thì trình duyệt chạy ẩn (thu nhỏ ngoài màn hình). Tick lên khi cần xem hoặc xử lý xác minh.
- **Chờ video tối đa (giây):** thời gian chờ video của mỗi link (mặc định 60).
- **Số link tối đa mỗi lần:** mặc định 10.
- **Nghỉ giữa 2 link:** khoảng nghỉ ngẫu nhiên (mặc định 30-90 giây) để giảm rủi ro bị Shopee chú ý.
- **Đăng nhập Shopee:** mở trình duyệt, bạn đăng nhập, rồi bấm **Tôi đã đăng nhập xong**. Phiên được lưu trên máy này. Hết hạn thì làm lại.
- **Xóa phiên đã lưu:** xóa phiên đăng nhập trên máy này.

### 3.3. Facebook
- **A. Ứng dụng Facebook:** App ID, App Secret (trong App settings > Basic của app Meta), phiên bản API (mặc định v25.0).
- **B. Lấy danh sách Page:** dán token người dùng từ Graph API Explorer rồi bấm **Lấy Page**. Chương trình tự đổi sang token dài hạn (trừ khi bạn tick "Token này đã là token dài hạn") và lấy token của từng Page. Chạy lại bước này bất cứ lúc nào để **thêm Page mới** hoặc **làm mới token**.
- **C. Tùy chọn đăng bài:**
  - **Hẹn giờ:** "Tự đăng khi đến giờ" (máy phải bật và chương trình đang chạy) hoặc "Nhờ Facebook hẹn giờ" (máy tắt vẫn đăng, giờ hẹn phải cách hiện tại từ khoảng 12 phút đến 29 ngày).
  - **Đưa link vào bình luận đầu tiên:** link nằm ở bình luận thay vì trong bài. Không áp dụng cho bài hẹn giờ trên Facebook.
  - **Chữ đứng trước link:** mặc định `Mua tại: `.
  - **Tối đa dòng/lần** và **Nghỉ giữa 2 bài:** mặc định 5 dòng, nghỉ 10-30 giây. Đăng liên tiếp quá sát nhau, nhất là cùng video lên nhiều Page, có thể bị Facebook coi là spam.
- **D. Danh sách Page:**
  - **Thêm thủ công:** nhập tên, Page ID, Page token.
  - **Đổi tên:** đặt tên ngắn dễ gõ trong cột F của sheet (ví dụ `meo`, `tienich`).
  - **Bật/Tắt:** Page bị tắt sẽ không được đăng (dòng nào nhắc Page đó sẽ báo lỗi).
  - **Xóa:** chỉ xóa khỏi chương trình, không ảnh hưởng Page trên Facebook.
  - **Kiểm tra:** thử token của các Page đang chọn (hoặc tất cả).

### 3.4. Chung
- **Mở thư mục dữ liệu**, **Xuất cấu hình...**, **Nhập cấu hình...** để sao lưu hoặc chuyển sang máy khác. File xuất ra **chứa token và App Secret**, hãy giữ bí mật.
- Bấm **Lưu cấu hình** ở góc dưới. Cấu hình cũng tự lưu khi bấm BẮT ĐẦU và khi đóng chương trình.

## 4. Cột trong Google Sheet

| Cột | Nội dung | Ai điền |
|---|---|---|
| A | Link sản phẩm Shopee | Bạn |
| B-E | Trạng thái tải, thời gian, file video, ghi chú | Chương trình |
| F | Page (tên hoặc ID; nhiều Page ngăn cách bằng dấu phẩy hoặc xuống dòng) | Bạn |
| G | Link affiliate (nếu trống sẽ dùng link ở cột A) | Bạn |
| H | Nội dung bài đăng | Bạn |
| I | Tag, ví dụ `#giadung #sale` hoặc `giadung, sale` | Bạn |
| J | Giờ đăng, ví dụ `04/10/2026 09:00` (để trống = đăng ngay) | Bạn |
| K-N | Trạng thái đăng, đã xử lý lúc, ID bài đăng, ghi chú đăng | Chương trình |

Bài đăng gồm: **nội dung**, rồi dòng **link** (`Mua tại: ...`), rồi các **tag**. Chỉ dòng có cột B là `Thành công` (đã tải xong) và đã điền cột F mới được đăng. Giờ đăng đã qua thì đăng ngay.

### Ý nghĩa trạng thái
| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Thành công (cột B) | Đã tải video | Điền cột F-J để đăng |
| Lỗi (cột B) | Không tải được, xem cột E | Sửa nguyên nhân, bật "Chạy lại các dòng Lỗi" |
| Thành công (cột K) | Đã đăng lên mọi Page | Không cần làm gì |
| Đã lên lịch | Facebook sẽ tự đăng đúng giờ | Không cần làm gì |
| Một phần | Một số Page đã lên, một số lỗi | Bật "Chạy lại..." để đăng nốt, không đăng trùng |
| Lỗi (cột K) | Không đăng được, xem cột N | Sửa nguyên nhân rồi chạy lại |
| Đang xử lý | Bị dừng giữa chừng | **Kiểm tra trên Facebook**; nếu chưa có bài thì xóa ô đó để chạy lại |

## 5. Tab Chạy

### 5.1. Chọn chức năng
- **Chỉ tải video:** tải video cho các link chưa tải.
- **Chỉ đăng Facebook:** đăng các video đã tải.
- **Tải rồi đăng (lần lượt):** tải xong rồi đăng. Nếu phần tải gặp lỗi, phần đăng vẫn chạy.
- **Tải và đăng song song:** vừa tải vừa đăng; video nào tải xong sẽ được đăng trong khoảng 1 phút.

### 5.2. Tùy chọn
- **Chạy thử:** chỉ kiểm tra và hiển thị những gì sẽ làm, không tải hay đăng thật, không ghi vào sheet.
- **Chạy lại các dòng Lỗi / Một phần:** làm lại các dòng bị lỗi.
- **Tải tối đa / Đăng tối đa:** giới hạn số lượng mỗi lượt.

### 5.3. BẮT ĐẦU và DỪNG
- Bấm **BẮT ĐẦU** để chạy. Chương trình kiểm tra cấu hình trước, thiếu gì sẽ báo rõ.
- Bấm **DỪNG** để dừng: chương trình dừng sau khi xong thao tác đang làm dở (ví dụ một video đang tải lên Facebook). Dòng đang làm dở được trả về trạng thái an toàn, không bị đăng trùng.

### 5.4. Tự động lặp lại
Tick **Tự chạy lại mỗi N phút**: chương trình chạy ngay, rồi chạy lại sau mỗi N phút kể từ lúc lượt trước kết thúc. Cách này thay cho Task Scheduler. Chương trình phải đang mở và máy không ở chế độ ngủ. Bấm DỪNG hoặc bỏ tick để tắt.

### 5.5. Xem kết quả
- **Bộ đếm** bên trái: số video tải thành công/lỗi, đăng thành công, đã lên lịch, một phần, lỗi, đang chờ đến giờ.
- **Nhật ký:** từng bước theo thời gian. Màu xanh là thành công, cam là cảnh báo, đỏ là lỗi.
- **Kết quả từng dòng:** mỗi dòng sheet đã xử lý ra sao.
- **Cảnh báo & lỗi (n):** gom riêng mọi cảnh báo và lỗi, bấm đúp để xem đầy đủ, có nút **Sao chép tất cả**.
- Khi kết thúc, một hộp thoại tổng kết hiện ra (có cảnh báo màu vàng nếu có lỗi). Nhật ký cũng được lưu trong `data\logs`.

## 6. Hẹn giờ đăng bài

- Để trống cột J: đăng ngay. Giờ đã qua: đăng ngay.
- Giờ trong tương lai với chế độ "Tự đăng khi đến giờ": dòng được bỏ qua cho đến giờ hẹn, và bài lên ở lần quét đầu tiên sau giờ đó. Cần bật **Tự chạy lại** hoặc chạy bằng tay.
- Với "Nhờ Facebook hẹn giờ": video được tải lên Facebook ngay và Facebook tự đăng đúng giờ, dòng có trạng thái **Đã lên lịch**. Giờ hẹn nằm ngoài khoảng 12 phút đến 29 ngày thì dòng chờ đến lượt quét sau.
- Giờ trong sheet được hiểu theo giờ của máy tính. Trong Google Sheet nên vào **Tệp > Cài đặt** đặt Ngôn ngữ là Việt Nam và Múi giờ là (GMT+07:00) Hà Nội, để `04/10/2026` không bị hiểu thành ngày 10 tháng 4.

## 7. Các cảnh báo và lỗi thường gặp

| Thông báo | Nguyên nhân và cách xử lý |
|---|---|
| Token không khớp | Token trong chương trình khác dòng TOKEN trong Apps Script, hoặc chưa triển khai phiên bản mới sau khi sửa |
| Apps Script đang là bản cũ | Bấm "Sao chép mã Apps Script", dán lại và triển khai phiên bản mới |
| Không bắt được link video | Sản phẩm không có video, hoặc Shopee đang yêu cầu đăng nhập/xác minh: đăng nhập lại Shopee, thử tick "Hiện cửa sổ trình duyệt" |
| Không mở được trình duyệt | Máy cần Microsoft Edge hoặc Chrome (xem tab Hệ thống) |
| Video dạng m3u8 cần ffmpeg | Cài `winget install ffmpeg` hoặc đặt ffmpeg.exe cạnh chương trình |
| Facebook báo lỗi 190 | Token hết hạn: lấy lại token và bấm "Lấy Page" |
| Facebook báo thiếu quyền (10/200) | App chưa có pages_manage_posts, publish_video; token tạo trước khi thêm quyền; hoặc tài khoản không phải quản trị Page |
| Giới hạn tốc độ (mã 4, 17, 32, 613...) | Chương trình dừng cả lượt; chờ vài giờ và tăng thời gian nghỉ giữa các bài |
| Không thấy Page 'X' | Tên ở cột F không khớp danh sách Page (đúng dấu tiếng Việt) hoặc dùng Page ID |
| Page đang bị tắt | Bật lại trong Cấu hình > Facebook |
| Không thấy file video | File đã bị xóa/di chuyển; tải lại hoặc sửa cột D |
| Giờ đăng không đọc được | Nhập dạng `04/10/2026 09:00` |

## 8. Chuyển sang máy khác

1. **Cách dễ nhất:** chép cả thư mục chương trình (gồm thư mục `data`) sang máy mới, mở ShopeeFBTool.exe.
2. **Hoặc:** ở máy cũ vào Cấu hình > Chung > **Xuất cấu hình...**; ở máy mới chép chương trình, vào Cấu hình > Chung > **Nhập cấu hình...**.
3. Phiên đăng nhập Shopee thường cần **đăng nhập lại** trên máy mới.
4. Không chạy cùng một sheet trên hai máy cùng lúc để tránh đăng trùng.

## 9. Bảo mật

- Thư mục `data` chứa token Page, App Secret, token Google Sheet và phiên đăng nhập Shopee. **Đừng gửi hoặc đưa lên mạng.**
- Nút **Sao chép báo cáo hỗ trợ** (tab Hệ thống) đã che thông tin bí mật, có thể gửi khi cần hỗ trợ.
