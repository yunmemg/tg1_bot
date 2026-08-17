#!/bin/bash
set -e

# 检查 .env 配置文件
if [ ! -f ".env" ]; then
    echo "未找到 .env 文件，正在从 .env.example 复制…"
    cp .env.example .env
    echo "请编辑 .env 文件，填入你的 BOT_TOKEN 后重新运行本脚本。"
    exit 1
fi

# 检查是否已配置 token
if grep -q "^BOT_TOKEN=123456789:" .env 2>/dev/null; then
    echo ".env 中的 BOT_TOKEN 还是示例值，请改为你自己的 Token（从 @BotFather 获取）。"
    exit 1
fi

# 优先使用虚拟环境；若 venv 不可用则回退到系统 Python
PY_CMD="python3"
if [ -d ".venv" ]; then
    PY_CMD=".venv/bin/python"
elif python3 -m venv --help >/dev/null 2>&1 && python3 -c "import ensurepip" >/dev/null 2>&1; then
    echo "创建虚拟环境并安装依赖…"
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    PY_CMD=".venv/bin/python"
else
    echo "虚拟环境不可用，使用系统 Python 并安装依赖…"
    pip3 install --break-system-packages -r requirements.txt
fi

echo "启动音乐机器人…"
exec $PY_CMD -m bot.main
