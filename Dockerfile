FROM python:3.11-slim

WORKDIR /app

# 依赖层单独缓存，代码变更时不重复安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 启动音乐机器人（长驻轮询进程，无需暴露端口）
CMD ["python", "-m", "bot.main"]
