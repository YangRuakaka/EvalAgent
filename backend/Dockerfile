# 使用官方 Python 运行时作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统基础工具 (Playwright 需要)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器和系统依赖
RUN playwright install --with-deps chromium

# 复制项目所有文件
COPY . .

# 暴露端口（仅供文档说明，Cloud Run 会自动处理）
EXPOSE 8080

# 启动命令
# Cloud Run 会注入 PORT 环境变量，exec 确保信号正确传递
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
