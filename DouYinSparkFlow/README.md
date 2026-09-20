# DouYinSparkFlow - Ứng dụng lõi (bản Douyin cũ, tham khảo)

**Cài TikTok SparkFlow trên macOS:** làm theo [README ở thư mục repo](../README.md#1-cài-và-chạy-trên-mac). Script macOS tự chọn Brave hoặc chuẩn bị Chromium; các lệnh Douyin/Docker bên dưới chỉ là tài liệu cũ.

> Hệ thống giữ lửa Douyin đa tài khoản - module source lõi

Đây là thư mục source lõi của DouYin SparkFlow, gồm toàn bộ logic nghiệp vụ, giao diện Web và task tự động.

> ⚠️ Project bên thứ ba không chính thức, không liên quan tới Douyin. Code tự viết trong thư mục này dùng giấy phép [PolyForm Noncommercial 1.0.0](../LICENSE), chỉ cho phi thương mại. Bạn chỉ được thao tác tài khoản của mình hoặc đã được ủy quyền, và tự chịu trách nhiệm tuân thủ quy định nền tảng/pháp luật.

---

## 📁 Cấu trúc thư mục

### `core/` - Module chức năng lõi

Code logic nghiệp vụ lõi, gồm tự động trình duyệt, gửi tin, quản lý bạn bè.

| File | Mô tả | Dung lượng |
|------|------|------|
| `browser.py` | Điều khiển trình duyệt và thao tác trang | 3.4 KB |
| `friends.py` | Quản lý và refresh danh sách bạn | 8.8 KB |
| `login.py` | Điều khiển luồng đăng nhập | 2.8 KB |
| `msg_builder.py` | Dựng nội dung tin nhắn (hitokoto, chúc phúc...) | 4.5 KB |
| `protocol_dispatch.py` | Phân phối và định tuyến protocol | 14.5 KB |
| `protocol_sender.mjs` | Protocol gửi tin (script Node.js) | 22.8 KB |
| `send_state.py` | Xác định trạng thái gửi chắc chắn / cần kiểm tra / trong ngày | 1.6 KB |
| `tasks.py` | **Lõi lập lịch** (task hẹn giờ, quản lý trạng thái) | 109.5 KB |

### `webui/` - Giao diện quản trị Web

Console quản trị Web bằng FastAPI, giao diện trực quan.

#### Module backend

| File | Mô tả |
|------|------|
| `app.py` | App chính FastAPI, định nghĩa route |
| `auth.py` | Xác thực user và quản lý session |
| `ops.py` | API thao tác (start/stop task, refresh bạn...) |

#### Resource frontend

```
webui/
├── static/              # Static
│   ├── app.css         # Style chủ đề (sáng/tối)
│   ├── app.js          # Script đổi theme
│   ├── lucide.min.js      # Thư viện icon local
│   ├── lucide-LICENSE.txt # Giấy phép icon
│   ├── styles.css      # Style cơ bản
│   └── multiPagePlugins/  # Plugin trình duyệt
└── templates/          # Template HTML
    ├── base.html       # Template layout cơ bản
    ├── dashboard.html  # Dashboard (màn hình chính)
    ├── login.html      # Trang đăng nhập
    ├── send_console.html  # Console gửi tin
    └── logs.html       # Xem log
```

### `utils/` - Module tiện ích

Hàm phụ trợ chung và quản lý cấu hình.

| File | Mô tả |
|------|------|
| `config.py` | Load và quản lý file cấu hình |
| `logger.py` | Cấu hình hệ thống log |
| `hitokoto.py` | Wrapper API hitokoto |
| `github_action_config.py` | Sinh cấu hình GitHub Actions |

### `scripts/` - Script phụ trợ

| File | Mô tả |
|------|------|
| `cron_runner.py` | Runner task cron |
| `start_login_desktop.sh` | Script khởi động desktop đăng nhập |

### `docs/` - Ảnh chụp màn hình

| Thư mục | Mô tả |
|----------|------|
| `images/` | Ảnh chụp giao diện và sơ đồ |

---

## 🚀 Cách chạy

### Chạy môi trường dev

#### 1. Cài dependency

```bash
# Dependency lõi
pip install -r requirements.txt

# Dependency Web UI
pip install -r requirements-web.txt

# Cài trình duyệt Playwright
playwright install chromium
```

#### 2. Cách khởi động

**Chế độ Web quản trị** (khuyên dùng)：
```bash
python main.py --web
# Mở http://localhost:8787
```

**Chế độ dòng lệnh**：
```bash
python main.py
# Chạy lập lịch trực tiếp
```

**Dịch vụ desktop đăng nhập**：
```bash
python login_desktop_server.py
# Khởi động API desktop đăng nhập (để quét mã)
```

### Chạy Docker

Tham khảo cấu hình `docker-compose.yml` ở thư mục gốc:

```bash
# Build image
docker build -f Dockerfile.server -t douyin-sparkflow:local .

# Chạy container
docker run -d \
  -p 8787:8787 \
  -v $(pwd):/app \
  douyin-sparkflow:local
```

---

## ⚙️ File cấu hình

### `config.example.json` và `config.json` - Cấu hình app

`config.example.json` là template công khai; lần chạy đầu sẽ sinh file `config.json` (không track Git) để lưu khung giờ gửi, quét bạn, Profile trình duyệt và chiến lược tin nhắn sửa trên Web:

```json
{
  "messageTemplate": "✨Giữ lửa hôm nay +1\n",
  "useProtocolSender": false,
  "browserSenderAccounts": [],
  "dailySendWindow": {
    "enabled": true,
    "startHour": 10,
    "endHour": 18,
    "scheduleIntervalMinutes": 20
  },
  "friendListScan": {
    "maxScanSeconds": 300,
    "idleScanSeconds": 120,
    "scrollStepPx": 400,
    "scrollDelaySeconds": 0.8
  },
  "persistentBrowserProfiles": {
    "enabled": true,
    "root": "/opt/douyin-sparkflow/state/browser-profiles",
    "seedCookiesWhenEmpty": true,
    "syncStoredCookiesBeforeRun": true,
    "refreshStoredCookiesAfterLogin": true
  }
}
```

| Mục cấu hình | Mô tả |
|--------|------|
| `dailySendWindow` | Khung giờ gửi mỗi ngày và khoảng lịch |
| `sendStrategy` | Delay mở tài khoản, khoảng cách tin và biến thể tin |
| `friendListScan` | Giới hạn quét danh sách bạn, chờ idle và thông số cuộn |
| `persistentBrowserProfiles` | Lưu Playwright Profile và chiến lược đồng bộ Cookie |
| `browserSenderAccounts` | Danh sách tài khoản ép gửi bằng trình duyệt; template mặc định rỗng |

### `usersData.json` - Dữ liệu user

Lưu thông tin tài khoản, danh sách bạn, lịch sử gửi... lúc chạy.

⚠️ **File chứa dữ liệu nhạy cảm, không commit lên Git**

Cấu trúc ví dụ:
```json
[
  {
    "unique_id": "123456789",
    "username": "Tên hiển thị tài khoản",
    "cookies": [],
    "targets": ["Bạn mục tiêu"],
    "enabled": true,
    "message_history": {},
    "failure_queue": {}
  }
]
```

### `webui_settings.json` - Cài đặt Web UI

Cấu hình giao diện quản trị Web (mật khẩu admin, port...).

⚠️ **File chứa dữ liệu nhạy cảm, không commit lên Git**

---

## 🔌 API

Web UI cung cấp các API RESTful sau:

### Quản lý tài khoản

- `GET /api/accounts` - Lấy danh sách tài khoản
- `POST /api/accounts/refresh` - Refresh danh sách bạn
- `DELETE /api/accounts/{id}` - Xóa tài khoản

### Điều khiển task

- `POST /api/tasks/start` - Bật task hẹn giờ
- `POST /api/tasks/stop` - Tắt task hẹn giờ
- `GET /api/tasks/status` - Lấy trạng thái task

### Quản lý đăng nhập

- `GET /api/login/qrcode` - Lấy mã QR đăng nhập
- `GET /api/login/status` - Kiểm tra trạng thái đăng nhập
- `POST /api/login/logout` - Đăng xuất

### Gửi tin nhắn

- `POST /api/send/manual` - Gửi tin thủ công
- `GET /api/send/history` - Lấy lịch sử gửi

Chi tiết API xem định nghĩa route trong `webui/app.py`.

---

## 🔧 Luồng hoạt động lõi

### 1. Luồng đăng nhập

```
User quét mã → browser.py mở trang đăng nhập
       → login.py sinh mã QR
       → User quét mã xác nhận
       → Lưu trạng thái đăng nhập vào state/
       → Trả về đăng nhập thành công
```

### 2. Refresh danh sách bạn

```
Bấm refresh → friends.py mở trình duyệt
        → Mở trang danh sách bạn
        → Parse dữ liệu bạn (nickname, trạng thái lửa...)
        → Lưu vào usersData.json
        → Đóng trình duyệt
```

### 3. Luồng gửi tin nhắn

```
Tới giờ → tasks.py kiểm tra điều kiện gửi
        → Lọc bạn cần gửi
        → msg_builder.py dựng nội dung tin
        → Theo cấu hình chọn gửi bằng trình duyệt Playwright hoặc protocol_sender.mjs
        → Chờ bằng chứng gửi chắc chắn
        → Ghi lịch sử gửi
        → Cập nhật giờ gửi tiếp theo
```

### 4. Logic lập lịch

`tasks.py` là scheduler lõi, phụ trách:

- ⏰ Kiểm tra khung giờ gửi theo lịch
- 🔄 Duyệt vòng mọi tài khoản
- 📊 Thống kê gửi thành công/thất bại
- 🛡️ Bảo vệ khi lỗi (cơ chế cooldown)
- 📝 Ghi log

---

## 🐛 Debug và phát triển

### Hệ thống log

File log nằm ở thư mục `logs/`:

```
logs/
├── app.log              # Log chính app
├── webui.log           # Log Web UI
├── tasks.log           # Log lập lịch
└── browser.log         # Log thao tác trình duyệt
```

Xem log realtime:
```bash
tail -f logs/app.log
```

### Gợi ý phát triển

1. **Sửa template**: sửa `webui/templates/*.html`, refresh trình duyệt là thấy (đã bật auto-reload)
2. **Sửa code Python**: cần restart service mới có hiệu lực
3. **Debug trình duyệt**: đặt `browser_headless: false` để thấy cửa sổ trình duyệt
4. **Test gửi tin**: dùng nút "Gửi thủ công" trên Web UI, khỏi chờ task hẹn giờ

### Câu hỏi thường gặp

**Q: Không hiện mã QR đăng nhập?**  
A: Kiểm tra `login_desktop_server.py` có đang chạy không, port 18090 có bị chiếm không.

**Q: Trình duyệt mở thất bại?**  
A: Chế độ Windows local chạy trước `.\scripts\start_login_desktop.ps1`; đồng thời đảm bảo đã cài Playwright:`playwright install chromium`

**Q: Gửi tin thất bại?**  
A: Kiểm tra mạng, xem `logs/app.log` hoặc log chạy trên Web.

**Q: Không mở được Web UI?**  
A: Kiểm tra port 8787 có bị chiếm không, firewall có cho phép không.

---

## 📦 Giải thích dependency

### `requirements.txt` - Dependency lõi

```
playwright>=1.40.0      # Tự động trình duyệt
cron_runner.py tùy chỉnh      # Lập lịch (không cần thêm dependency Python)
```

### `requirements-web.txt` - Dependency Web

```
fastapi>=0.104.0        # Framework Web
uvicorn>=0.24.0         # Server ASGI
jinja2>=3.1.0           # Template engine
```

Danh sách đầy đủ xem trong file `requirements*.txt`.

---

## 🔐 Lưu ý bảo mật

### Bảo vệ file nhạy cảm

Các file sau **tuyệt đối không** commit lên Git:

- ❌ `config.json` - Cấu hình gửi lúc chạy
- ❌ `usersData.json` - Chứa dữ liệu tài khoản và bạn bè
- ❌ `webui_settings.json` - Chứa mật khẩu admin
- ❌ `.env` - Chứa biến môi trường và key
- ❌ `state/` - Chứa trạng thái đăng nhập trình duyệt
- ❌ `logs/` - Có thể chứa log nhạy cảm
- ❌ `.im_sdk_cache/` - Cache IM SDK

Đã cấu hình ignore trong `.gitignore`.

### Bảo mật mật khẩu

- Đổi mật khẩu admin mặc định trong `webui_settings.json`
- Không lưu mật khẩu dạng text trong file cấu hình
- Dùng biến môi trường cho cấu hình nhạy cảm

---

## 📚 Tài liệu liên quan

- [README chính](../README.md) - Giới thiệu tổng quan và bắt đầu nhanh
- [Hướng dẫn dùng](../docs/usage.md) - Tutorial chi tiết
- [Changelog](../CHANGELOG.md) - Lịch sử cập nhật
- [Triển khai Docker](../docker-compose.yml) - Cấu hình container

---

## 🤝 Hướng dẫn đóng góp

Chào mừng đóng góp code và gợi ý tính năng!

Quy chuẩn phát triển:
- Code Python theo chuẩn PEP 8
- Chạy test trước khi commit để đảm bảo đúng
- Thêm comment cần thiết
- Cập nhật tài liệu liên quan

---

## 📄 Giấy phép

Code tự viết của project dùng giấy phép [PolyForm Noncommercial 1.0.0](../LICENSE), chỉ cho phi thương mại. Không dùng cho dịch vụ thu phí, kinh doanh, quản lý acc thuê, marketing, tích hợp sản phẩm thương mại... nếu chưa có văn bản cho phép.

Dependency bên thứ ba, icon, font, ảnh, screenshot, thương hiệu, nội dung nền tảng và tài nguyên ngoài khác theo giấy phép riêng; giấy phép icon Lucide xem [`webui/static/lucide-LICENSE.txt`](webui/static/lucide-LICENSE.txt).

---

<div align="center">

**Về [trang chính](../README.md)**

Made with ❤️ by [halfwaystudent](https://github.com/halfwaystudent)

</div>
