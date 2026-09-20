# TikTok SparkFlow — bản port cho macOS

Gửi tin nhắn theo lịch cho **các cuộc trò chuyện TikTok Web do bạn chọn**. Tái sử dụng dashboard FastAPI/Jinja, cấu hình JSON, mẫu tin nhắn, phân quyền và thuật toán phân bố giờ gửi của [DouYin SparkFlow](https://github.com/halfwaystudent/douyin-sparkflow).

**Trạng thái:** đã triển khai và kiểm thử với Chromium trên trang mô phỏng offline. **Chưa kiểm chứng DOM hoặc gửi tin trên tài khoản TikTok thật.** Selector mặc định là cấu hình khởi đầu, có thể phải sửa sau khi bạn đăng nhập. Không coi bản này là công cụ đã được chứng minh giữ streak thực tế.

Không đọc/giả lập điểm streak. Theo [TikTok](https://support.tiktok.com/vi/using-tiktok/messaging-and-notifications/streaks), streak gắn với việc trao đổi tin nhắn; công cụ này chỉ hỗ trợ phần gửi tin, không bảo đảm streak tăng hay còn hiệu lực.

## 1. Cài và chạy trên Mac

Cần **Python 3.11 trở lên** và kết nối mạng để cài thư viện/trình duyệt. Hướng dẫn dưới đây dùng Python 3.11 để tránh Python cũ có sẵn trên macOS. Không cần Docker.

**Copy từng ô lệnh riêng → Enter → chờ chạy xong rồi mới chạy ô tiếp theo. Nếu có lỗi, dừng tại bước đó.** Không ghép lệnh `cd` và `python` trên cùng một dòng.

### Bước 1: Lấy repo và vào đúng thư mục

Nếu tải mới bằng Git, chạy lần lượt (thư mục đích `tiktok-sparkflow` chưa tồn tại):

```bash
mkdir -p "$HOME/Documents"
```

```bash
cd "$HOME/Documents"
```

```bash
git clone https://github.com/quyen2867/tiktok-sparkflow.git
```

```bash
cd tiktok-sparkflow
```

Nếu đã tải ZIP, **bỏ qua phần clone**. Ví dụ giải nén `tiktok-sparkflow-main` trong Documents thì dùng:

```bash
cd "$HOME/Documents/tiktok-sparkflow-main"
```

Nếu nằm trong Downloads thì dùng:

```bash
cd "$HOME/Downloads/tiktok-sparkflow-main"
```

Chỉ chọn lệnh khớp vị trí thật. Với vị trí/tên khác: gõ `cd ` (có dấu cách), kéo thư mục từ Finder vào Terminal rồi Enter. Cách này xử lý cả tên thư mục có dấu cách. Dùng thư mục ngoài cùng chứa README này và `DouYinSparkFlow`; không cần vào bản sao `tiktok-sparkflow-VI`.

Xác nhận đường dẫn requirements tồn tại trước khi tiếp tục:

```bash
ls DouYinSparkFlow/requirements.txt
```

### Bước 2: Python và môi trường riêng

Kiểm tra Python:

```bash
python3.11 --version
```

Nếu chưa có Python 3.11 và máy đã có [Homebrew](https://brew.sh/):

```bash
brew install python@3.11
```

Nếu chưa dùng Homebrew, có thể cài Python từ [python.org](https://www.python.org/downloads/macos/). Nếu đã có Python mới hơn, thay **riêng `python3.11`** trong lệnh tạo môi trường bằng tên Python đó, ví dụ `python3.13`; phải là phiên bản >=3.11. Script cũng kiểm tra phiên bản thật trong `.venv` trước khi chạy.

Tại thư mục repo, tạo môi trường:

```bash
python3.11 -m venv .venv
```

Kích hoạt:

```bash
source .venv/bin/activate
```

Kiểm tra phải ra Python 3.11 trở lên:

```bash
python --version
```

Nâng cấp pip:

```bash
python -m pip install --upgrade pip
```

Cài thư viện (đã bao gồm dashboard; không cần cài riêng `requirements-web.txt`):

```bash
python -m pip install -r DouYinSparkFlow/requirements.txt
```

### Bước 3: Chạy

```bash
bash DouYinSparkFlow/scripts/start_macos.sh
```

Script tự dùng **Brave** nếu có tại `/Applications/Brave Browser.app/Contents/MacOS/Brave Browser`. **Không cần export biến môi trường hoặc cài Chromium khi đã có Brave.** Nếu không có Brave, script dùng Chromium của Playwright và tự tải khi thiếu; lần đầu cần mạng và có thể mất vài phút. Terminal sẽ báo trình duyệt được chọn trước khi khởi động dịch vụ.

Nếu đã chủ động đặt `SPARKFLOW_BROWSER_EXECUTABLE` hoặc `SPARKFLOW_BROWSER_CHANNEL`, cấu hình đó được ưu tiên. Cả dashboard và dịch vụ đăng nhập nhận cùng cấu hình trình duyệt.

Lần sau chỉ cần vào lại đúng thư mục repo rồi chạy lệnh ở Bước 3; script tự dùng `.venv` của repo nên không cần activate lại.

Mở [dashboard cục bộ](http://127.0.0.1:8787). Lần đầu tạo tài khoản quản trị của dashboard; đây **không phải mật khẩu TikTok**. Script khởi động cả dashboard và dịch vụ mở cửa sổ đăng nhập tại `127.0.0.1:18090`. Ctrl+C để tắt.

Mặc định `scheduleEnabled=false`; mở dashboard chưa gửi tin. Cả dashboard và helper chỉ lắng nghe loopback. Không dùng các hướng dẫn Docker/Douyin cũ trong `docs/upstream/` cho bản port này.

## 2. Đăng nhập và chọn chat

1. Mở **Đăng nhập bằng trình duyệt**, bấm **Thêm tài khoản TikTok**.
2. Trong Brave hoặc Chromium trên Mac, tự đăng nhập bằng phương thức TikTok cung cấp. Tự hoàn thành QR, mật khẩu, OTP, CAPTCHA và xác minh thiết bị nếu có. Công cụ không xử lý hộ các bước này.
3. Quay lại dashboard và bấm **Lưu đăng nhập**. Công cụ đọc liên kết hồ sơ của chính tài khoản, lưu cookies và local storage cục bộ. Nếu không đọc được hồ sơ thì báo lỗi, không đoán tài khoản.
4. Trong **Tài khoản và chat**, bấm **Đọc các chat hiện có**, chọn người nhận và lưu. Hoặc nhập **`@username` chính xác, mỗi dòng một người**. Tên hiển thị không được chấp nhận; `alice123` và `bob123` không bị gộp vào ID `123`.
5. Chỉ hỗ trợ chat một-một đã có trong inbox và có liên kết hồ sơ đủ để xác định người nhận. Không tự tạo chat mới, gửi lời mời, quét follower hoặc hỗ trợ chat nhóm. Danh sách quét có giới hạn; thiếu chat không đồng nghĩa không có chat đó.

Đăng nhập qua Terminal cũng được (bắt đầu tại thư mục repo):

```bash
cd DouYinSparkFlow
```

```bash
../.venv/bin/python main.py --login
```

Phiên đăng nhập lưu trong `DouYinSparkFlow/usersData.json` (quyền file 0600 khi ghi). Đây là dữ liệu nhạy cảm, không chia sẻ hoặc commit. Session hết hạn: đăng nhập lại **đúng tài khoản**. Đăng nhập lại không tự bỏ chặn các lần gửi chưa rõ kết quả.

## 3. Kiểm tra selector trước khi bật lịch

Chưa có session TikTok thật trong quá trình phát triển nên **không thể xác nhận selector mẫu khớp TikTok hiện tại, tài khoản hay khu vực của bạn**. Nếu selector không khớp, chương trình dừng; không tìm cách dùng API ẩn hoặc qua mặt xác minh.

Bắt đầu tại thư mục repo. Lệnh này chỉ mở trang, đọc danh sách và chọn chat, **không gõ/gửi tin**:

```bash
cd DouYinSparkFlow
```

```bash
../.venv/bin/python scripts/check_tiktok.py --account ten_tai_khoan --target @ten_nguoi_nhan
```

Khi báo `Expected one visible ...` hoặc không tìm thấy inbox:

- Dùng DevTools trong Brave/Chromium để kiểm tra DOM hiển thị trên tài khoản của bạn.
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
- `core/login.py`, `login_desktop_server.py`: đăng nhập thủ công trong Brave/Chromium.
- `core/browser.py`: Playwright thông thường, không đổi fingerprint/proxy fallback.
- `core/friends.py`: đọc chat có sẵn và session.
- `core/tasks.py`: lịch gửi, journal chống gửi trùng, trạng thái dừng và khoá tiến trình.
- `webui/`: dashboard/phân quyền cũ, thêm bật lịch, múi giờ, xử lý thủ công và login local.
- `utils/config.py`: giữ cấu trúc JSON, bổ sung `platform`, `scheduleEnabled`, `timezone`, `tiktok`.

Từ thư mục repo, chạy từng lệnh. Bộ kiểm thử offline gọi Chromium trực tiếp, nên riêng khi chạy tests cần cài Chromium kể cả máy đã có Brave:

```bash
source .venv/bin/activate
```

```bash
python -m playwright install chromium
```

```bash
cd DouYinSparkFlow
```

```bash
python -m unittest discover -s tests -v
```

Tests trình duyệt chặn toàn bộ request và dùng fixture offline, không nhắn tin tới người thật. Chi tiết thay đổi và phạm vi kiểm chứng: [PORTING_NOTES.md](PORTING_NOTES.md).

## 7. Troubleshooting trên macOS

### `cd: too many arguments` hoặc không tìm thấy thư mục

Lỗi này thường do dán `cd` và lệnh tạo `.venv` dính trên một dòng, hoặc đường dẫn có dấu cách chưa được đặt trong dấu nháy. Chạy từng ô lệnh ở Bước 1, không nối thêm `python` sau lệnh `cd`. Với thư mục có tên khác, kéo từ Finder vào Terminal sau `cd `.

Kiểm tra đang ở đâu:

```bash
pwd
```

Kiểm tra đúng thư mục repo:

```bash
ls DouYinSparkFlow/requirements.txt
```

Nếu không thấy file này thì quay lại Bước 1; chưa cài requirements hay chạy script.

### Python quá cũ / `No matching distribution found` / `Requires-Python`

```bash
python --version
```

Nếu thấp hơn 3.11, cài Python 3.11 trở lên như Bước 2. Nâng pip không thể nâng phiên bản Python trong `.venv`. Tại thư mục repo, nếu đang activate môi trường thì thoát trước:

```bash
deactivate
```

Giữ lại môi trường cũ bằng cách đổi tên (nếu `.venv-old` đã tồn tại, chọn tên khác):

```bash
mv .venv .venv-old
```

Sau đó chạy lại từng lệnh ở Bước 2 từ tạo `.venv`, activate, nâng pip tới cài requirements. Nếu Python đã đủ mới mà pip vẫn lỗi, kiểm tra kết nối mạng và dòng lỗi tên gói cụ thể.

### `Executable doesn't exist` / thiếu browser executable

Chạy lại script ở Bước 3: script tự nhận Brave hoặc tải Chromium vào vị trí Playwright đang sử dụng. Nếu tải thất bại, kiểm tra mạng và dung lượng trống rồi chạy lại.

Nếu từng thử export biến từ hướng dẫn cũ, bỏ cấu hình cũ trong Terminal hiện tại bằng từng lệnh sau rồi chạy lại script:

```bash
unset SPARKFLOW_BROWSER_EXECUTABLE
```

```bash
unset SPARKFLOW_BROWSER_CHANNEL
```

```bash
unset PLAYWRIGHT_BROWSERS_PATH
```

Không cần đặt `PLAYWRIGHT_BROWSERS_PATH=0` hay `BROWSER_EXECUTABLE`. Nếu biến cũ được khai báo trong `~/.zshrc`, bỏ dòng khai báo đó để Terminal mới không dùng lại. Một đường dẫn `SPARKFLOW_BROWSER_EXECUTABLE` được đặt thủ công nhưng không tồn tại sẽ báo lỗi rõ, thay vì âm thầm chọn trình duyệt khác.

Giữ giấy phép [PolyForm Noncommercial 1.0.0](LICENSE) và tác giả repo gốc. Bản port không đổi phạm vi cấp phép. Các tài liệu/deploy Douyin cũ được giữ trong `docs/upstream/` để tham khảo, không phải đường chạy được hỗ trợ của bản TikTok.
