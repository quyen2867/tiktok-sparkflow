"""Private protocol sending is intentionally unavailable in this port."""
async def run_protocol_tasks(*args, **kwargs):
    raise RuntimeError("Bản TikTok chỉ hỗ trợ gửi qua giao diện trình duyệt")
