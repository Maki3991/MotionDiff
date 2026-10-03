AI软件创作赛道 - MotionDiff - MotionDiff 动作对比大师

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

VPS、子域名、HTTPS 和 API key 边界见 [VPS_DEPLOYMENT.md](docs/VPS_DEPLOYMENT.md)。当前网页入口先展示五个动作类别，再展示类别内动作；只有“力量 / 体能基础 → 深蹲”进入已实现的视频比较，其他动作会显示开发中状态。

## Git 同步范围

同步应用源码、`static/`、`tools/`、`analysis/` 下的 Python 脚本、文档和 `.gitignore`。`analysis/app_runs/`、`analysis/results/`、`reports/` 是测试和运行生成物；`videos/` 是原始素材；虚拟环境、缓存、模型和 `archive/` 也只保留在本机，不推送到 GitHub。Git 忽略规则只影响版本跟踪，不删除本地文件。

## 本地资料整理

- `analysis/app_runs/` 当前保留文档引用的 4 次完整运行：一次 `test2` A/B，以及 `test1` 的 A-B、A-C、A-D。新运行仍会写入这里。
- `archive/old-tests-2026-10-02/` 收纳 9 次旧版本或重复运行、早期 `analysis/results/` 实验产物和旧 `reports/` 报告。归档可恢复，但不节省磁盘空间；不要把它当成当前应用输出。
- `docs/STATUS.md` 是进度入口；`PRD.md`、`DECISIONS.md`、`DEMO_FLOW_ACCEPTANCE.md`、`POSE_DATA_CONTRACT.md`、`APP_RUN.md`、`VALIDATION_LOG.md` 仍用于需求、实现和验证。`GOAL_SETUP_QUESTIONNAIRE.md` 是已填写的历史团队选择记录；`MEDIAPIPE_EXPORT.md` 保留环境安装和独立导出说明，其中早期测试计划并非当前进度。
- `analysis/compare_test1.py`、`analysis/extract_frames.py` 是源脚本；`videos/` 是原始素材，`models/` 和 `.venv-mediapipe/` 是本机运行依赖。这些都没有作为旧测试结果清理。
