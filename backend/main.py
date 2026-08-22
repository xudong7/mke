# backend/main.py
"""MKE Web API 入口：uv run uvicorn backend.main:app --reload --port 8000

- /api/* 业务端点（papers / pipeline / annotations / health）
- 生产模式：托管 frontend/dist 构建产物，SPA 路由回退到 index.html
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import deps
from .annotations import router as annotations_router
from .papers import router as papers_router
from .pipeline import router as pipeline_router
from .runs import papers_runs_router, router as runs_router

app = FastAPI(title="MKE Web API", description="介孔材料文献知识自动抽取系统 Web 接口")

# 开发模式：Vite dev server (:5173) 通过代理访问 /api，CORS 仅兜底直连场景
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")
app.include_router(annotations_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(papers_runs_router, prefix="/api")


@app.get("/api/health")
def health():
    """健康检查：报告模型配置（不泄露密钥），驱动前端"消耗 token"提示。"""
    from .deps import get_model_name

    import os
    return {
        "ok": True,
        "model": get_model_name(),
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"),
        "llm_configured": bool(os.environ.get("OPENAI_API_KEY")),
    }


# ---- 生产模式：托管前端构建产物（必须最后挂载，保证 /api 优先） ----
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.is_dir() and (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
