# TikTok SparkFlow — bản port cho macOS

Gửi tin nhắn theo lịch cho **các cuộc trò chuyện TikTok Web do bạn chọn**. Tái sử dụng dashboard FastAPI/Jinja, cấu hình JSON, mẫu tin nhắn, phân quyền và thuật toán phân bố giờ gửi của [DouYin SparkFlow](https://github.com/halfwaystudent/douyin-sparkflow).

**Trạng thái:** đã triển khai và kiểm thử với Chromium trên trang mô phỏng offline. **Chưa kiểm chứng DOM hoặc gửi tin trên tài khoản TikTok thật.** Selector mặc định là cấu hình khởi đầu, có thể phải sửa sau khi bạn đăng nhập. Không coi bản này là công cụ đã được chứng minh giữ streak thực tế.

Không đọc/giả lập điểm streak. Theo [TikTok](https://support.tiktok.com/vi/using-tiktok/messaging-and-notifications/streaks), streak gắn với việc trao đổi tin nhắn; công cụ này chỉ hỗ trợ phần gửi tin, không bảo đảm streak tăng hay còn hiệu lực.

## 1. Cài và chạy trên Mac

Cần Python 3.11 trở lên và kết nối truy cập TikTok bình thường. Đã chạy bộ kiểm thử trên macOS ARM64, Python 3.14.7, Playwright 1.56.0. Không cần Docker.

Trong Terminal, vào thư mục repo đã giải nén rồi chạy:

```bash
cd /duong/dan/toi/tiktok-sparkflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r DouYinSparkFlow/requirements.txt
PLAYWRIGHT_SKIP_BROWSER_GC=1 python -m playwright install chromium
bash DouYinSparkFlow/scripts/start_macos.sh
```

Mở [dashboard cục bộ](http://127.0.0.1:8787). Lần đầu tạo tài khoản quản trị của dashboard; đây **không phải mật khẩu TikTok**. Script khởi động cả dashboard và dịch vụ mở cửa sổ đăng nhập tại `127.0.0.1:18090`. Ctrl+C để tắt.

Mặc định `scheduleEnabled=false`; mở dashboard chưa gửi tin. Cả dashboard và helper chỉ lắng nghe loopback. Không dùng các hướng dẫn Docker/Douyin cũ trong `docs/upstream/` cho bản port này.

## 2. Đăng nhập và chọn chat

1. Mở **Đăng nhập bằng trình duyệt**, bấm **Thêm tài khoản TikTok**.
2. Trong Chromium trên Mac, tự đăng nhập bằng phương thức TikTok cung cấp. Tự hoàn thành QR, mật khẩu, OTP, CAPTCHA và xác minh thiết bị nếu có. Công cụ không xử lý hộ các bước này.
3. Quay lại dashboard và bấm **Lưu đăng nhập**. Công cụ đọc liên kết hồ sơ của chính tài khoản, lưu cookies và local storage cục bộ. Nếu không đọc được hồ sơ thì báo lỗi, không đoán tài khoản.
4. Trong **Tài khoản và chat**, bấm **Đọc các chat hiện có**, chọn người nhận và lưu. Hoặc nhập **`@username` chính xác, mỗi dòng một người**. Tên hiển thị không được chấp nhận; `alice123` và `bob123` không bị gộp vào ID `123`.
5. Chỉ hỗ trợ chat một-một đã có trong inbox và có liên kết hồ sơ đủ để xác định người nhận. Không tự tạo chat mới, gửi lời mời, quét follower hoặc hỗ trợ chat nhóm. Danh sách quét có giới hạn; thiếu chat không đồng nghĩa không có chat đó.

Đăng nhập qua Terminal cũng được:

```bash
cd DouYinSparkFlow
../.venv/bin/python main.py --login
```

Phiên đăng nhập lưu trong `DouYinSparkFlow/usersData.json` (quyền file 0600 khi ghi). Đây là dữ liệu nhạy cảm, không chia sẻ hoặc commit. Session hết hạn: đăng nhập lại **đúng tài khoản**. Đăng nhập lại không tự bỏ chặn các lần gửi chưa rõ kết quả.

## 3. Kiểm tra selector trước khi bật lịch

Chưa có session TikTok thật trong quá trình phát triển nên **không thể xác nhận selector mẫu khớp TikTok hiện tại, tài khoản hay khu vực của bạn**. Nếu selector không khớp, chương trình dừng; không tìm cách dùng API ẩn hoặc qua mặt xác minh.

Lệnh này chỉ mở trang, đọc danh sách và chọn chat, **không gõ/gửi tin**:

```bash
cd DouYinSparkFlow
../.venv/bin/python scripts/check_tiktok.py --account ten_tai_khoan --target @ten_nguoi_nhan
```

Khi báo `Expected one visible ...` hoặc không tìm thấy inbox:

- Dùng DevTools trong Chromium để kiểm tra DOM hiển thị trên tài khoản của bạn.
- Chỉnh các selector tương ứng trong `config.json` → `tiktok.selectors`; các trường không ghi đè dùng `core/tiktok.py:DEFAULT_SELECTORS`.
- `selfProfile` phải là đúng liên kết hồ sơ **của bạn**, không phải video/người đang xem.
- `chatList` phải là vùng cuộn của inbox; `chatRow` là một dòng chat; `rowProfile` là liên kết `/@username` bên trong dòng đó.
- `chatHeaderProfile` phải là liên kết hồ sơ **người nhận đang mở**.
- `composer` là vùng soạn `contenteditable`; `sendButton` là nút gửi trong chat đó.
- `outgoingMessage` phải chỉ khớp **nội dung tin do bạn gửi trong khung chat**, không khớp tin đến, sidebar, timestamp hay ô soạn.
- `challenge`, `login`, `restriction`, `sendFailure` phải phản ánh giao diện xác minh/đăng nhập/lỗi thực tế. Không xoá chúng để cố tiếp tục qua một cảnh báo.

Ví dụ cấu trúc (thay selector bằng giá trị đã kiểm tra trên DOM, không sao chép giá trị minh hoạ):

```json
{
  "tiktok": {
    "timeoutMs": 15000,
    "maxScrolls": 30,
    "selectors": {
      "selfProfile": "a[data-e2e='profile-icon']"
    }
  }
}
```

Nếu TikTok Web không cung cấp liên kết định danh người nhận hoặc không cho gửi DM, bản này không hỗ trợ gửi tự động trong giao diện đó. Không chọn theo tên hiển thị để lách kiểm tra định danh. Gửi thủ công bằng app trong trường hợp này.

## 4. Nội dung và lịch gửi

Trong **Mẫu tin nhắn**, đặt nội dung cố định. Nếu nhập danh sách mẫu, mỗi lần chọn một mẫu từ danh sách. Khoảng cách giữa hai chat là số giây cấu hình cố định; không dùng để né giới hạn.

Trong **Lịch gửi và nhật ký**, lưu:

- `10:00`: mỗi ngày sau 10:00, theo múi giờ cấu hình.
- `10:00-18:00/20m`: mỗi chat nhận một mốc ổn định trong ngày, theo các khoảng 20 phút trong khung giờ. Phân bố thời điểm được tái sử dụng từ repo gốc.

Ở đầu dashboard, đặt múi giờ IANA như `Asia/Seoul` hoặc `Asia/Ho_Chi_Minh`, tích **Bật gửi theo lịch** rồi lưu. Nếu biến môi trường `SPARKFLOW_TIMEZONE` được đặt thì nó ưu tiên hơn cấu hình.

Scheduler kiểm tra mỗi phút khi dashboard đang chạy. Một lần chạy có thể trễ vì trình duyệt, các chat trước đó, sleep của Mac hoặc lỗi mạng. Máy phải đang thức, có mạng và tiến trình vẫn chạy. Có thể chạy:

```bash
caffeinate -i bash DouYinSparkFlow/scripts/start_macos.sh
```

Đóng dashboard server thì lịch dừng. Không cài LaunchAgent, không sửa crontab và không tạo GitHub Actions gửi tin tự động. Nút **Gửi ngay** chỉ gửi các chat chưa được xử lý; không cưỡng ép gửi lại tin đã thử trong ngày.

## 5. Kết quả gửi và thao tác thủ công

- **Đã hiện trên Web:** thấy thêm tin outgoing đúng nội dung và ô soạn trống. Đây là phản hồi DOM, **không phải biên nhận từ máy chủ, xác nhận người nhận đã nhận hay bằng chứng giữ streak**. Bỏ qua chat đó hết ngày; ngày hôm sau có thể gửi tiếp.
- **Chưa rõ kết quả:** đã ghi ý định gửi trước khi bấm nút, nhưng không thấy phản hồi phù hợp, bị timeout hoặc tiến trình dừng. Chặn tự gửi lại kể cả sang ngày mới. Bạn phải mở TikTok kiểm tra.
- **Cần xử lý tài khoản:** CAPTCHA, yêu cầu đăng nhập/xác minh, HTTP 403/429, lỗi gửi, sai định danh, selector thay đổi hoặc lỗi trình duyệt làm dừng các chat còn lại của tài khoản. Không retry, đổi IP/proxy, ẩn automation hay gọi giao thức riêng.
- **Có tin nháp:** dừng, giữ nguyên tin nháp, để bạn tự xử lý.

Trong phần **Kiểm tra thủ công**:

1. Chọn chat, sau khi xem TikTok bấm **tin đã gửi** hoặc **chưa gửi — cho phép thử lại** đúng với thực tế.
2. Nếu tài khoản bị dừng, tự giải quyết nguyên nhân/xác minh rồi bấm **mở lại tài khoản**. Với phiên hết hạn, dùng đăng nhập lại.
3. Nút xác nhận chưa gửi không tự gửi ngay. Lần chạy tiếp theo mới xét lại; nếu cần, bấm Gửi ngay.

Không có cơ chế tự phục hồi streak, né hạn chế tài khoản hay bảo đảm phát hiện mọi biến thể CAPTCHA/lỗi của TikTok. Nếu thông báo/DOM không nhận diện được, thiếu các phần tử bắt buộc vẫn làm dừng luồng; trường hợp gửi không rõ kết quả được giữ lại để kiểm tra.

## 6. Mã và kiểm thử

- `core/tiktok.py`: hợp đồng selector, guard, xác định tài khoản/người nhận, scan inbox và một lần bấm gửi.
- `core/login.py`, `login_desktop_server.py`: đăng nhập thủ công trong Chromium.
- `core/browser.py`: Playwright thông thường, không đổi fingerprint/proxy fallback.
- `core/friends.py`: đọc chat có sẵn và session.
- `core/tasks.py`: lịch gửi, journal chống gửi trùng, trạng thái dừng và khoá tiến trình.
- `webui/`: dashboard/phân quyền cũ, thêm bật lịch, múi giờ, xử lý thủ công và login local.
- `utils/config.py`: giữ cấu trúc JSON, bổ sung `platform`, `scheduleEnabled`, `timezone`, `tiktok`.

```bash
source .venv/bin/activate
cd DouYinSparkFlow
python -m unittest discover -s tests -v
```

Tests trình duyệt chặn toàn bộ request và dùng fixture offline, không nhắn tin tới người thật. Chi tiết thay đổi và phạm vi kiểm chứng: [PORTING_NOTES.md](PORTING_NOTES.md).

Giữ giấy phép [PolyForm Noncommercial 1.0.0](LICENSE) và tác giả repo gốc. Bản port không đổi phạm vi cấp phép. Các tài liệu/deploy Douyin cũ được giữ trong `docs/upstream/` để tham khảo, không phải đường chạy được hỗ trợ của bản TikTok.
