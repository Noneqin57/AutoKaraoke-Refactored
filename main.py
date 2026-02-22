# -*- coding: utf-8 -*-
"""
REATK Web 版入口

启动 uvicorn 服务并自动打开浏览器。
使用方式: python main.py
"""
import os
import sys
import time
import threading
import webbrowser

HOST = "127.0.0.1"
PORT = 18632


def open_browser():
    """延迟一秒后打开浏览器"""
    time.sleep(1.5)
    url = f"http://{HOST}:{PORT}"
    print(f"🌐 正在打开浏览器: {url}")
    webbrowser.open(url)


def main():
    """主入口"""
    import uvicorn

    print("=" * 50)
    print("  REATK - AutoKaraoke Refactored (Web 版)")
    print(f"  服务地址: http://{HOST}:{PORT}")
    print(f"  API 文档: http://{HOST}:{PORT}/docs")
    print("=" * 50)

    # 在后台线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # 启动 uvicorn
    uvicorn.run(
        "server:create_app",
        host=HOST,
        port=PORT,
        factory=True,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    # Windows multiprocessing 兼容
    from multiprocessing import freeze_support
    freeze_support()
    main()
