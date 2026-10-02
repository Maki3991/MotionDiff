# MotionDiff 两视频比较应用

这是当前首版的本机浏览器应用。它接收一段参考视频和一段学员视频，用 MediaPipe Pose Landmarker 逐帧导出 JSON，再进行动作序列对齐和差异比较。

首版支持的素材是 `videos/test2/A-标准.mp4` 和 `videos/test2/B-学员.mp4` 所展示的站立侧抬腿并伴随手臂摆动动作。新录视频应尽量保持正面方向、相近相机高度和距离，并保证一个人完整出镜。

## 启动

在 PowerShell 中执行：

```powershell
Set-Location "D:\Softwares\Programming Projects\xi'an-hackathon\MotionDiff"
& .\.venv-mediapipe\Scripts\python.exe .\app.py
```

浏览器打开 `http://127.0.0.1:8765/`。在页面选择参考视频和学员视频，然后点击“开始分析”。

应用要求项目内已有：

- `.venv-mediapipe`：MediaPipe Python 环境；
- `models/mediapipe/pose_landmarker_full.task`：Full 模型文件。

如果需要重新准备环境，参见 [MEDIAPIPE_EXPORT.md](MEDIAPIPE_EXPORT.md)。

## 每次分析的产物

每次运行生成在 `analysis/app_runs/<run_id>/`：

```text
input/reference.mp4              参考原视频
input/student.mp4                学员原视频
pose/reference/*_keypoints.json  参考视频逐帧 MediaPipe 数据
pose/student/*_keypoints.json    学员视频逐帧 MediaPipe 数据
report/comparison.json            结构化比较结果
report/comparison.md              可读 Markdown 报告
```

逐帧 JSON 保留原始帧号、时间戳、画面尺寸、33 个带语义名称的 MediaPipe 关键点，以及 `visibility`、`presence` 和可选的世界坐标。比较层再根据双肩中点和双肩距离做归一化。

## 当前比较方法

1. 将每帧的双肩中点作为中心，以双肩距离作为尺度，减少人物大小和画面平移的影响。
2. 使用肩、肘、腕、髋、膝、踝的有效关键点做 DTW 时间对齐，允许两段动作速度不同。
3. 计算每个关键点的平均位置差、P90 差异和四段动作进度中的峰值差异。
4. 计算肘、肩、膝和髋的二维投影夹角差。
5. 生成一个**未校准相似度指数**，并列出主要关节及其相对参考视频的位置提示。

这个指数不是合格线，也不代表安全或专业动作结论。二维单目数据仍然依赖相近拍摄方向；识别失败、缺少关键点或机位差异过大时，结果应按“无法判断”处理。

## 已完成的 test2 运行

MediaPipe Full、CPU、VIDEO 模式、逐帧处理：

- A：396 帧，395 帧检测到人；导出脚本处理循环约 7.88 秒，脚本总耗时约 9.14 秒；
- B：298 帧，298 帧检测到人；导出脚本处理循环约 6.07 秒，脚本总耗时约 6.90 秒；
- 比较结果：436 个 DTW 对齐帧，平均位置差约 0.0775 个肩宽，未校准相似度指数约 75.4/100；
- 主要差异包括右踝、右膝、左手腕、右手腕、左踝和右髋，结果中的每条提示带有动作进度区间和峰值帧号。

这些数字是这两段素材的一次运行结果，不是通用精度或性能承诺。完整样例在 `analysis/results/test2_mediapipe_full/comparison.md`。

## 后续验收

团队问卷选择了新视频验收。当前 test2 结果证明了固定素材的完整链路；仍需另一位参与者在相同拍摄条件下录制同一动作，确认普通重复不会出现大量无依据差异、刻意制造的变化能够被定位。新视频未验收前，不把“应用已完成”解释为“对所有人和所有机位都可靠”。
