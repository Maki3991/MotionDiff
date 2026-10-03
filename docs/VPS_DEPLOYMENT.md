# VPS 部署说明

当前 MotionDiff 是一个同源的 Python 服务：它同时提供 `static/` 页面、`/api/analyze` 上传接口、进度查询、视频文件和报告文件。VPS 部署不需要数据库，也不需要外部 AI API；MediaPipe 在 VPS 本地运行。

## 1. VPS 环境

以下命令以 Ubuntu/Debian 和项目目录 `/opt/motiondiff` 为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
sudo mkdir -p /opt/motiondiff
sudo chown "$USER":"$USER" /opt/motiondiff
git clone <repository-url> /opt/motiondiff
cd /opt/motiondiff
python3 -m venv .venv
. .venv/bin/activate
pip install -r tools/requirements-mediapipe.txt
mkdir -p models/mediapipe analysis/app_runs
```

把 `pose_landmarker_full.task` 上传到：

```text
/opt/motiondiff/models/mediapipe/pose_landmarker_full.task
```

模型文件和虚拟环境被 `.gitignore` 排除，不能假设 `git clone` 会带上它们。

## 2. 服务进程

先直接验证：

```bash
cd /opt/motiondiff
. .venv/bin/activate
MOTIONDIFF_HOST=127.0.0.1 MOTIONDIFF_PORT=8765 python app.py
```

健康检查地址为 `http://127.0.0.1:8765/healthz`。正式运行时建议使用 systemd，并让 Nginx 或 Caddy 负责 HTTPS 和公网 443 端口。

可用的部署环境变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `MOTIONDIFF_HOST` | `127.0.0.1` | 监听地址 |
| `MOTIONDIFF_PORT` | `8765` | 服务端口 |
| `MOTIONDIFF_MODEL_PATH` | 项目内模型路径 | 模型文件位置 |
| `MOTIONDIFF_RUNS_DIR` | `analysis/app_runs` | 上传视频、逐帧 JSON 和报告的持久目录 |
| `MOTIONDIFF_MAX_UPLOAD_BYTES` | `105906176` | 单次 multipart 请求上限，101 MiB |
| `MOTIONDIFF_MAX_VIDEO_BYTES` | `52428800` | 每个视频上限，50 MiB |
| `MOTIONDIFF_MAX_VIDEO_SECONDS` | `60` | 每个视频时长上限，秒 |
| `MOTIONDIFF_MAX_VIDEO_FRAMES` | `3600` | 每个视频帧数上限 |
| `MOTIONDIFF_MAX_ALIGNMENT_CELLS` | `3240000` | 两段视频帧数乘积上限，控制当前 DTW 内存 |

## 3. 反向代理

把子域名（例如 `motion.example.com`）解析到 VPS，并将 HTTPS 请求转发到 `127.0.0.1:8765`。代理的请求体上限与后端保持一致。下面是待部署的示例，不表示已修改 VPS；HTTPS 证书配置另行添加。两个 `limit_*_zone` 放在 Nginx `http` 上下文内，并使用本服务专属名称，避免影响现有站点：

```nginx
limit_req_zone $binary_remote_addr zone=motiondiff_upload_rate:10m rate=3r/m;
limit_conn_zone $binary_remote_addr zone=motiondiff_upload_connections:10m;

server {
    server_name motion.example.com;
    client_max_body_size 101M;
    client_body_timeout 30s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;

    location = /api/analyze {
        limit_req zone=motiondiff_upload_rate burst=2 nodelay;
        limit_req_status 429;
        limit_conn motiondiff_upload_connections 2;
        limit_conn_status 429;
        proxy_request_buffering off;
        proxy_pass http://127.0.0.1:8765;
    }

    location / {
        proxy_pass http://127.0.0.1:8765;
    }
}
```

当前前端使用相对路径请求 `/api/analyze`，所以前后端放在同一子域名下时不需要 CORS 配置。该示例平均每 IP 每分钟 3 次上传、允许有限突发，同时最多 2 条上传连接；关闭请求缓冲让后端忙碌时立即拒绝新上传。后端自身只允许一组上传／分析，接收超时为空闲 30 秒、总计 120 秒。若前面再接 Cloudflare，部署时配置可信来源的真实 IP 恢复，否则限流可能把所有用户视为代理 IP。

配置校验应使用 `nginx -t`，通过后再重新加载。改动只放在新服务子域名，不停止既有服务。本轮只准备示例，没有连接 VPS 或应用 Nginx 配置。

## 4. API key 边界

当前代码没有读取或调用任何外部 API key。`/api/analyze` 是 MotionDiff 自己的 HTTP 接口，姿态分析由本地 MediaPipe 完成。

黑客松提供的 API key 只有在明确接入某个外部能力时才需要，例如生成文字总结、调用云端模型或对象存储。届时应放在 VPS 的环境变量或 systemd `EnvironmentFile` 中，不能写进 `static/app.js`、HTML、Git 或报告文件。接入前需要确认供应商、API 基础 URL、模型名、计费/限额和允许的出网策略。

## 5. 当前上线边界

- 运行目录必须使用持久磁盘；容器重启后不能依赖内存中的任务状态恢复页面。
- 当前服务适合黑客松单进程演示，已包含大小／时长／帧数限制及一组上传／分析占用控制，不包含用户认证、分布式限流、排队和自动清理。Nginx 限流示例需要部署时生效。
- 时长预检使用 OpenCV 容器帧数／帧率估算，提取时再检查实际时间及帧数，不能把文件扩展名或浏览器上报视作可靠证据。超限制预检会删除两个上传视频；成功任务、运行中失败的部分 JSON 仍保留，公开长期运行前需补定期清理、磁盘配额或演示访问口令。单靠一分钟时长限制无法阻止重复或分布式攻击。
- 建议先限制短视频和单一动作，并监控 CPU、内存和磁盘占用。
- 如果以后要在网页中直接录制手机视频，需要 HTTPS 和额外的 `MediaRecorder`/摄像头权限实现；部署本身不会自动提供录制功能。
