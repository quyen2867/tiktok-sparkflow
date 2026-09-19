# Ghi chú chuyển Douyin → TikTok

Nguồn: `halfwaystudent/douyin-sparkflow`, commit `7c7d9c2f79a664c7dbf2b174c0e7caf0fdc3c37b`. Mốc thực hiện: 18/09/2026. Giữ thư mục `DouYinSparkFlow` để giảm thay đổi đường dẫn import và dashboard.

## Những phần phụ thuộc nền tảng được phát hiện

| Phần | Repo gốc | Bản TikTok |
|---|---|---|
| `core/login.py` | QR/identity từ Douyin Creator Center, XPath `garfish_app_for_douyin_creator_pc_home` | Người dùng đăng nhập trong Chromium, đọc link profile của chính mình, lưu cookies/local storage |
| `core/browser.py` | Đường mạng Douyin direct/Mihomo, kiểm tra route và fallback; profile `/opt/...` | Playwright thông thường, không fallback proxy, không đổi fingerprint; session cục bộ |
| `core/friends.py` | Trang private chat Creator Center, tab friends và DOM Douyin | Inbox `https://www.tiktok.com/messages`, đọc chat đã có theo liên kết `/@username` |
| `core/tasks.py` | Khoảng 2.800 dòng trộn scheduler, selector, logic Douyin IM, friend scan, retry | Engine TikTok nhỏ hơn, giữ phân bố giờ bằng hash, template và schema lịch sử; kiểm tra định danh và journal trước gửi |
| `core/protocol_dispatch.py`, `protocol_sender.mjs` | Giao thức gửi riêng Douyin | Dispatcher từ chối chạy; xóa sender riêng khỏi bản port |
| `login_desktop_server.py` | Login desktop/noVNC, network preflight, QR extraction, debug/network actions | Dịch vụ local chỉ mở/đóng/focus cửa sổ và xuất session sau khi đăng nhập thủ công |
| `webui/ops.py` | Tự chọn Docker, `/var/log`, crontab và retry/fallback | Chạy Python local, log trong app, scheduler cùng vòng đời dashboard; không ghi crontab |
| `utils/config.py` | ID bị lọc còn chữ số, Douyin defaults | Giữ nguyên username chữ+số; thêm platform, múi giờ, bật lịch và selector tùy chỉnh |

## Phần được tái sử dụng

FastAPI/Jinja, CSS và phần lớn JavaScript dashboard; quản trị user và quyền sở hữu tài khoản; CSRF/session; hàng đợi login workspace; JSON config/account store và ghi file atomic; message builder; schema message history/failure; thuật toán phân bố giờ gửi theo ngày/tài khoản/target. Scheduler native dùng lại cấu hình khung giờ nhưng thay lớp thực thi crontab/Docker để phù hợp macOS.

Giữ tương thích tên field/API ở dashboard, nên một số tên biến nội bộ như `friends_cache`, `today_confirmed_targets` còn giữ tên cũ. Bộ đếm trên UI bao gồm phản hồi Web hoặc người dùng xác nhận; không phải xác nhận streak. Giao diện, trạng thái cập nhật trực tiếp, hộp xác nhận và thông báo do ứng dụng tạo đã được Việt hóa. Nội dung do người dùng nhập, nội dung TikTok và chẩn đoán từ thư viện bên ngoài được giữ nguyên.

Tài liệu/deploy/workflow và test riêng của Douyin đã chuyển sang `docs/upstream/`. Workflow lịch cũ đổi đuôi `.disabled`, không chạy. Bộ test nền tảng cũ được thay bằng test TikTok; test phân quyền và web safety phù hợp được giữ/cập nhật. Docker/noVNC/Windows/GitHub Actions sending không phải đường chạy được hỗ trợ của bản port macOS này.

## Hành vi gửi và kiểm soát lỗi

- Chỉ tài khoản `platform=tiktok`, bật gửi và có target do người dùng chọn mới được xét.
- Không định danh bằng display name, không tìm gần đúng. Chat phải có đúng một liên kết định danh; header người nhận được kiểm tra lại trước khi bấm gửi.
- Không có queue tự retry khi lỗi. Một lỗi làm dừng tài khoản đến khi người dùng xử lý.
- Ghi journal trước nút gửi. Nếu không thấy echo, giữ `needsVerification=true` qua các ngày. Không suy ra thành công từ ô soạn đã trống.
- Nếu thấy outgoing echo đúng nội dung và ô soạn trống: đánh dấu phản hồi Web mức yếu, chống gửi lại cùng ngày; cho phép ngày tiếp theo. Đây không phải delivery receipt.
- Khóa `flock` ngăn hai sender chạy đồng thời. Ghi account từ dashboard cũng giữ khóa đó để tránh ghi đè journal đang gửi.
- CAPTCHA/login/restriction, HTTP 403/429 và UI lỗi được nhận diện thì dừng. Không giả mạo browser fingerprint, dùng stealth, đổi proxy, giải CAPTCHA, gửi API riêng hoặc vượt hạn chế.
- Nội dung tin nháp sẵn có được bảo toàn bằng cách dừng trước khi ghi đè.

## Phạm vi kiểm chứng

Ngày 18/09/2026:

- **45 tests passed** với `python -m unittest discover -s tests -v`.
- Chromium thật trên macOS ARM64, Python 3.14.7, Playwright 1.56.0.
- Tests trình duyệt intercept toàn bộ mạng bằng fixture HTML offline. Kiểm tra: đọc hai người có cùng tên hiển thị nhưng khác username, sai người nhận, duplicate row, thiếu chat, tin nháp, CAPTCHA/429, thiếu echo, journal lỗi và không bấm gửi lần hai.
- Tests lịch: tắt/bật opt-in, giờ cố định, múi giờ, `endHour=24`, chống gửi cùng ngày, chặn tin chưa rõ qua ngày mới, khóa chồng tiến trình.
- Tests dashboard/API: render với account/session mẫu, không lộ session trong HTML, CSRF, giới hạn target đã chọn, resolution thủ công, helper chống origin/host không hợp lệ, đăng nhập lại sai tài khoản.
- Python compile, dependency consistency và kiểm tra khoảng trắng diff đều qua.
- Khởi động Uvicorn thật, mở trang login bằng Chromium, kiểm tra HTTP 200 và giao diện; shutdown sạch.

**Chưa kiểm chứng:** login trên TikTok thật, DOM/selector theo khu vực, TikTok có chấp nhận DM Web và có tính streak hay không, vận hành lịch nhiều ngày. Không có tin nào được gửi tới người thật khi làm bản port.

Selector mặc định là **hợp đồng DOM để khởi đầu và kiểm thử**, không phải selector đã trích từ session TikTok hiện tại. Việc kiểm tra/chỉnh selector trên session thật là bước triển khai cần thiết, có lệnh `scripts/check_tiktok.py` không gửi tin. Nếu không có định danh/DM trên Web, chương trình dừng và cần dùng app thủ công.

## Tài liệu tham chiếu

- [Repo gốc](https://github.com/halfwaystudent/douyin-sparkflow).
- [TikTok: Streak](https://support.tiktok.com/vi/using-tiktok/messaging-and-notifications/streaks) — chức năng dựa vào việc trao đổi tin nhắn; không suy ra điểm streak từ một outgoing echo.
- [Playwright: authentication state](https://playwright.dev/python/docs/auth) — lưu/khôi phục trạng thái trình duyệt.
- [Playwright: input](https://playwright.dev/python/docs/input) — thao tác DOM thông thường, không force-click.

## Bản giao diện tiếng Việt

Đã Việt hóa toàn bộ các trang đăng nhập, tổng quan, tài khoản, người dùng, cấu hình, theo dõi gửi tin và nhật ký; gồm cả thông báo JavaScript, nhãn trợ năng, trạng thái lỗi và thông báo từ máy chủ. Định dạng ngày hiển thị dùng ngày/tháng và locale vi-VN. Đã đổi mã phiên bản tài nguyên tĩnh để trình duyệt tải bản dịch mới. Không đổi dữ liệu tài khoản hay nội dung tin nhắn do người dùng đặt.
