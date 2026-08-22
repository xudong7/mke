.PHONY: dev backend frontend build prod clean install

# === 开发模式 ===
# 并行启动前后端（后台运行），Ctrl+C 同时停止
dev:
	@echo "启动后端 :8000 + 前端 :5173 ..."
	@trap 'kill 0' EXIT; \
	uv run uvicorn backend.main:app --reload --port 8000 & \
	cd frontend && npm run dev & \
	wait

# 仅后端（:8000）
backend:
	uv run uvicorn backend.main:app --reload --port 8000

# 仅前端（:5173）
frontend:
	cd frontend && npm run dev

# === 生产模式 ===
# 构建前端后单端口启动（:8000）
build:
	cd frontend && npm run build

prod: build
	uv run uvicorn backend.main:app --port 8000

# === 工具 ===
# 安装全部依赖
install:
	uv sync
	cd frontend && npm install

# 停止 :8000 :5173 上的进程
clean:
	@lsof -ti :8000 | xargs kill 2>/dev/null || true
	@lsof -ti :5173 | xargs kill 2>/dev/null || true
	@echo "已停止 :8000 :5173"