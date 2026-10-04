# VPS 部署说明

当前 MotionDiff 是一个同源的 Python 服务：它同时提供 `static/` 页面、`/api/analyze` 上传接口、进度查询、视频文件和报告文件。姿态提取和比较由 VPS 本地 MediaPipe 运行；深蹲的可读建议可选调用外部 AI API，不需要数据库。

## 已上线实例：2026-10-04

- 地址：<https://motiondiff.maki3991.xyz/#analyze/strength/squat>，HTTP 自动跳转 HTTPS。
- 发布来源：GitHub `feature/ephemeral-runs`，线上代码提交 `313a3cd788548c93b19d9c9b37b8e79545cc1133`；`main` 仍保留之前的 `1652a76d045912ad1b5feadab89828b847f4eace`。
- 北京 ECS：`i-2zef1pphzxbat7xkfbxt`；Ubuntu 24.04、2 vCPU、约 1.6 GiB RAM。代码 `/opt/motiondiff`，虚拟环境 `/opt/motiondiff/.venv`，独立用户及服务 `motiondiff` / `motiondiff.service`。
- 后端仅监听 `127.0.0.1:8765`；Nginx 配置 `/etc/nginx/sites-available/motiondiff.maki3991.xyz`。现有 study 的目录、站点配置、systemd 配置和证书均未修改，服务未停止或重启。
- API 配置通过 `/etc/motiondiff/ai.env` 注入，权限 `600`，目录权限 `700`；密钥未进入仓库或静态资源。
- 当前线上结果目录是 tmpfs `/dev/shm/motiondiff-runs`。页面离开或刷新会请求删除整次任务；异常退出由默认 30 分钟空闲 TTL 兜底，服务重启时清理残留任务目录。旧持久目录 `/var/lib/motiondiff/runs` 仍有约 6.5 MiB 历史数据，尚未删除，但不再接收新任务。
- 系统依赖含 `python3-venv libgl1 libegl1 libgles2`。仅导入 MediaPipe 不能验证运行库完整；已实际创建 PoseLandmarker 并处理视频。
- 为给 study 留出资源，MotionDiff 使用 `CPUQuota=100%`、`MemoryHigh=750M`、`MemoryMax=900M`，`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`，对齐预算 `MOTIONDIFF_MAX_ALIGNMENT_CELLS=810000`。建议每段 5～15 秒、一次深蹲；60 秒只是时长上限，两段帧数乘积超过预算仍会拒绝。
- Nginx 已启用每 IP 平均每分钟 3 次上传、有限突发、最多 2 条上传连接；后端同时只处理一组视频，每段上限 50 MiB / 60 秒。
- Let's Encrypt 证书已签发，`certbot.timer` 活跃；续期钩子 `/etc/letsencrypt/renewal-hooks/deploy/motiondiff-nginx.sh` 在 `nginx -t` 通过后平滑 reload。
- 公网真实任务 `c0c6624d529b42cd8bf52af0f45c282b`：99 / 171 帧，44.77 秒，报告和 AI 建议均 `complete`；手机及桌面浏览器已验证报告和两段视频，详见 [VALIDATION_LOG.md](VALIDATION_LOG.md)。这是一次链路验证，不代表 AI 建议已通过教练验收或所有网络均稳定。

仓库中的 [deploy/motiondiff.service](../deploy/motiondiff.service) 已安装为线上 unit。MotionDiff 专属旧 unit 和 Nginx 配置备份在 `/root/motiondiff-pre-ephemeral-20261004/`；Nginx 已配置 `proxy_buffering off`。

日常只读检查：

```bash
systemctl status motiondiff --no-pager
journalctl -u motiondiff -n 80 --no-pager
curl -fsS http://127.0.0.1:8765/healthz
du -sh /var/lib/motiondiff/runs
```

## 1. VPS 环境

以下命令以 Ubuntu/Debian 和项目目录 `/opt/motiondiff` 为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv git libgl1 libegl1 libgles2
sudo mkdir -p /opt/motiondiff
sudo chown "$USER":"$USER" /opt/motiondiff
git clone <repository-url> /opt/motiondiff
cd /opt/motiondiff
python3 -m venv .venv
. .venv/bin/activate
pip install -r tools/requirements-mediapipe.txt
mkdir -p models/mediapipe
mkdir -m 700 -p /dev/shm/motiondiff-runs
```

把 `pose_landmarker_full.task` 上传到：

```text
/opt/motiondiff/models/mediapipe/pose_landmarker_full.task
```

若使用 `motiondiff` systemd 用户启动，先用 `sudo install -d -m 700 -o motiondiff -g motiondiff /dev/shm/motiondiff-runs` 建目录。`/dev/shm` 重启后清空，需在服务启动时重复建目录；应用启动也会创建并收紧目录权限，但前提是服务用户对父目录有写入权限。

安装仓库内 systemd 模板时，先确认目标服务和备份现有 unit：

```bash
sudo install -m 644 deploy/motiondiff.service /etc/systemd/system/motiondiff.service
sudo systemctl daemon-reload
sudo systemctl restart motiondiff
```

该模板在启动前由服务用户创建目录，并让应用进程固定使用 `/dev/shm/motiondiff-runs`，即使环境文件中设置了旧目录也不会覆盖它。`ReadWritePaths` 使用始终存在的 `/dev/shm`，避免 VPS 重启后任务子目录尚未创建时启动失败；任务目录自身权限为 700。服务重启后应用会清理残留的随机任务目录。重启后应检查 `systemctl cat motiondiff`、`df -h /dev/shm`、`curl -fsS http://127.0.0.1:8765/healthz`，再做一次完整分析。这里的 `restart` 会中断正在进行的分析，只应在没有需要保留的线上任务时执行。

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
| `MOTIONDIFF_RUNS_DIR` | Linux: `/dev/shm/motiondiff-runs` | 一次性视频、逐帧 JSON 和报告目录；Linux 正式部署必须使用 RAM-backed tmpfs，不要改到持久磁盘 |
| `MOTIONDIFF_RUN_IDLE_TTL_SECONDS` | `1800` | 页面异常离开时的兜底过期时间；超过后删除整次任务 |
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
    proxy_buffering off;

    location = /api/analyze {
        limit_req zone=motiondiff_upload_rate burst=2 nodelay;
        limit_req_status 429;
        limit_conn motiondiff_upload_connections 2;
        limit_conn_status 429;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_pass http://127.0.0.1:8765;
    }

    location / {
        proxy_pass http://127.0.0.1:8765;
    }
}
```

当前前端使用相对路径请求 `/api/analyze`，所以前后端放在同一子域名下时不需要 CORS 配置。该示例平均每 IP 每分钟 3 次上传、允许有限突发，同时最多 2 条上传连接；关闭请求缓冲让后端忙碌时立即拒绝新上传。后端自身只允许一组上传／分析，接收超时为空闲 30 秒、总计 120 秒。若前面再接 Cloudflare，部署时配置可信来源的真实 IP 恢复，否则限流可能把所有用户视为代理 IP。

配置校验应使用 `nginx -t`，通过后再重新加载。改动只放在新服务子域名，不停止既有服务。以上为可复用示例；当前已上线实例的具体状态见本文开头。

## 4. API key 边界

`/api/analyze` 是 MotionDiff 自己的 HTTP 接口，姿态分析仍由本地 MediaPipe 完成。`action=squat` 在服务端读取 `.env` 中的 AI 配置并调用外部 Responses API；通用比较不调用 AI。AI 不可用时本地报告仍完成。

黑客松提供的 API key 可用于生成深蹲文字总结，但应放在 VPS 的环境变量或 systemd `EnvironmentFile` 中，不能写进 `static/app.js`、HTML、Git 或报告文件。部署前仍需确认供应商、API 基础 URL、模型名、计费/限额和允许的出网策略；完整配置见 [AI_API_SETUP.md](AI_API_SETUP.md)。

## 5. 一次性结果与数据清理

- 上传视频、MediaPipe JSON 和 Markdown/JSON 报告全部写入 `MOTIONDIFF_RUNS_DIR`。Linux 正式部署应设置为 `/dev/shm/motiondiff-runs`，该目录位于内存文件系统；应用进程重启会清理旧任务目录，VPS 重启会清空 tmpfs。
- 页面刷新、关闭或离开页面时，浏览器会请求 `POST /api/runs/<run_id>/delete` 删除整次任务；点击“重新分析”也会删除上一任务。接口是幂等的。浏览器只在 `sessionStorage` 暂存随机任务 ID，刷新后的新页面会再次请求删除；不在浏览器存储报告或视频。
- 如果浏览器崩溃、断网或请求未送达，后台每分钟检查一次，默认 30 分钟无访问后删除整次任务。报告链接和视频链接在删除后都会返回 404。刷新即时清理依赖浏览器请求成功；这不是浏览器异常退出时的严格零延迟保证。
- 因此这是“分析期间临时存在、结束后销毁”的方案，不提供跨刷新、跨设备恢复报告。前端不会恢复 `sessionStorage` 中的旧任务。
- `/dev/shm` 受 VPS 内存限制；上传上限、MediaPipe 中间数据和报告必须一起计入内存预算。若内存不足，应降低视频大小/时长或配置更大的 tmpfs，而不能退回持久磁盘。
- Linux 启动时会检查运行目录实际所在的文件系统，若不是 tmpfs 就拒绝启动，避免误把视频写入普通磁盘。Nginx 配置还应关闭本服务的响应缓冲落盘（`proxy_buffering off`）。
- 这里清理的是任务视频、逐帧数据和报告文件；Nginx/systemd 常规访问日志可能仍记录访问时间、IP 和 URL，但不应记录视频或报告正文。外部 AI 服务会接收当前已配置的派生指标和少量证据截图，其保留策略由该服务决定。

## 6. 当前上线边界

- 当前服务适合黑客松单进程演示，已包含大小／时长／帧数限制、一组上传／分析占用控制和一次性任务清理；仍不包含用户认证、分布式限流和排队。Nginx 限流示例需要部署时生效。
- 时长预检使用 OpenCV 容器帧数／帧率估算，提取时再检查实际时间及帧数，不能把文件扩展名或浏览器上报视作可靠证据。单靠一分钟时长限制无法阻止重复或分布式攻击。
- 建议先限制短视频和单一动作，并监控 CPU、内存和磁盘占用。
- 如果以后要在网页中直接录制手机视频，需要 HTTPS 和额外的 `MediaRecorder`/摄像头权限实现；部署本身不会自动提供录制功能。
