# MotionDiff AI API 环境配置

这份文件说明下一轮接入 AI 建议时需要填写的环境变量。当前代码还没有调用 AI API；填写密钥不会自动产生网络请求。

## 填写位置

在项目根目录的 `.env` 中填写：

```env
AI_API_KEY=把黑客松提供的 API key 写在这里
AI_API_BASE_URL=把官方 API 地址写在这里
AI_MODEL=把官方模型名写在这里
AI_ENABLED=false
AI_TIMEOUT_SECONDS=45
AI_MAX_OUTPUT_TOKENS=1200
```

提交代码或上传截图时不要暴露 `AI_API_KEY`。这个密钥只能由 Python 后端读取，不能写入 `static/app.js`、HTML 或浏览器请求。

## 当前状态

- `.env`：本机填写，已加入 `.gitignore`。
- `.env.example`：不含真实密钥的配置模板，可以提交到 Git。
- `AI_ENABLED=false`：当前保持关闭，因为 API 协议、模型和输出格式还没有确认。
- 下一轮接入后，AI 请求应由后端发出，浏览器只接收脱敏后的建议结果。

## 需要从官方资料确认的字段

在打开 `AI_ENABLED` 前，确认以下信息：

1. API 是 OpenAI 兼容接口，还是自定义 REST 接口。
2. 完整请求地址和鉴权方式，是 `Authorization: Bearer` 还是其他 Header。
3. 可用模型名称、输入输出格式和单次请求限制。
4. 失败、超时、余额不足时的错误码和重试要求。

官方资料没有明确前，不要猜测 endpoint、模型名或请求字段。

接口协议和地址可以由 Agent 查资料确认；你只需提供 key，以及控制台给出的地址、模型名或接口文档链接。不必理解底层 API 协议。

官方接口文档链接（可自由填写）：

> 

数据发送范围和真人验收选择请填写 [AI_FEEDBACK_DECISIONS.md](AI_FEEDBACK_DECISIONS.md)。下一轮由程序加载 `.env`，核对提供商配置，按问卷授权范围进行真实调用；本轮不调用 API。该文件仅做配置说明，不要把真实 key 写在这里。
