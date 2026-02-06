# EvalAgent 云端运维与存储管理指南

本文档记录了如何管理部署在 Google Cloud 上的后端服务，特别是如何操作 Google Cloud Storage (GCS) 中的持久化数据（历史日志和截图）。

> **项目配置信息**
> *   **Project ID**: `1099182984762`
> *   **Region**: `us-central1`
> *   **Bucket Name**: `gs://1099182984762-history-logs`
> *   **Cloud Run Service**: `eval-agent-backend`

---

## 1. 查看云端数据 (List)

不需要下载数据，可以直接在命令行查看云端 Bucket 中的内容。

**查看根目录文件：**
```powershell
gcloud storage ls gs://1099182984762-history-logs/
```

**递归查看所有文件（包含子文件夹中的截图等）：**
```powershell
gcloud storage ls --recursive gs://1099182984762-history-logs/
```

---

## 2. 删除云端数据 (Delete)

您可以直接远程删除不需要的数据及文件夹。

**删除单个文件：**
```powershell
gcloud storage rm gs://1099182984762-history-logs/old_log_file.json
```

**递归删除文件夹（例如删除某次运行的截图）：**
```powershell
# 请务必确认路径正确，操作不可逆
gcloud storage rm --recursive gs://1099182984762-history-logs/screenshots/Buy_milk_OLD_RUN/
```

**清空整个 Bucket（慎用）：**
```powershell
gcloud storage rm --recursive gs://1099182984762-history-logs/*
```

---

## 3. 数据同步 (Sync)

### 场景 A：手动上传本地数据
如果您在本地生成了新的日志，想补充上传到云端（不会删除云端已有文件）。

```powershell
# 1. 进入本地数据目录
cd history_logs

# 2. 递归上传当前目录下的所有内容到 Bucket 根目录
gcloud storage cp -r . gs://1099182984762-history-logs/
```

### 场景 B：完全镜像同步（Make Mirror）
如果您希望云端的状态**完全变得和本地一致**。
*   **警告**：这会**删除**云端存在但本地不存在的文件。

```powershell
# 在 backend 根目录下执行
# 将本地 history_logs 文件夹的内容同步到云端 Bucket
gcloud storage rsync -r --delete-unmatched-destination-objects history_logs gs://1099182984762-history-logs
```

---

## 4. 重新部署命令
每次代码修改后，使用以下命令重新部署（已包含存储挂载参数）：

**CMD / PowerShell:**
```powershell
gcloud run deploy eval-agent-backend ^
  --source . ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --execution-environment gen2 ^
  --add-volume name=logs-storage,type=cloud-storage,bucket=1099182984762-history-logs ^
  --add-volume-mount volume=logs-storage,mount-path=/app/history_logs
```
