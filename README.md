# MotionDiff

本机双视频动作比较原型：在浏览器中选择参考视频和学员视频，由 MediaPipe 提取姿态并生成可回看的差异报告。当前仅针对 `videos/test2` 所示的站立侧抬腿与手臂抬起序列进行初步比较；新录视频验收仍待完成。

## 打开应用

在 **PowerShell** 中运行：

```powershell
Set-Location "D:\Softwares\Programming Projects\xi'an-hackathon\MotionDiff"
& .\.venv-mediapipe\Scripts\python.exe .\app.py
```

保持终端运行，在浏览器访问 **http://127.0.0.1:8765/**，再选择两段 MP4。`static/index.html` 不能直接双击打开：页面依赖应用服务器提供 `/static/styles.css`、JavaScript 和 `/api/analyze`。停止服务可在终端按 `Ctrl+C`。如果 8765 端口被占用，用 `& .\.venv-mediapipe\Scripts\python.exe .\app.py --port 8766` 并访问 `http://127.0.0.1:8766/`。

首次在另一台电脑克隆后，需要按照 [环境说明](docs/MEDIAPIPE_EXPORT.md) 建立 `.venv-mediapipe` 并下载模型到 `models/mediapipe/pose_landmarker_full.task`；这些本机依赖不在 Git 仓库中。当前进度与下一步见 [STATUS.md](docs/STATUS.md)，详细功能与结果说明见 [APP_RUN.md](docs/APP_RUN.md)。

## Git 同步范围

同步应用源码、`static/`、`tools/`、`analysis/` 下的 Python 脚本、文档和 `.gitignore`。`analysis/app_runs/`、`analysis/results/`、`reports/` 是测试和运行生成物；`videos/` 是原始素材；虚拟环境、缓存和模型也保留在本机，不推送到 GitHub。运行生成物仍留在当前电脑，Git 忽略规则只影响版本跟踪，不删除文件。
