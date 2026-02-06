# EvalAgent 后端部署文档

本文档详细说明了如何将 EvalAgent 后端服务部署到 Google Cloud Run。

## 前置条件

1.  **Google Cloud 账号**：拥有一个可用的 Google Cloud 项目。
2.  **Google Cloud CLI**：本地已安装 `gcloud` 命令行工具。
3.  **Firebase 项目（可选）**：如果与前端集成，建议使用 Firebase 项目。
4.  **Billing**：项目必须绑定计费账户（Blaze 计划），但在免费额度内通常不收费。

## 部署步骤

### 1. 初始化 Google Cloud 环境

如果你是第一次部署，请先登录并设置项目：

```powershell
# 1. 登录 Google Cloud
gcloud auth login

# 2. 设置项目 ID (替换 <YOUR_PROJECT_ID>)
gcloud config set project <YOUR_PROJECT_ID>

# 3. 设置代理 (仅中国大陆用户需要，根据实际端口修改，例如 7890)
gcloud config set proxy/type http
gcloud config set proxy/address 127.0.0.1
gcloud config set proxy/port 1080
```

### 2. 准备持久化存储 (重要)

为了在重新部署后保留历史记录 (`history_logs`) 和截图，我们使用 Google Cloud Storage (GCS) 进行挂载。

1.  **创建存储桶** (如果尚未创建)：
    ```powershell
    # 替换 <YOUR_PROJECT_ID> 为你的真实项目 ID
    gcloud storage buckets create gs://<YOUR_PROJECT_ID>-history-logs --location=us-central1
    ```

2.  **上传本地预置数据** (可选，将本地现有的 logs 和截图上传)：
    ```powershell
    # 进入 history_logs 目录
    cd history_logs
    # 递归上传所有内容到 Bucket 根目录
    gcloud storage cp -r . gs://<YOUR_PROJECT_ID>-history-logs/
    # 返回上级目录
    cd ..
    ```

### 3. 部署到 Cloud Run (带存储挂载)

在 `backend` 目录下运行以下命令。请将 `<YOUR_PROJECT_ID>` 替换为实际 ID。

**PowerShell / CMD:**
```powershell
gcloud run deploy eval-agent-backend --source . --region us-central1 --allow-unauthenticated --execution-environment gen2 --add-volume name=logs-storage,type=cloud-storage,bucket=1099182984762-history-logs --add-volume-mount volume=logs-storage,mount-path=/app/history_logs
```

**交互提示说明：**
*   **Enable APIs**: 首次运行如果提示启用 API (Artifact Registry, Cloud Build 等)，输入 `y` 确认。
*   **Create Repository**: 如果提示创建 Docker repository，输入 `y` 确认。
*   **Allow unauthenticated**: 必须为 `y`，否则外部无法访问 API。

### 3. 验证部署

部署成功后，终端会输出一个 Service URL，例如：
`https://eval-agent-backend-xxxxx-uc.a.run.app`

访问 `https://<你的URL>/docs` 即可查看 Swagger API 文档。

---

## 常见问题处理

### 1. 权限错误 (Permission Denied) / API Disabled
*   **现象**：
    *   提示 `API disabled` (例如 `Cloud Run Admin API has not been used in project ...`).
    *   提示 `permission denied`.
*   **解决**：
    *   **启用 API**：根据报错提示的链接（通常是 console.developers.google.com/...）去启用相应的 API (如 Cloud Run Admin API)。
    *   或者使用命令启用：`gcloud services enable run.googleapis.com`
    *   启用后，等待 1-2 分钟让变更生效，然后重试命令。

### 2. 网络错误 (SSL Error / Connection Reset)
*   **现象**：`SSLError(SSLEOFError)` 或连接超时。
*   **解决**：检查代理设置。确保终端的环境变量也配置了代理：
    ```cmd
    set HTTP_PROXY=http://127.0.0.1:1080
    set HTTPS_PROXY=http://127.0.0.1:1080
    ```

### 3. 计费问题
*   **现象**：提示需要开启 Billing。
*   **解决**：前往 Google Cloud Console -> Billing，关联信用卡。只要不手动修改最小实例数 (`min-instances`) 为 1 以上，个人测试通常都在免费额度内。

## 配置说明

### Dockerfile
项目根目录包含 `Dockerfile`，定义了运行环境：
*   基于 Python 3.11 Slim 镜像。
*   自动安装 `requirements.txt` 依赖。
*   使用 `uvicorn` 启动服务，端口自动适配 `$PORT` 环境变量。

### .dockerignore
用于排除不需要上传到云端的文件（如 `venv`, `.env`, `__pycache__` 等），加快构建速度。
