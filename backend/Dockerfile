# 使用官方 Python 运行时作为基础镜像
FROM python:3.11-slim

# 设置非交互式前端，避免安装过程中的提示
ENV DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 升级 pip
RUN pip install --upgrade pip

# 复制 requirements.txt
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Chromium 系统包及其依赖 (browser_use 使用自己的浏览器启动机制)
# 同时安装 Playwright 浏览器作为备选
RUN apt-get update && apt-get install -y \
    curl sudo \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# 确保 chromium 在 PATH 中 (browser_use 的 local_browser_watchdog 需要)
# Debian/slim 中 chromium 通常在 /usr/bin/chromium
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium

# 复制项目所有文件
COPY . .

# 暴露端口（仅供文档说明，Cloud Run 会自动处理）
EXPOSE 8080

# 启动命令
# Cloud Run 会注入 PORT 环境变量，exec 确保信号正确传递
# 对 browser_use + 本地 Chromium，显式使用 asyncio loop 更稳定
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --loop asyncio
