import argparse
import asyncio

from rich.console import Console
from rich.prompt import Prompt

from core.login import userLogin



console = Console()


def interactive_cli():
    console.print("[bold green]Chào mừng đến với TikTok SparkFlow[/bold green]")
    console.print("[bold yellow]Chọn thao tác:[/bold yellow]")
    console.print("[cyan]1.[/cyan] Thêm tài khoản đăng nhập")
    console.print("[cyan]2.[/cyan] Kiểm tra bộ chọn giao diện TikTok (không gửi tin)")
    console.print("[cyan]3.[/cyan] Chạy lượt gửi trên máy này")
    console.print("[cyan]4.[/cyan] Mở bảng điều khiển")

    choice = Prompt.ask("Nhập lựa chọn (1/2/3/4)", choices=["1", "2", "3", "4"])

    if choice == "1":
        console.print("[bold blue]Đang mở cửa sổ đăng nhập...[/bold blue]")
        while True:
            asyncio.run(userLogin())
            if Prompt.ask("Tiếp tục thêm tài khoản? (y: có / n: không)", choices=["y", "n"]) == "n":
                break
    elif choice == "2":
        console.print("Chạy: python scripts/check_tiktok.py --account TEN_TAI_KHOAN")
    elif choice == "3":
        from core.tasks import runTasks

        asyncio.run(runTasks())
    else:
        from webui.app import run_web_app

        run_web_app()


def build_parser():
    parser = argparse.ArgumentParser(description="TikTok SparkFlow")
    parser.add_argument("--login", action="store_true", help="Mở cửa sổ đăng nhập TikTok thủ công")
    parser.add_argument("--doTask", action="store_true", help="Chạy lượt gửi tin ngay")
    parser.add_argument("--web", action="store_true", help="Khởi động bảng điều khiển")
    parser.add_argument("--host", default=None, help="Địa chỉ lắng nghe của bảng điều khiển")
    parser.add_argument("--port", type=int, default=None, help="Cổng của bảng điều khiển")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.login:
        asyncio.run(userLogin())
    elif args.doTask:
        from core.tasks import runTasks

        asyncio.run(runTasks())
    elif args.web:
        from webui.app import run_web_app

        run_web_app(host=args.host, port=args.port)
    else:
        interactive_cli()
