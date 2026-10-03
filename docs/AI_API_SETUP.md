# MotionDiff AI API 环境配置

AI 建议已接入 Python 后端。启动时自动读取项目根目录 `.env`，操作系统环境变量优先；修改后需重启服务。密钥只由后端读取。

## 填写位置

在项目根目录的 `.env` 中填写：

```env
AI_API_KEY=把黑客松提供的 API key 写在这里
AI_API_BASE_URL=https://api.openai-next.com/v1
AI_MODEL=gpt-6.1-sol
AI_ENABLED=true
AI_TIMEOUT_SECONDS=120
AI_MAX_OUTPUT_TOKENS=1200
```

提交代码或上传截图时不要暴露 `AI_API_KEY`。这个密钥只能由 Python 后端读取，不能写入 `static/app.js`、HTML 或浏览器请求。

## 当前状态

- `.env`：本机填写，已加入 `.gitignore`。
- `.env.example`：不含真实密钥的配置模板，可以提交到 Git。
- 本机 `.env` 已启用 AI；`.env.example` 保持关闭默认值。`AI_ENABLED=false` 时仅显示本地报告，不请求外部服务。
- AI 请求由后端发出，浏览器接收脱敏后的建议和本地证据。`action=squat` 启用深蹲流程；历史通用比较不调用 AI。
- 真实测试确认 `gpt-6.1-sol` 能通过 `/v1/responses` 接收文字指标和四张 JPEG、使用严格 JSON Schema 返回中文建议；也验证了零建议和超时状态。

## 接口与请求边界

官方快速接入：[OpenAI Next Quickstart](https://credits.openai-next.com/guide/quickstart)。该页面给出带 `/v1` 的 OpenAI 兼容地址和 Bearer 鉴权示例；Responses 路径、图像输入和严格结构化输出由本轮真实请求验证。

程序支持 base URL 带或不带 `/v1`，统一构建 `/v1/responses`；必须 HTTPS。请求使用 Bearer、`store:false`、低推理强度，默认 1200 输出 token；代码默认 45 秒网络超时，本机在连续超时后调至 90 秒（最大 120 秒）。不自动重试计费请求。

每次只发送深蹲窗口指标、数据质量、证据时间及参考/学员的下蹲中段和最低位四张截图。截图长边最多 640 像素、每张最多 200 KB。不发送整段视频、文件名、姓名、本地路径、密钥；内部髋膝尺度会转为高低关系后发送。

数据不足时不调用 API；格式错误、未知证据引用、服务拒绝访问或超时只影响 AI 区域，本地报告继续保存。页面建议标记“待核对”。`store:false` 不代表提供商作出零保留承诺。

## 本地检查

```powershell
& .\.venv-mediapipe\Scripts\python.exe .\app.py --port 8880
& .\.venv-mediapipe\Scripts\python.exe -m unittest discover -s tools/tests -v
```

浏览器打开 `http://127.0.0.1:8880/#analyze/strength/squat`。两段各为一次站立→下蹲→起身，使用相近侧面机位，完整露出身体。数据发送和本人验收按 [AI_FEEDBACK_DECISIONS.md](AI_FEEDBACK_DECISIONS.md) 执行。不要将 `.env` 提交或放进静态目录。
