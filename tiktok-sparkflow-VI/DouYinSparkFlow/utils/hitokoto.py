import requests
from utils.config import get_config

hitokotoApi = "https://v1.hitokoto.cn/"

# Bảng map thể loại hitokoto (giữ key tiếng Trung cũ để tương thích config cũ,
# thêm key tiếng Việt để người dùng mới dễ dùng).
allHitokotoTypes = {
    "动画": "a",
    "漫画": "b",
    "游戏": "c",
    "文学": "d",
    "原创": "e",
    "来自网络": "f",
    "其他": "g",
    "影视": "h",
    "诗词": "i",
    "哲学": "k",
    "抖机灵": "l",
    # Alias tiếng Việt
    "Hoạt hình": "a",
    "Truyện tranh": "b",
    "Game": "c",
    "Văn học": "d",
    "Sáng tác": "e",
    "Sưu tầm mạng": "f",
    "Khác": "g",
    "Phim ảnh": "h",
    "Thơ ca": "i",
    "Triết học": "k",
    "Hài hước": "l",
}


def request_hitokoto():
    """Gọi API hitokoto để lấy một câu quote"""
    config = get_config()
    
    api_url = hitokotoApi

    for t in allHitokotoTypes.keys():
        if t in config["hitokotoTypes"]:
            if "?" not in api_url:
                api_url += "?"
            if "c=" in api_url:
                api_url += f"&c={allHitokotoTypes[t]}"
            else:
                api_url += f"c={allHitokotoTypes[t]}"

    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        theFrom = data.get("from")
        if theFrom is None or theFrom.strip() == "":
            theFrom = "Không rõ nguồn"
        theFromWho = data.get("from_who")
        if theFromWho is None or theFromWho.strip() == "":
            theFromWho = "Không rõ tác giả"
        return f"{data['hitokoto']} —— {theFrom} ({theFromWho})"
    except Exception:
        return "[lỗi] Không lấy được nội dung hitokoto"
