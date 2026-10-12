"""文献知识抽取系统 - 一键启动入口

用法:
    uv run python run.py        (或直接双击 start.bat)

行为:
- 若 frontend/node_modules 或 frontend/dist 不存在, 先自动安装前端依赖并构建(需要 Node.js/npm)
- 在 :8000 单端口启动后端(同时托管前端页面与 API)
- 服务就绪后自动打开浏览器
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"
PORT = int(os.environ.get("MKE_PORT", "8000"))


def _npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def ensure_frontend_deps() -> None:
    """首次运行时安装前端依赖(node_modules 不入库, 需机器已装 Node.js/npm)。"""
    if (ROOT / "frontend" / "node_modules").is_dir():
        return
    print("前端依赖未安装, 先执行 npm install(约 1 分钟)...")
    subprocess.run([_npm(), "install"], cwd=str(ROOT / "frontend"), check=True)


def build_frontend() -> None:
    """首次运行时安装依赖并构建前端产物(frontend/dist)。"""
    print("frontend/dist 不存在, 先构建前端(约 1 分钟)...")
    ensure_frontend_deps()
    subprocess.run([_npm(), "run", "build"], cwd=str(ROOT / "frontend"), check=True)


def wait_and_open_browser() -> None:
    """轮询健康检查, 服务就绪后打开浏览器。"""
    url = f"http://localhost:{PORT}"
    for _ in range(120):  # 最多等 60 秒
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{url}/api/health", timeout=2)
            print(f"\n服务已就绪: {url} (Ctrl+C 停止)")
            webbrowser.open(url)
            return
        except Exception:
            pass
    print(f"\n服务启动较慢, 请手动访问 {url}")


def main() -> None:
    # Windows 控制台默认 GBK，打印 emoji（如 core 模块日志里的 🔧）会抛 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="replace")

    if not (DIST / "index.html").exists():
        try:
            build_frontend()
        except FileNotFoundError:
            raise SystemExit("未找到 npm, 请先安装 Node.js(自带 npm): https://nodejs.org") from None
        except subprocess.CalledProcessError:
            raise SystemExit("前端安装或构建失败, 请手动执行: cd frontend; npm install; npm run build") from None
    threading.Thread(target=wait_and_open_browser, daemon=True).start()

    import uvicorn

    from backend.main import app

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止")
        sys.exit(0)
