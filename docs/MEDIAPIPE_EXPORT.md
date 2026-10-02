# MediaPipe 逐帧 JSON 导出与测速准备

- 日期：2026-10-02
- 状态：导出脚本、独立依赖环境和 Full 模型已准备；8 项完整性检查和 A 首帧真实接口验证通过。完整 A 视频导出与两引擎速度比较尚未执行。
- 入口：`tools/export_mediapipe_json.py`
- 范围：输入本地视频，每个解码帧同步调用一次 MediaPipe，逐帧保存 JSON，不抽帧、不渲染、不评分。

## 1. 环境与模型准备（不计入视频处理耗时）

使用官方预编译 Python SDK，无需编译旁边的 MediaPipe 源码仓库。依赖固定在 `tools/requirements-mediapipe.txt`，在独立虚拟环境安装，不修改现有全局 Python 环境。

当前工作区已完成下面的环境和模型准备，不必重复下载。MediaPipe 依赖 OpenCV contrib 发行包，因此只安装 `opencv-contrib-python`，避免两个 OpenCV wheel 同时提供 `cv2`。若未另设 `MPLCONFIGDIR`，导出脚本会把第三方字体缓存限定到项目 `.cache/matplotlib`。

从 PowerShell 执行：

```powershell
Set-Location "D:\Softwares\Programming Projects\xi'an-hackathon\MotionDiff"
python -m venv .venv-mediapipe
& .\.venv-mediapipe\Scripts\python.exe -m pip install -r .\tools\requirements-mediapipe.txt
New-Item -ItemType Directory -Force .\models\mediapipe | Out-Null
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task" -OutFile .\models\mediapipe\pose_landmarker_full.task
```

使用 Full 模型作为首轮候选，CPU 执行。模型文件名、SHA-256、实际 SDK 版本、Python 路径都会记录；这不是最终引擎选型。安装或下载失败时先解决准备问题，不把它计作模型处理视频的耗时。

## 2. A 视频导出命令（下一轮真实测试）

工作目录仍为 `MotionDiff`；输出目录必须不存在或为空。

```powershell
& .\.venv-mediapipe\Scripts\python.exe .\tools\export_mediapipe_json.py --video .\videos\test1\A.mp4 --model .\models\mediapipe\pose_landmarker_full.task --output-dir .\analysis\results\speed_benchmark\mediapipe_full_video\A
```

已通过视频元数据检查确认当前 A 为 1920×1080、30 FPS、47 帧。成功完整运行后，输出目录根部应有 47 个 `A_000000000000_keypoints.json` 至 `A_000000000046_keypoints.json`；实际生成数量需运行后核验。运行摘要放在 `_meta/run_summary.json`，不会混入根部逐帧 JSON。

默认 `--running-mode VIDEO` 是同步视频处理：每一帧都调用 `detect_for_video()`，没有抽帧或异步丢帧。MediaPipe 内部仍会使用跟踪优化。可显式指定 `--running-mode IMAGE`，在一个新的输出目录独立识别每帧；它也不抽帧，应视作单独实验。

## 3. 文件内容与已有 OpenPose 的关系

采用相同逐帧命名习惯，但保存原生 33 点语义，**不是** OpenPose BODY_25/75 数值格式；现有仅接受 BODY_25 的对比脚本不能直接读取。实现细节以 `POSE_DATA_CONTRACT.md` 的适配器附录为准。

- 每帧保存原始帧号、时间戳、解码画面尺寸和 `people`。
- 优先采用 OpenCV 解码时间戳；不可用时使用帧号/FPS，逐帧记录来源，并统计回退次数。VIDEO 的整数时间戳严格递增；若因毫秒取整需要调整，会单独记录。
- 每人保存 33 个有名称的点、像素坐标、原生归一化坐标、visibility/presence 和可用的估计三维坐标。
- 未识别人也保存 `people: []`，状态为 `no_pose_detected`，不缩短时间线。
- 不把低置信度点静默删掉；保存原始数值，留待比较层决定筛选方式。
- 处理失败、中断、声明帧数与解码数量不符时，摘要标为 failed/interrupted，不能当作完整导出。
- 拒绝往非空输出目录追加，避免覆盖或把多次结果混在一起。

## 4. 耗时定义与公平比较

脚本记录依赖导入、模型初始化、解码、色彩转换、同步推理、数据整理及 JSON 写盘、资源清理等耗时。

- `inference_seconds`：所有同步检测调用的总时间，不含解码和写盘。
- `processing_loop_seconds`：第一帧读取到最后一次读到视频结束，包含逐帧转换、推理、数据整理和写盘，不含模型初始化。
- `export_wall_seconds`：导出函数总耗时，包括模型加载、目录准备、处理和清理，截止最终摘要写入之前；不含依赖导入和解释器启动。
- `script_wall_seconds_before_final_summary`：从脚本开始执行计时到最终摘要写入之前，含依赖导入；仍不含 Python 解释器启动、最终摘要写入和进程退出。
- `processing_fps`：逐帧 JSON 数量除以 processing_loop_seconds；不是整个进程的吞吐率。

**两引擎主指标要用相同外部计时方法：启动进程到进程退出，包含模型初始化、视频读取、识别和逐帧 JSON 写盘。不要拿 OpenPose 总耗时与 MediaPipe 的纯 inference_seconds 直接比较。**

下一轮测试要求：

1. 顺序处理同一个原始 A.mp4，不同时运行两种引擎；逐帧，不缩短视频，不抽帧。
2. 都关闭显示、骨架渲染、输出视频，以及额外的独立人脸/手部任务；MediaPipe 的原生 33 点仍会输出。
3. 记录各自实际设备、模型、内部输入分辨率、人物数量设置及线程设置。当前脚本是 CPU、Full、最多一人；OpenPose 的实际构建和参数需在运行前核实。两种模型的内部工作量并不相同。
4. 检查每次都有 47 份逐帧 JSON，并记录有/无人体检测的帧数；运行成功与识别准确是不同验收项。
5. 首次运行与后续重复运行分开记录；各次使用独立输出目录，安装和模型下载在计时之前完成。
6. 结论限定为“这台电脑、这些版本和参数、这个视频的端到端用时”，不推出等精度或所有视频的速度结论。

## 5. 脚本检查与证据边界

```powershell
python -m unittest discover -s .\tools\tests -p test_export_mediapipe_json.py -v
```

该检查使用模拟检测器和临时文件，覆盖无人体帧也写 JSON、VIDEO/IMAGE 均逐帧、时间戳回退、坐标转换、异常/截断标记及拒绝覆盖。它不能证明真实模型加载、识别效果或耗时；真实模型状态在完成后另行记录。

2026-10-02 已执行的验证：

- 8 项完整性检查全部通过。
- Python 3.13.0 独立虚拟环境安装 MediaPipe 1.0.1、opencv-contrib-python 4.13.0.92。
- 官方 Full 模型文件 9,398,198 字节；SHA-256 为 `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`。
- CPU + VIDEO 模式成功加载模型，读取 A 第 0 帧（1920×1080），识别到 1 人、33 个关键点，调用本脚本的序列化函数后通过严格 JSON 编码。
- 此次只做真实首帧接口验证，没有导出完整 A，没有运行 OpenPose，也不报告速度比值或精度结论。下一轮执行第 2 节命令并按第 4 节统一计时。

## 官方接口来源

- https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python
- https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
- https://pypi.org/project/mediapipe/1.0.1/
