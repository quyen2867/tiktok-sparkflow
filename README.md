# tiktok-sparkflow

Gửi tin nhắn TikTok theo lịch qua TikTok Web, điều khiển bằng dashboard chạy local. Port từ [douyin-sparkflow](https://github.com/halfwaystudent/douyin-sparkflow) sang TikTok + macOS.

Chỉ gửi cho chat 1-1 đã có sẵn trong inbox, theo @username bạn chọn. Không tạo chat mới, không đọc điểm streak.

## Chạy trên Mac

Cần Python 3.11 trở lên. Có Brave sẵn trong Applications thì script tự dùng Brave, chưa có thì dùng Chromium của Playwright.

```bash
git clone https://github.com/quyen2867/tiktok-sparkflow.git
cd tiktok-sparkflow
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -r DouYinSparkFlow/requirements.txt
bash DouYinSparkFlow/scripts/start_macos.sh
```

Mở http://127.0.0.1:8787, tạo tài khoản admin cho dashboard (không phải mật khẩu TikTok). Ctrl+C để tắt.

## Dùng

1. Đăng nhập bằng trình duyệt -> Thêm tài khoản TikTok, tự đăng nhập và xác minh trong cửa sổ hiện ra, rồi bấm Lưu đăng nhập.
2. Tài khoản và chat -> Đọc các chat hiện có, tick người nhận. Nhập tay cũng được, mỗi dòng một @username chính xác.
3. Đổi nội dung ở phần Mẫu tin nhắn, đặt khung giờ ở Lịch gửi và nhật ký, bật gửi theo lịch.
4. Nút Gửi ngay chỉ gửi các chat chưa xử lý trong ngày.
5. "Đã hiện trên Web" mới chỉ nghĩa là thấy tin trong trang, chưa chắc đã giao. Chat nào trạng thái chưa rõ thì mở TikTok kiểm tra tay rồi bấm đã gửi / chưa gửi trong phần Kiểm tra thủ công.

Muốn kiểm tra selector có khớp tài khoản của mình không (chỉ đọc, không gửi):

```bash
cd DouYinSparkFlow
../.venv/bin/python scripts/check_tiktok.py --account <ten_tai_khoan> --target @<nguoi_nhan>
```

Session lưu ở `DouYinSparkFlow/usersData.json`, đừng commit file này.

## Test

```bash
cd DouYinSparkFlow
python -m unittest discover -s tests -v
```

## License

PolyForm Noncommercial 1.0.0, xem [LICENSE](LICENSE). Code gốc của repo douyin-sparkflow.
