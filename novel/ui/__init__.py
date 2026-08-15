"""Web GUI entry point: `uv run novel-ui`."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    import argparse
    import threading
    import webbrowser

    import uvicorn

    from novel.ui.app import create_app

    parser = argparse.ArgumentParser(prog="novel-ui", description="多智能体小说生成 - 图形界面")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="小说项目所在的根目录")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    app = create_app(args.root)
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"novel GUI 运行中: {url}  (Ctrl+C 退出)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
