import json
from rich.console import Console
from rich.panel import Panel
from utils.config import get_config
import pyperclip

config = get_config()

# Khởi tạo console rich
console = Console()


def compress_users_data():
    # Nén nội dung usersData.json
    with open("usersData.json", "r", encoding="utf-8") as f:
        user_data = json.loads(f.read())

    return json.dumps(user_data, ensure_ascii=False)


def print_github_action_config():
    """
    In bảng cấu hình GitHub Action
    """

    # In hướng dẫn các bước chuẩn bị
    steps = (
        "1. Đảm bảo đã clone repo và bật "
        "[bold green]TikTok SparkFlow Schedule Run[/bold green] trong tab [bold yellow]Action[/bold yellow]\n"
        "2. Trong tab Settings của repo, mục [bold yellow]Environment[/bold yellow], thêm môi trường "
        "[bold green]user-data[/bold green] rồi thêm lần lượt các Secrets bên dưới vào Secrets của môi trường đó"
    )
    console.print(Panel(steps, title="Bước chuẩn bị", expand=False, style="bold cyan"))

    secrets = {
        "USER_DATA": compress_users_data()
    }
    if "proxyAddress" in config and config["proxyAddress"]:
        secrets["proxyAddress"] = config["proxyAddress"]

    # In từng key và value
    console.print("\n[bold yellow]Cấu hình Secrets: bôi đen rồi chuột phải để copy (không có menu popup thì bấm chuột phải là đã copy xong!)[/bold yellow]")

    for key, value in secrets.items():
        console.rule(f"[bold cyan]{key}[/bold cyan]")
        console.print(f"[green]{value}[/green]\n")

    pyperclip.copy(secrets["USER_DATA"])
    console.print("[bold yellow]Gợi ý:[/bold yellow][bold magenta] Giá trị USER_DATA đã tự chép vào clipboard (nên dán trực tiếp, copy tay dễ dính khoảng trắng thừa gây lỗi) [/bold magenta]")