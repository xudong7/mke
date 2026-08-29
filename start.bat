@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在启动 文献知识抽取系统 ...
uv run python run.py
pause
